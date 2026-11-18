"""项目级已授权论文 PDF 全文处理：隔离、审计、逐页可检索的原文证据。

仅使用现有受审查的 PDF HTTPS 下载器以及离线 Docling；不开启自发爬虫。
已解析与已被专业人员核验是两种独立状态。
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any, Callable

from .core import PatentWorkflowError, utc_now
from .literature_memory import LiteratureMemoryStore
from .pdf_archive import MAX_PDF_BYTES, download_pdf
from .pdf_extraction import parse_local_pdf

_DOC_ID = re.compile(r"EV-[A-F0-9]{12}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
# 明确记录可审查的授权基础。免费可读或 PDF URL 本身不代表可归档。
RIGHTS_BASES = frozenset({
    "cc0", "cc-by", "cc-by-sa", "public-domain",
    "written-permission", "institutional-license",
})
MAX_BLOCK_CHARS = 10000
MAX_BLOCKS = 30000


def _atomic_copy_pdf(source: Path, target_dir: Path) -> dict[str, Any]:
    """只读本地普通 PDF 并按 SHA256 内容寻址；拒绝符号链接。"""
    source = Path(source)
    if source.is_symlink() or not source.is_file() or source.suffix.lower() != ".pdf":
        raise PatentWorkflowError("只允许导入已审核的本地非符号链接 PDF。")
    size = source.stat().st_size
    if size < 5 or size > MAX_PDF_BYTES:
        raise PatentWorkflowError("本地 PDF 大小超出允许范围（最大 40 MiB）。")
    target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target_dir.is_symlink():
        raise PatentWorkflowError("PDF 目标目录禁止符号链接。")
    name = ""
    digest = sha256()
    try:
        # O_NOFOLLOW blocks last-component symlinks; seekable local file only.
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(source, flags)
        try:
            with os.fdopen(fd, "rb") as reader, tempfile.NamedTemporaryFile(
                dir=target_dir, prefix=".pdf-stage-", suffix=".tmp", delete=False
            ) as writer:
                name = writer.name
                os.chmod(name, 0o600)
                prefix = reader.read(5)
                if prefix != b"%PDF-":
                    raise PatentWorkflowError("源文件 PDF 标识无效。")
                writer.write(prefix)
                digest.update(prefix)
                copied = 5
                while True:
                    chunk = reader.read(64 * 1024)
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > MAX_PDF_BYTES:
                        raise PatentWorkflowError("读取过程中 PDF 超出大小预算。")
                    writer.write(chunk)
                    digest.update(chunk)
                if copied != size:
                    raise PatentWorkflowError("文件在导入时发生变更；已中止。")
                writer.flush()
                os.fsync(writer.fileno())
        except BaseException:
            # fdopen owns fd once constructed.
            raise
        fingerprint = digest.hexdigest()
        target = target_dir / (fingerprint + ".pdf")
        if target.is_symlink():
            raise PatentWorkflowError("目标 PDF 不得为符号链接。")
        if target.exists():
            if target.stat().st_size != size or sha256(target.read_bytes()).hexdigest() != fingerprint:
                raise PatentWorkflowError("已有内容地址对象损坏。")
        else:
            os.replace(name, target)
            name = ""
        return {"path": str(target), "sha256": fingerprint, "bytes": size}
    except OSError as exc:
        raise PatentWorkflowError("无法读取或安全归档本地 PDF。") from exc
    finally:
        if name:
            Path(name).unlink(missing_ok=True)


class LiteratureFullText:
    """每个项目共享既有 LiteratureMemoryStore 的 SQLite，页码证据单独索引。"""

    def __init__(self, memory: LiteratureMemoryStore):
        self.memory = memory
        self.root = memory.root / "fulltext"
        if self.root.is_symlink():
            raise PatentWorkflowError("全文资料目录禁止符号链接。")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with memory.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS fulltext_documents (
                  doc_id TEXT PRIMARY KEY REFERENCES documents(doc_id),
                  pdf_sha256 TEXT NOT NULL,
                  pdf_relpath TEXT NOT NULL,
                  source_url TEXT NOT NULL,
                  rights_basis TEXT NOT NULL,
                  rights_reference TEXT NOT NULL,
                  state TEXT NOT NULL,
                  parser TEXT NOT NULL DEFAULT '',
                  parser_version TEXT NOT NULL DEFAULT '',
                  parsed_relpath TEXT NOT NULL DEFAULT '',
                  block_count INTEGER NOT NULL DEFAULT 0,
                  page_count INTEGER NOT NULL DEFAULT 0,
                  last_error TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fulltext_blocks (
                  doc_id TEXT NOT NULL REFERENCES documents(doc_id),
                  pdf_sha256 TEXT NOT NULL,
                  block_no INTEGER NOT NULL,
                  page_no INTEGER,
                  label TEXT NOT NULL,
                  text TEXT NOT NULL,
                  bbox_json TEXT NOT NULL,
                  PRIMARY KEY(doc_id, block_no)
                );
                CREATE INDEX IF NOT EXISTS idx_fulltext_pages
                  ON fulltext_blocks(doc_id, page_no, block_no);
            """)
            try:
                db.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS fulltext_fts USING fts5("
                    "doc_id UNINDEXED, block_no UNINDEXED, text, tokenize='trigram')"
                )
            except sqlite3.OperationalError:
                # 兼容没有 trigram 的精简 SQLite 构建：LIKE 路径仍可使用。
                pass

    @staticmethod
    def _validate_rights(*, authorized: bool, rights_basis: str, rights_reference: str) -> None:
        if not authorized:
            raise PatentWorkflowError("保存或解析论文全文必须得到明确资料使用授权。")
        if rights_basis not in RIGHTS_BASES:
            raise PatentWorkflowError("全文许可基础无效；开放获取不等于可复制的许可。")
        if not isinstance(rights_reference, str) or not 8 <= len(rights_reference.strip()) <= 1000:
            raise PatentWorkflowError("必须记录可复查的许可证链接或机构授权记录。")

    def _source(self, doc_id: str) -> dict[str, Any]:
        if not isinstance(doc_id, str) or not _DOC_ID.fullmatch(doc_id):
            raise PatentWorkflowError("无效的文献证据编号。")
        with self.memory.connect() as db:
            row = db.execute(
                "SELECT doc_id,kind,publication,source_url,pdf_url,paper_metadata_json "
                "FROM documents WHERE doc_id=?", (doc_id,),
            ).fetchone()
        if row is None or row["kind"] != "paper":
            raise PatentWorkflowError("项目内找不到指定论文文献。")
        out = dict(row)
        out["paper_metadata"] = json.loads(out.pop("paper_metadata_json") or "{}")
        return out

    def _relative(self, path: Path) -> str:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise PatentWorkflowError("全文对象必须保存在本项目隔离存储中。")
        return str(resolved.relative_to(self.root))

    def _local(self, relative: str) -> Path:
        if not relative:
            raise PatentWorkflowError("全文存储对象路径为空。")
        path = self.root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(self.root.resolve()):
            raise PatentWorkflowError("全文对象路径非法或越界。")
        return path

    def _register(
        self, doc_id: str, pdf: dict[str, Any], *, source_url: str,
        rights_basis: str, rights_reference: str,
    ) -> dict[str, Any]:
        if not _SHA.fullmatch(str(pdf["sha256"])):
            raise PatentWorkflowError("PDF 校验和错误。")
        relative = self._relative(Path(pdf["path"]))
        now = utc_now()
        with self.memory.connect(write=True) as db:
            old = db.execute(
                "SELECT pdf_sha256 FROM fulltext_documents WHERE doc_id=?", (doc_id,),
            ).fetchone()
            if old and old["pdf_sha256"] != pdf["sha256"]:
                db.execute("DELETE FROM fulltext_blocks WHERE doc_id=?", (doc_id,))
                if self._fts_enabled(db):
                    db.execute("DELETE FROM fulltext_fts WHERE doc_id=?", (doc_id,))
            same = old is not None and old["pdf_sha256"] == pdf["sha256"]
            db.execute(
                "INSERT INTO fulltext_documents (doc_id,pdf_sha256,pdf_relpath,source_url,"
                "rights_basis,rights_reference,state,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(doc_id) DO UPDATE SET "
                "pdf_sha256=excluded.pdf_sha256,pdf_relpath=excluded.pdf_relpath,"
                "source_url=excluded.source_url,rights_basis=excluded.rights_basis,"
                "rights_reference=excluded.rights_reference,"
                "state=CASE WHEN fulltext_documents.pdf_sha256=excluded.pdf_sha256 "
                "THEN fulltext_documents.state ELSE 'staged' END,"
                "parser=CASE WHEN fulltext_documents.pdf_sha256=excluded.pdf_sha256 "
                "THEN fulltext_documents.parser ELSE '' END,"
                "parser_version=CASE WHEN fulltext_documents.pdf_sha256=excluded.pdf_sha256 "
                "THEN fulltext_documents.parser_version ELSE '' END,"
                "parsed_relpath=CASE WHEN fulltext_documents.pdf_sha256=excluded.pdf_sha256 "
                "THEN fulltext_documents.parsed_relpath ELSE '' END,"
                "block_count=CASE WHEN fulltext_documents.pdf_sha256=excluded.pdf_sha256 "
                "THEN fulltext_documents.block_count ELSE 0 END,"
                "page_count=CASE WHEN fulltext_documents.pdf_sha256=excluded.pdf_sha256 "
                "THEN fulltext_documents.page_count ELSE 0 END,"
                "last_error='',updated_at=excluded.updated_at",
                (doc_id, pdf["sha256"], relative, source_url,
                 rights_basis, rights_reference, "staged", now, now),
            )
        status = self.status(doc_id)
        status["reused_existing_pdf"] = bool(same)
        return status

    def import_local(
        self, doc_id: str, pdf_path: Path, *, authorized: bool,
        rights_basis: str, rights_reference: str, source_url: str = "",
    ) -> dict[str, Any]:
        """经授权的本地已持有 PDF 导入；不会访问外网。"""
        self._validate_rights(
            authorized=authorized, rights_basis=rights_basis, rights_reference=rights_reference
        )
        document = self._source(doc_id)
        if source_url and not source_url.startswith("https://"):
            raise PatentWorkflowError("原文在线出处必须是 HTTPS URL。")
        pdf = _atomic_copy_pdf(Path(pdf_path), self.root / "pdfs")
        return self._register(
            doc_id, pdf, source_url=source_url or document["source_url"],
            rights_basis=rights_basis, rights_reference=rights_reference,
        )

    def fetch(
        self, doc_id: str, *, allowed_hosts: set[str], authorized: bool,
        rights_basis: str, rights_reference: str,
        outbound_approved: bool, download: Callable[..., dict[str, Any]] = download_pdf,
        max_bytes: int = MAX_PDF_BYTES,
    ) -> dict[str, Any]:
        """仅下载当前文献原有元数据里的确切 PDF URL，禁用任意用户传 URL。"""
        self._validate_rights(
            authorized=authorized, rights_basis=rights_basis, rights_reference=rights_reference
        )
        if not outbound_approved:
            raise PatentWorkflowError("论文下载必须通过该案卷本轮网络外发审批。")
        record = self._source(doc_id)
        url = record["pdf_url"]
        if not url:
            raise PatentWorkflowError("该论文没有供应商提供的候选 PDF 地址。")
        if not allowed_hosts:
            raise PatentWorkflowError("必须显式指定获准的 PDF 来源域名白名单。")
        result = download(
            url, self.root / "pdfs", allowed_hosts=set(allowed_hosts),
            max_bytes=max_bytes,
        )
        pdf = {
            "path": result["local_pdf_path"],
            "sha256": result["sha256"],
            "bytes": result["bytes"],
        }
        return self._register(
            doc_id, pdf, source_url=url,
            rights_basis=rights_basis, rights_reference=rights_reference,
        )

    def status(self, doc_id: str) -> dict[str, Any]:
        self._source(doc_id)
        with self.memory.connect() as db:
            row = db.execute(
                "SELECT * FROM fulltext_documents WHERE doc_id=?", (doc_id,),
            ).fetchone()
        if row is None:
            return {"doc_id": doc_id, "state": "not_available",
                    "full_text_verified": False}
        result = dict(row)
        # 仅返回相对路径，不向 MCP 客户端泄露宿主磁盘位置。
        result["full_text_verified"] = False
        return result

    @staticmethod
    def _fts_enabled(db: sqlite3.Connection) -> bool:
        return db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fulltext_fts'"
        ).fetchone() is not None

    def parse(
        self, doc_id: str, *, authorized: bool, artifacts: Path | None = None,
        converter: Any | None = None, max_pages: int = 200,
    ) -> dict[str, Any]:
        """离线解析已有 PDF。原始 PDF、许可和摘要均不被更改。"""
        if not authorized:
            raise PatentWorkflowError("全文结构化解析需要已批准的本地处理授权。")
        existing = self.status(doc_id)
        if existing["state"] == "not_available":
            raise PatentWorkflowError("需要先合法导入或获取原始论文 PDF。")
        source = self._local(existing["pdf_relpath"])
        if not source.is_file() or source.suffix != ".pdf":
            raise PatentWorkflowError("归档 PDF 缺失。")
        checksum = sha256(source.read_bytes()).hexdigest()
        if checksum != existing["pdf_sha256"]:
            raise PatentWorkflowError("原始 PDF 哈希变化，阻断下游解析。")
        out = self.root / "parsed" / (doc_id + "-" + checksum + ".json")
        out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            parsed = parse_local_pdf(
                source, out, authorized=True, source_url=existing["source_url"],
                artifacts=artifacts, converter=converter, max_pages=max_pages,
            )
            payload = json.loads(out.read_text(encoding="utf-8"))
            if payload.get("source_pdf_sha256") != checksum:
                raise PatentWorkflowError("Docling 结果与原始 PDF SHA256 不匹配。")
            blocks = payload.get("blocks", [])
            if not isinstance(blocks, list) or not 1 <= len(blocks) <= MAX_BLOCKS:
                raise PatentWorkflowError("解析结果没有可索引的有效原文段落。")
            rows = []
            for i, item in enumerate(blocks, 1):
                if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                    raise PatentWorkflowError("PDF 段落记录格式无效。")
                if not item["text"].strip():
                    continue
                if len(item["text"]) > MAX_BLOCK_CHARS:
                    raise PatentWorkflowError("原文段落超出安全长度。")
                page = item.get("page")
                if page is not None and (type(page) is not int or not 1 <= page <= max_pages):
                    raise PatentWorkflowError("页面定位超出本次 PDF 页数范围。")
                bbox = item.get("bbox")
                if bbox is not None and not isinstance(bbox, dict):
                    raise PatentWorkflowError("PDF 原文坐标无效。")
                rows.append((
                    doc_id, checksum, i, page,
                    str(item.get("label") or "text")[:100],
                    item["text"], json.dumps(bbox or {}, ensure_ascii=False),
                ))
            if not rows:
                raise PatentWorkflowError("PDF 没有可用的原文段落。")
            with self.memory.connect(write=True) as db:
                current = db.execute(
                    "SELECT pdf_sha256 FROM fulltext_documents WHERE doc_id=?", (doc_id,),
                ).fetchone()
                if current is None or current["pdf_sha256"] != checksum:
                    raise PatentWorkflowError("解析期间原始文件版本发生变化。")
                db.execute("DELETE FROM fulltext_blocks WHERE doc_id=?", (doc_id,))
                db.executemany(
                    "INSERT INTO fulltext_blocks(doc_id,pdf_sha256,block_no,page_no,label,text,bbox_json)"
                    " VALUES(?,?,?,?,?,?,?)", rows,
                )
                if self._fts_enabled(db):
                    db.execute("DELETE FROM fulltext_fts WHERE doc_id=?", (doc_id,))
                    db.executemany(
                        "INSERT INTO fulltext_fts(doc_id,block_no,text) VALUES(?,?,?)",
                        [(r[0], r[2], r[5]) for r in rows],
                    )
                db.execute(
                    "UPDATE fulltext_documents SET state='parsed_unreviewed',parser=?,"
                    "parser_version=?,parsed_relpath=?,block_count=?,page_count=?,"
                    "last_error='',updated_at=? WHERE doc_id=?",
                    (str(payload.get("parser") or "docling"),
                     str(payload.get("parser_version") or "unknown"),
                     self._relative(out), len(rows),
                     len({r[3] for r in rows if r[3] is not None}),
                     utc_now(), doc_id),
                )
        except Exception as exc:
            # 保存上一版成功索引；失败不会删除可能已接受的人类研究批注。
            with self.memory.connect(write=True) as db:
                db.execute(
                    "UPDATE fulltext_documents SET last_error=?,updated_at=? WHERE doc_id=?",
                    (str(exc)[:350], utc_now(), doc_id),
                )
            raise
        result = self.status(doc_id)
        result["parser_report"] = parsed
        return result

    def search(
        self, term: str, *, doc_id: str | None = None, limit: int = 20,
    ) -> list[dict[str, Any]]:
        if not isinstance(term, str) or not term.strip() or len(term) > 160:
            raise PatentWorkflowError("全文检索词不能为空或超过160字符。")
        if doc_id is not None:
            self._source(doc_id)
        limit = max(1, min(int(limit), 100))
        escaped = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self.memory.connect() as db:
            rows = []
            if len(term.strip()) >= 3 and self._fts_enabled(db):
                try:
                    sql = (
                        "SELECT b.doc_id,b.block_no,b.page_no,b.label,b.text,b.bbox_json,"
                        "b.pdf_sha256,d.publication,d.title FROM fulltext_fts f "
                        "JOIN fulltext_blocks b ON b.doc_id=f.doc_id AND b.block_no=f.block_no "
                        "JOIN documents d ON d.doc_id=b.doc_id "
                        "WHERE f.text MATCH ?"
                    )
                    args: list[Any] = ['"' + term.strip().replace('"', '""') + '"']
                    if doc_id:
                        sql += " AND b.doc_id=?"
                        args.append(doc_id)
                    rows = db.execute(sql + " LIMIT ?", [*args, limit]).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            if not rows:
                sql = (
                    "SELECT b.doc_id,b.block_no,b.page_no,b.label,b.text,b.bbox_json,"
                    "b.pdf_sha256,d.publication,d.title FROM fulltext_blocks b "
                    "JOIN documents d ON d.doc_id=b.doc_id "
                    "WHERE b.text LIKE ? ESCAPE '\\'"
                )
                args = ["%" + escaped + "%"]
                if doc_id:
                    sql += " AND b.doc_id=?"
                    args.append(doc_id)
                rows = db.execute(
                    sql + " ORDER BY b.doc_id,b.page_no,b.block_no LIMIT ?", [*args, limit],
                ).fetchall()
            return [
                {
                    "doc_id": r["doc_id"], "publication": r["publication"], "title": r["title"],
                    "page": r["page_no"], "block": r["block_no"], "label": r["label"],
                    "text": r["text"][:2500], "bbox": json.loads(r["bbox_json"]),
                    "pdf_sha256": r["pdf_sha256"],
                    "review_status": "awaiting_original_pdf_review",
                }
                for r in rows
            ]

    def page(self, doc_id: str, page: int, *, limit: int = 100) -> dict[str, Any]:
        self._source(doc_id)
        if type(page) is not int or page < 1 or page > 600:
            raise PatentWorkflowError("需要有效的 PDF 页码（1-600）。")
        limit = max(1, min(int(limit), 300))
        with self.memory.connect() as db:
            rows = db.execute(
                "SELECT block_no,label,text,bbox_json,pdf_sha256 FROM fulltext_blocks "
                "WHERE doc_id=? AND page_no=? ORDER BY block_no LIMIT ?",
                (doc_id, page, limit),
            ).fetchall()
        return {
            "doc_id": doc_id, "page": page,
            "blocks": [{"block": r["block_no"], "label": r["label"],
                        "text": r["text"], "bbox": json.loads(r["bbox_json"]),
                        "pdf_sha256": r["pdf_sha256"]} for r in rows],
            "review_status": "awaiting_original_pdf_review",
        }
