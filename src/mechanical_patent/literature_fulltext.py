"""学术论文合规 PDF 获取、离线解析、页码证据与项目级断点恢复。

文献下载必须经过案卷保密外发审批、逐篇许可核验及显式执行授权。
仅接受提供方返回且经过许可确认的 OA PDF，严禁从任意网页猜测链接。
真正的文献技术结论仍需要研究人员结合原始 PDF 逐项核实。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable
from urllib.parse import urlsplit
from uuid import uuid4

from .core import PatentWorkflowError, utc_now
from .literature_memory import (
    LiteratureMemoryStore, _atomic_text, _safe_markdown, AUTO_END, MAX_NOTES,
)
from .pdf_archive import MAX_PDF_BYTES, download_pdf
from .pdf_extraction import parse_local_pdf

_LICENSES = frozenset({
    "cc0", "cc010", "cczero", "publicdomain",
    "ccby", "ccby30", "ccby40",
    "ccbysa", "ccbysa30", "ccbysa40",
})
_PDF_DOC = re.compile(r"EV-[0-9A-F]{12}\Z")
_HASH = re.compile(r"[a-f0-9]{64}\Z")


def _licensed(value: str) -> bool:
    """来源声明的标准开放许可证；非商业/禁止改编与未知许可均需人工另行处理。"""
    cleaned = re.sub(r"[^a-z0-9]", "", str(value).lower())
    return cleaned in _LICENSES


def _host(url: str) -> str:
    try:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise PatentWorkflowError("PDF 候选地址必须是无认证信息的 HTTPS URL。")
        if parts.port not in (None, 443):
            raise PatentWorkflowError("PDF 候选地址不能使用非标准端口。")
        return parts.hostname.lower().rstrip(".")
    except ValueError as exc:
        raise PatentWorkflowError("PDF 地址的端口或域名无效。") from exc


def _sha_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


class FulltextPipeline:
    """项目知识库的全生命周期：queued → downloading → downloaded → parsing → parsed。

    同项目共享 SQLite 事务与文件目录；不借助全局数据库，租约到期可重试。
    parsed 仅指解析器已运行，full_text_verified 始终为 false。
    """

    def __init__(self, memory: LiteratureMemoryStore):
        self.memory = memory
        self.root = memory.root / "fulltext"
        if self.root.is_symlink():
            raise PatentWorkflowError("全文目录禁止符号链接。")
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        with self.memory.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS fulltext_jobs(
                  doc_id TEXT PRIMARY KEY REFERENCES documents(doc_id) ON DELETE CASCADE,
                  pdf_url TEXT NOT NULL,
                  source_license TEXT NOT NULL,
                  rights_actor TEXT NOT NULL,
                  rights_reference TEXT NOT NULL,
                  status TEXT NOT NULL,
                  attempts INTEGER NOT NULL DEFAULT 0,
                  lease_owner TEXT NOT NULL DEFAULT '',
                  lease_expires TEXT,
                  pdf_sha256 TEXT NOT NULL DEFAULT '',
                  pdf_path TEXT NOT NULL DEFAULT '',
                  parse_sha256 TEXT NOT NULL DEFAULT '',
                  parse_path TEXT NOT NULL DEFAULT '',
                  error TEXT NOT NULL DEFAULT '',
                  last_updated TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_fulltext_jobs_status
                  ON fulltext_jobs(status,last_updated);
                CREATE TABLE IF NOT EXISTS fulltext_blocks(
                  doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                  block_no INTEGER NOT NULL,
                  page_no INTEGER,
                  label TEXT NOT NULL,
                  content TEXT NOT NULL,
                  source_pdf_sha256 TEXT NOT NULL,
                  PRIMARY KEY(doc_id,block_no)
                );
                CREATE INDEX IF NOT EXISTS idx_fulltext_blocks_doc_page
                  ON fulltext_blocks(doc_id,page_no,block_no);
                CREATE TABLE IF NOT EXISTS fulltext_events(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  doc_id TEXT NOT NULL,
                  event TEXT NOT NULL,
                  actor TEXT NOT NULL,
                  detail TEXT NOT NULL,
                  recorded_at TEXT NOT NULL
                );
            """)
            try:
                db.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS fulltext_blocks_fts "
                    "USING fts5(doc_id UNINDEXED,block_no UNINDEXED,content,tokenize='trigram')"
                )
            except sqlite3.OperationalError:
                pass

    def _event(self, db: sqlite3.Connection, doc_id: str, event: str,
               actor: str, detail: str = "") -> None:
        db.execute(
            "INSERT INTO fulltext_events(doc_id,event,actor,detail,recorded_at)"
            " VALUES(?,?,?,?,?)",
            (doc_id, event, actor[:100], detail[:700], utc_now()),
        )

    def status(self, doc_id: str) -> dict[str, Any]:
        if not _PDF_DOC.fullmatch(doc_id):
            raise PatentWorkflowError("文献 ID 无效。")
        with self.memory.connect() as db:
            row = db.execute(
                "SELECT * FROM fulltext_jobs WHERE doc_id=?", (doc_id,)
            ).fetchone()
            total = db.execute(
                "SELECT COUNT(*) FROM fulltext_blocks WHERE doc_id=?", (doc_id,)
            ).fetchone()[0]
        if row is None:
            return {"doc_id": doc_id, "status": "not_planned",
                    "extracted_blocks": total, "full_text_verified": False}
        item = dict(row)
        item["extracted_blocks"] = total
        item["full_text_verified"] = False
        return item

    def queue(self, doc_id: str, *, rights_actor: str, rights_reference: str,
              authorized: bool) -> dict[str, Any]:
        """法律审批记录由外部真实身份/权限层承认；不能把本工具参数当成签名。"""
        if not authorized:
            raise PatentWorkflowError("全文处理需要逐篇显式许可确认。")
        actor = rights_actor.strip()[:100]
        reference = rights_reference.strip()[:300]
        if len(actor) < 2 or len(reference) < 8:
            raise PatentWorkflowError("需要保留真实审批人标识及可追查的许可记录编号。")
        if not _PDF_DOC.fullmatch(doc_id):
            raise PatentWorkflowError("文献编号无效。")
        with self.memory.connect(write=True) as db:
            document = db.execute(
                "SELECT doc_id,kind,pdf_url,metadata_json FROM documents WHERE doc_id=?",
                (doc_id,),
            ).fetchone()
            if document is None or document["kind"] != "paper":
                raise PatentWorkflowError("仅可对项目知识库中存在的论文制定 PDF 任务。")
            metadata = json.loads(document["metadata_json"] or "{}")
            if metadata.get("is_open_access") is not True:
                raise PatentWorkflowError("尚无明确的开放获取来源标记，拒绝批量下载。")
            license_name = str(metadata.get("license") or "")
            if not _licensed(license_name):
                raise PatentWorkflowError("论文许可不满足开放归档白名单；需人工另行核实。")
            url = str(document["pdf_url"] or "")
            if not url:
                raise PatentWorkflowError("论文尚未发现可追溯的 PDF 候选链接。")
            _host(url)
            prior = db.execute(
                "SELECT * FROM fulltext_jobs WHERE doc_id=?", (doc_id,)
            ).fetchone()
            if prior and prior["pdf_url"] == url and prior["source_license"] == license_name:
                if prior["status"] == "parsed":
                    return self.status(doc_id)
                if prior["status"] in {"downloading", "parsing"} and prior["lease_expires"]:
                    if prior["lease_expires"] > utc_now():
                        raise PatentWorkflowError("论文 PDF 任务已被其他执行者领取。")
            db.execute(
                "INSERT INTO fulltext_jobs(doc_id,pdf_url,source_license,rights_actor,"
                "rights_reference,status,last_updated) VALUES(?,?,?,?,?,?,?)"
                " ON CONFLICT(doc_id) DO UPDATE SET "
                "pdf_url=excluded.pdf_url,source_license=excluded.source_license,"
                "rights_actor=excluded.rights_actor,rights_reference=excluded.rights_reference,"
                "status='queued',attempts=0,lease_owner='',lease_expires=NULL,"
                "pdf_sha256='',pdf_path='',parse_sha256='',parse_path='',error='',"
                "last_updated=excluded.last_updated",
                (doc_id, url, license_name, actor, reference, "queued", utc_now()),
            )
            self._event(db, doc_id, "queued", actor, "开放许可来源已记录；PDF 尚未下载。")
        return self.status(doc_id)

    def _claim(self, doc_id: str) -> tuple[dict[str, Any], str]:
        owner = uuid4().hex
        expiry = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(timespec="seconds")
        with self.memory.connect(write=True) as db:
            job = db.execute(
                "SELECT * FROM fulltext_jobs WHERE doc_id=?", (doc_id,)
            ).fetchone()
            if job is None:
                raise PatentWorkflowError("请先登记论文 PDF 许可及任务。")
            # 实际执行前重新检查最新来源/许可，阻断许可撤回和 PDF URL 替换。
            source = db.execute(
                "SELECT kind,pdf_url,metadata_json FROM documents WHERE doc_id=?",
                (doc_id,),
            ).fetchone()
            if source is None or source["kind"] != "paper":
                raise PatentWorkflowError("论文记录已变更，全文任务必须重新审批。")
            source_meta = json.loads(source["metadata_json"] or "{}")
            if (source_meta.get("is_open_access") is not True
                    or not _licensed(str(source_meta.get("license") or ""))
                    or source["pdf_url"] != job["pdf_url"]
                    or str(source_meta.get("license") or "") != job["source_license"]):
                raise PatentWorkflowError("OA 来源、地址或许可证已改变，禁止使用旧授权下载。")
            if job["status"] == "parsed":
                return dict(job), ""
            if job["status"] in {"downloading", "parsing"} and (
                job["lease_expires"] or ""
            ) > utc_now():
                raise PatentWorkflowError("全文任务在有效租约内，禁止并发抢占。")
            if int(job["attempts"]) >= 3:
                raise PatentWorkflowError("达到失败重试次数上限；需人工排查后重新授权。")
            new_status = "parsing" if job["pdf_sha256"] and job["pdf_path"] else "downloading"
            db.execute(
                "UPDATE fulltext_jobs SET status=?,attempts=attempts+1,"
                "lease_owner=?,lease_expires=?,error='',last_updated=? WHERE doc_id=?",
                (new_status, owner, expiry, utc_now(), doc_id),
            )
            self._event(db, doc_id, "claimed", owner, new_status)
        result = self.status(doc_id)
        return result, owner

    def _update(self, doc_id: str, owner: str, *, status: str,
                fields: dict[str, str] | None = None, error: str = "") -> None:
        allowed = {"pdf_sha256", "pdf_path", "parse_sha256", "parse_path"}
        supplied = fields or {}
        if set(supplied) - allowed:
            raise PatentWorkflowError("不受支持的全文状态字段。")
        clauses = ["status=?", "error=?", "last_updated=?"]
        values: list[Any] = [status, error[:700], utc_now()]
        for key, value in supplied.items():
            clauses.append(key + "=?")
            values.append(value)
        if status in {"parsed", "downloaded", "failed"}:
            clauses.extend(["lease_owner=''", "lease_expires=NULL"])
        with self.memory.connect(write=True) as db:
            result = db.execute(
                "UPDATE fulltext_jobs SET " + ",".join(clauses)
                + " WHERE doc_id=? AND lease_owner=?",
                (*values, doc_id, owner),
            )
            if result.rowcount != 1:
                raise PatentWorkflowError("任务租约已失效，结果未写入数据库。")
            self._event(db, doc_id, status, owner, error)
            
    def _safe_local(self, relative: str, digest: str) -> Path:
        path = (self.memory.root / relative).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise PatentWorkflowError("本地 PDF 文件路径超出当前项目。")
        if path.is_symlink() or not path.is_file() or not _HASH.fullmatch(digest):
            raise PatentWorkflowError("已归档原文路径或哈希无效。")
        if _sha_file(path) != digest:
            raise PatentWorkflowError("本地 PDF 已发生内容变化，拒绝复用。")
        return path

    def process(self, doc_id: str, *, allowed_hosts: set[str],
                authorized: bool, artifacts: Path | None = None,
                parse: bool = True, max_bytes: int = MAX_PDF_BYTES,
                downloader: Callable[..., dict[str, Any]] = download_pdf,
                parser: Callable[..., dict[str, Any]] = parse_local_pdf,
                converter: Any | None = None) -> dict[str, Any]:
        """执行一次可恢复处理：合法下载后可以选择离线 Docling 解析。"""
        if not authorized:
            raise PatentWorkflowError("未取得明确的 PDF 下载与本地解析授权。")
        if not 1_000 <= max_bytes <= MAX_PDF_BYTES:
            raise PatentWorkflowError("单文献 PDF 大小预算不合法。")
        job, owner = self._claim(doc_id)
        if not owner:  # 已完成同一版本的机器解析
            return self.status(doc_id)
        source = job["pdf_url"]
        try:
            host = _host(source)
            if host not in {x.lower().rstrip(".") for x in allowed_hosts}:
                raise PatentWorkflowError("PDF 来源域名未获得本轮下载白名单授权。")
            pdf_path: Path | None = None
            pdf_digest = job["pdf_sha256"]
            if pdf_digest and job["pdf_path"]:
                pdf_path = self._safe_local(job["pdf_path"], pdf_digest)
            else:
                dest = self.root / "pdfs"
                if dest.is_symlink():
                    raise PatentWorkflowError("PDF 存储目录不可为符号链接。")
                dest.mkdir(mode=0o700, parents=True, exist_ok=True)
                data = downloader(source, dest, allowed_hosts={host}, max_bytes=max_bytes)
                if data.get("online_url") != source or not _HASH.fullmatch(str(data.get("sha256", ""))):
                    raise PatentWorkflowError("下载来源及 PDF 哈希校验失败。")
                path = Path(str(data.get("local_pdf_path") or ""))
                if path.is_symlink() or not path.resolve().is_relative_to(dest.resolve()):
                    raise PatentWorkflowError("PDF 下载返回了项目目录外的文件。")
                if not path.is_file() or _sha_file(path) != data["sha256"]:
                    raise PatentWorkflowError("PDF 字节与下载哈希不一致。")
                pdf_path = path
                pdf_digest = data["sha256"]
                relative = str(path.resolve().relative_to(self.memory.root.resolve()))
                self._update(doc_id, owner, status="downloading", fields={
                    "pdf_sha256": pdf_digest, "pdf_path": relative,
                })
            if not parse:
                self._update(doc_id, owner, status="downloaded")
                return self.status(doc_id)
            # 单篇离线模型预置是强制项，绝不让 Docling 默默从外网拉权重。
            if converter is None and (artifacts is None or not Path(artifacts).is_dir()):
                raise PatentWorkflowError("离线 Docling 模型目录不存在，已保留合法下载的 PDF。")
            self._update(doc_id, owner, status="parsing")
            parsedir = self.root / "parsed"
            if parsedir.is_symlink():
                raise PatentWorkflowError("解析结果目录不可为符号链接。")
            parsedir.mkdir(mode=0o700, parents=True, exist_ok=True)
            output = parsedir / (doc_id + "-" + pdf_digest[:16] + ".json")
            if output.is_symlink():
                raise PatentWorkflowError("解析结果位置被符号链接替换，已阻断。")
            parser(pdf_path, output, authorized=True, source_url=source,
                   artifacts=artifacts, converter=converter)
            payload = json.loads(output.read_text(encoding="utf-8"))
            if payload.get("source_pdf_sha256") != pdf_digest or not isinstance(payload.get("blocks"), list):
                raise PatentWorkflowError("解析输出未与原始 PDF SHA256 建立一致性关联。")
            blocks = payload["blocks"]
            if not blocks or len(blocks) > 30000:
                raise PatentWorkflowError("全文解析没有可索引段落或超过段落数量上限。")
            parse_digest = _sha_file(output)
            self._save_passages(doc_id, blocks, pdf_digest)
            # 自动生成的解析索引独立标注出处和人工核查缺口。
            self._add_machine_note(doc_id, source, pdf_digest, parse_digest, blocks, output)
            self._update(doc_id, owner, status="parsed", fields={
                "parse_sha256": parse_digest,
                "parse_path": str(output.relative_to(self.memory.root)),
            })
            return self.status(doc_id)
        except Exception as exc:
            # 下载成功但解析失败时可直接复用带哈希的 PDF。
            with self.memory.connect(write=True) as db:
                active = db.execute(
                    "SELECT pdf_sha256,pdf_path FROM fulltext_jobs WHERE doc_id=? "
                    "AND lease_owner=?", (doc_id, owner),
                ).fetchone()
            if active:
                stage = "downloaded" if active["pdf_sha256"] and active["pdf_path"] else "failed"
                self._update(doc_id, owner, status=stage, error=str(exc))
            if isinstance(exc, PatentWorkflowError):
                raise
            raise PatentWorkflowError("论文全文获取或离线解析失败，已记录可恢复状态。") from exc

    def _save_passages(self, doc_id: str, blocks: list[dict[str, Any]], pdf_sha: str) -> None:
        with self.memory.connect(write=True) as db:
            db.execute("DELETE FROM fulltext_blocks WHERE doc_id=?", (doc_id,))
            fts = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fulltext_blocks_fts'"
            ).fetchone()
            if fts:
                db.execute("DELETE FROM fulltext_blocks_fts WHERE doc_id=?", (doc_id,))
            for index, block in enumerate(blocks, start=1):
                body = str(block.get("text") or "")[:10000].strip()
                if not body:
                    continue
                page = block.get("page")
                page = page if type(page) is int and page > 0 else None
                label = str(block.get("label") or "text")[:60]
                db.execute(
                    "INSERT INTO fulltext_blocks(doc_id,block_no,page_no,label,content,source_pdf_sha256)"
                    " VALUES(?,?,?,?,?,?)",
                    (doc_id, index, page, label, body, pdf_sha),
                )
                if fts:
                    db.execute(
                        "INSERT INTO fulltext_blocks_fts(doc_id,block_no,content) VALUES(?,?,?)",
                        (doc_id, index, body),
                    )

    def _add_machine_note(self, doc_id: str, source: str, pdf_sha: str,
                          parse_sha: str, blocks: list[dict[str, Any]], output: Path) -> None:
        tag = "<!-- PDF-PARSE:" + parse_sha + " -->"
        with self.memory.connect(write=True) as db:
            row = db.execute(
                "SELECT kind,note_path FROM documents WHERE doc_id=?", (doc_id,)
            ).fetchone()
            if row is None or row["kind"] != "paper":
                raise PatentWorkflowError("解析文献与知识库身份不匹配。")
            note = self.memory._note_path(doc_id, row["kind"])
            if note.is_symlink():
                raise PatentWorkflowError("文献记忆文件不可为符号链接。")
            old = note.read_text(encoding="utf-8")
            if tag in old:
                return
            sample = [
                "- 第" + str(x.get("page") or "?") + "页，第" + str(x.get("block") or "?")
                + "块：" + _safe_markdown(str(x.get("text") or ""), 250)
                for x in blocks[:8]
            ]
            entry = (
                "\n\n" + tag + "\n\n## 机器 PDF 解析索引（未作人工核验）\n\n"
                + "- 源 PDF：" + _safe_markdown(source, 1500) + "\n"
                + "- PDF SHA-256：" + pdf_sha + "\n"
                + "- 解析结果 SHA-256：" + parse_sha + "\n"
                + "- 结构化段落：" + str(len(blocks)) + "\n"
                + "- 解析 JSON：" + str(output.relative_to(self.memory.root)) + "\n"
                + "- 证据状态：awaiting_original_pdf_review\n\n"
                + "### 带页码的样本片段\n\n" + "\n".join(sample) + "\n\n"
                + "该内容是 Docling 自动抽取的定位线索，技术事实仍需原始 PDF 复核。\n"
            )
            if len(old) + len(entry) > MAX_NOTES:
                raise PatentWorkflowError("研究记忆超过单篇大小预算。")
            _atomic_text(note, old + entry)
            self.memory._index_fts(db, doc_id, body=old + entry)

    def pending(self, *, limit: int = 30) -> list[dict[str, Any]]:
        """只返回有界任务状态；避免向 AI 一次输入整篇论文和原始 PDF。"""
        count = max(1, min(int(limit), 200))
        with self.memory.connect() as db:
            rows = db.execute(
                "SELECT doc_id,status,attempts,last_updated,error "
                "FROM fulltext_jobs WHERE status!='parsed' "
                "ORDER BY last_updated,doc_id LIMIT ?", (count,),
            ).fetchall()
        return [dict(row) for row in rows]


    def validate_positions(
        self, doc_id: str, positions: list[str],
    ) -> dict[str, Any]:
        """确认每个页码/块都属于此案卷当前完成的 PDF 解析版本。

        只验证结构化解析索引，不代表原始 PDF 已经人工核对。
        不允许没有页码的块作为 full_text 研究批注依据。
        """
        if not isinstance(doc_id, str) or not _PDF_DOC.fullmatch(doc_id):
            raise PatentWorkflowError("文献 ID 无效。")
        if not isinstance(positions, list) or not 1 <= len(positions) <= 30:
            raise PatentWorkflowError("全文研究批注必须提供1至30个页码段落锚点。")
        anchors = []
        for anchor in positions:
            match = re.fullmatch(r"p([1-9][0-9]{0,3}):b([1-9][0-9]{0,6})", anchor) if isinstance(anchor, str) else None
            if match is None:
                raise PatentWorkflowError("引用必须使用当前文献真实的 p2:b7 页码和段落编号。")
            anchors.append((int(match.group(1)), int(match.group(2))))
        with self.memory.connect() as db:
            job = db.execute(
                "SELECT status,pdf_sha256,parse_sha256,pdf_url FROM fulltext_jobs "
                "WHERE doc_id=?", (doc_id,),
            ).fetchone()
            if (job is None or job["status"] != "parsed"
                    or not _HASH.fullmatch(job["pdf_sha256"])
                    or not _HASH.fullmatch(job["parse_sha256"])):
                raise PatentWorkflowError("当前文献尚无完成的真实 PDF 解析版本。")
            for page, block in anchors:
                row = db.execute(
                    "SELECT page_no,source_pdf_sha256 FROM fulltext_blocks "
                    "WHERE doc_id=? AND block_no=?",
                    (doc_id, block),
                ).fetchone()
                if (row is None or row["page_no"] != page
                        or row["source_pdf_sha256"] != job["pdf_sha256"]):
                    raise PatentWorkflowError("引用页码或段落在当前 PDF 解析版本中不存在。")
        return {
            "doc_id": doc_id, "anchors": list(positions),
            "pdf_sha256": job["pdf_sha256"],
            "parse_sha256": job["parse_sha256"],
            "source_url": job["pdf_url"],
            "verification_level": "parsed_text_anchor_only",
            "full_text_verified": False,
        }

    def quote(self, doc_id: str, anchor: str, verbatim: str) -> dict[str, Any]:
        """逐字查证已解析段落中的短引，不代替人类对原始 PDF 的审核。"""
        evidence = self.validate_positions(doc_id, [anchor])
        if (not isinstance(verbatim, str)
                or not 3 <= len(verbatim) <= 1000
                or not verbatim.strip()):
            raise PatentWorkflowError("短引应为3至1000个实际原文字符。")
        block_no = int(anchor.split(":b", 1)[1])
        with self.memory.connect() as db:
            row = db.execute(
                "SELECT content,source_pdf_sha256 FROM fulltext_blocks "
                "WHERE doc_id=? AND block_no=?",
                (doc_id, block_no),
            ).fetchone()
            if row is None or row["source_pdf_sha256"] != evidence["pdf_sha256"]:
                raise PatentWorkflowError("原文解析版本已更新，请重新定位引文。")
        exact = verbatim in row["content"]
        return {
            **evidence, "anchor": anchor, "exact_match": exact,
            "block_sha256": sha256(row["content"].encode("utf-8")).hexdigest(),
            "quote_sha256": sha256(verbatim.encode("utf-8")).hexdigest() if exact else None,
            "verification_level": "parsed_text_match_only",
        }

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """按正文页码/段落检索，返回可验证的 PDF SHA 与明确的未核验状态。"""
        term = str(query or "").strip()[:160]
        if not term:
            raise PatentWorkflowError("全文索引检索词不能为空。")
        count = max(1, min(int(limit), 100))
        with self.memory.connect() as db:
            fts = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fulltext_blocks_fts'"
            ).fetchone()
            if fts and len(term) >= 3:
                try:
                    rows = db.execute(
                        "SELECT b.doc_id,b.block_no,b.page_no,b.label,b.content,"
                        "b.source_pdf_sha256 FROM fulltext_blocks_fts "
                        "JOIN fulltext_blocks b ON b.doc_id=fulltext_blocks_fts.doc_id "
                        "AND b.block_no=fulltext_blocks_fts.block_no "
                        "WHERE fulltext_blocks_fts MATCH ? ORDER BY b.doc_id,b.page_no,b.block_no LIMIT ?",
                        ('"' + term.replace('"', '""') + '"', count),
                    ).fetchall()
                    return [dict(x) | {"review_status": "awaiting_original_pdf_review"} for x in rows]
                except sqlite3.OperationalError:
                    pass
            escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            rows = db.execute(
                "SELECT doc_id,block_no,page_no,label,content,source_pdf_sha256 "
                "FROM fulltext_blocks WHERE content LIKE ? ESCAPE '\\' "
                "ORDER BY doc_id,page_no,block_no LIMIT ?", ("%" + escaped + "%", count),
            ).fetchall()
            return [dict(x) | {"review_status": "awaiting_original_pdf_review"} for x in rows]
