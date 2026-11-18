"""项目隔离的学术 PDF 获取—离线解析—页码证据链。

无 LLM 或隐式模型下载；HTTP 下载复用原有 DNS 钉扎/TLS/不跟随重定向。
PDF 访问和解析需要独立明确审批，状态为机器提取、待原文核验。
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Callable

from .core import PatentWorkflowError, utc_now
from .literature_memory import LiteratureMemoryStore
from .pdf_archive import MAX_PDF_BYTES, download_pdf
from .pdf_extraction import parse_local_pdf

RIGHTS_BASES = frozenset({"open_license", "public_domain", "rightsholder_permission"})
RUNNING = frozenset({"downloading", "parsing"})
SHA_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
DOC_PATTERN = re.compile(r"EV-[A-F0-9]{12}\Z")


class PaperFullTextService:
    """可恢复逐篇证据处理；以一个项目的私有 SQLite 和内容寻址文件为唯一状态。"""

    def __init__(self, memory: LiteratureMemoryStore, *,
                 downloader: Callable[..., dict[str, Any]] = download_pdf,
                 parser: Callable[..., dict[str, Any]] = parse_local_pdf):
        self.memory = memory
        self.download_impl = downloader
        self.parse_impl = parser
        self.pdf_root = memory.root / "pdf_objects"
        self.parse_root = memory.root / "pdf_extracted"
        for folder in (self.pdf_root, self.parse_root):
            if folder.is_symlink() or not folder.resolve().is_relative_to(memory.root.resolve()):
                raise PatentWorkflowError("PDF 存储目录不得为符号链接或跨越项目空间。")
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        with memory.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS paper_fulltext (
                doc_id TEXT PRIMARY KEY REFERENCES documents(doc_id) ON DELETE CASCADE,
                pdf_url TEXT NOT NULL,
                rights_basis TEXT NOT NULL,
                rights_reference TEXT NOT NULL,
                state TEXT NOT NULL,
                pdf_sha256 TEXT NOT NULL DEFAULT '',
                pdf_local_path TEXT NOT NULL DEFAULT '',
                pdf_bytes INTEGER NOT NULL DEFAULT 0,
                parsed_json_path TEXT NOT NULL DEFAULT '',
                parsed_blocks INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")

    def _paper(self, doc_id: str) -> dict[str, Any]:
        if not isinstance(doc_id, str) or not DOC_PATTERN.fullmatch(doc_id):
            raise PatentWorkflowError("PDF 文献编号格式无效。")
        return self.memory.paper_source(doc_id)

    def _row(self, doc_id: str) -> dict[str, Any] | None:
        with self.memory.connect() as db:
            row = db.execute("SELECT * FROM paper_fulltext WHERE doc_id=?", (doc_id,)).fetchone()
        return dict(row) if row else None

    def _safe_object(self, original: str, *, expected_root: Path, suffix: str) -> Path:
        path = Path(original)
        if not original or path.is_symlink() or not path.is_file():
            raise PatentWorkflowError("已登记的 PDF/解析文件不存在或为符号链接。")
        if expected_root.is_symlink() or path.suffix != suffix or not path.resolve().is_relative_to(expected_root.resolve()):
            raise PatentWorkflowError("PDF/解析文件超出项目专属存储空间。")
        return path

    def _save(self, doc_id: str, state: str, *, claim: bool = False, **changes: Any) -> None:
        columns = {
            "pdf_url", "rights_basis", "rights_reference", "pdf_sha256",
            "pdf_local_path", "pdf_bytes", "parsed_json_path", "parsed_blocks", "last_error",
        }
        if set(changes) - columns:
            raise PatentWorkflowError("无效的 PDF 状态字段。")
        now = utc_now()
        with self.memory.connect(write=True) as db:
            existing = db.execute("SELECT * FROM paper_fulltext WHERE doc_id=?", (doc_id,)).fetchone()
            if claim and existing is not None:
                # Transactional check prevents two concurrent workers from claiming the same DOI.
                self._guard_busy(dict(existing))
            if existing:
                sets = ["state=?", "updated_at=?"] + [key + "=?" for key in changes]
                values = [state, now] + list(changes.values()) + [doc_id]
                db.execute("UPDATE paper_fulltext SET " + ",".join(sets) + " WHERE doc_id=?", values)
            else:
                required = {"pdf_url", "rights_basis", "rights_reference"}
                if not required.issubset(changes):
                    raise PatentWorkflowError("首次 PDF 操作缺少许可审计记录。")
                fields = ["doc_id", "state", "created_at", "updated_at", *changes]
                values = [doc_id, state, now, now, *changes.values()]
                db.execute("INSERT INTO paper_fulltext(" + ",".join(fields) + ") VALUES(" +
                           ",".join("?" for _ in fields) + ")", values)

    def status(self, doc_id: str) -> dict[str, Any]:
        paper = self._paper(doc_id)
        row = self._row(doc_id)
        if row is None:
            return {"doc_id": doc_id, "title": paper["title"],
                    "state": "not_downloaded", "pdf_url": paper["pdf_url"],
                    "full_text_verified": False}
        return {**row, "title": paper["title"], "full_text_verified": False,
                "note": "仅为机器下载和结构化提取状态，原文仍需独立核验。"}

    def _guard_busy(self, row: dict[str, Any] | None) -> None:
        if row and row["state"] in RUNNING:
            # Interrupted tasks may be recovered after a bounded lease.
            from datetime import datetime, timezone
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                    row["updated_at"])).total_seconds()
            except ValueError:
                age = 0
            if age < 1800:
                raise PatentWorkflowError("已有 PDF 下载或解析任务进行中，请通过状态接口确认后重试。")

    def download(
        self, doc_id: str, *, authorized: bool, allowed_hosts: set[str],
        rights_basis: str, rights_reference: str, max_bytes: int = MAX_PDF_BYTES,
        **test_transport: Any,
    ) -> dict[str, Any]:
        paper = self._paper(doc_id)
        if not authorized:
            raise PatentWorkflowError("公开 PDF 下载需要明确的企业/用户授权。")
        if rights_basis not in RIGHTS_BASES or len(rights_reference.strip()) < 8:
            raise PatentWorkflowError("PDF 归档需要记录可核查的合法使用依据与证明。")
        url = paper["pdf_url"]
        if not url:
            raise PatentWorkflowError("当前论文缺少开放 PDF 候选地址，需先补全 DOI 来源。")
        if not allowed_hosts or any(not h or "/" in h for h in allowed_hosts):
            raise PatentWorkflowError("PDF 下载必须显式列出已批准的来源域名。")
        current = self._row(doc_id)
        self._guard_busy(current)
        if current and current["pdf_url"] == url and (
            current["rights_basis"] != rights_basis
            or current["rights_reference"] != rights_reference.strip()[:1500]
        ):
            raise PatentWorkflowError("本 DOI 的归档权利依据与此前已登记记录不同，需要人工审计后重新批准。")
        if current and current["pdf_url"] == url and current["state"] in {
            "downloaded", "parsed_unverified", "parse_failed"
        }:
            try:
                path = self._safe_object(current["pdf_local_path"],
                                         expected_root=self.pdf_root, suffix=".pdf")
                if sha256(path.read_bytes()).hexdigest() == current["pdf_sha256"]:
                    return self.status(doc_id)
            except (OSError, PatentWorkflowError):
                pass
        self._save(doc_id, "downloading", claim=True, pdf_url=url, rights_basis=rights_basis,
                   rights_reference=rights_reference.strip()[:1500], last_error="")
        try:
            result = self.download_impl(
                url, self.pdf_root, allowed_hosts=set(allowed_hosts),
                max_bytes=max_bytes, **test_transport
            )
            target = self._safe_object(result["local_pdf_path"],
                                       expected_root=self.pdf_root, suffix=".pdf")
            digest = sha256(target.read_bytes()).hexdigest()
            if digest != result.get("sha256") or not SHA_PATTERN.fullmatch(digest):
                raise PatentWorkflowError("下载后的 PDF SHA256 与文件实际内容不一致。")
            self._save(doc_id, "downloaded", pdf_sha256=digest,
                       pdf_local_path=str(target), pdf_bytes=target.stat().st_size,
                       parsed_json_path="", parsed_blocks=0)
        except (PatentWorkflowError, OSError, KeyError, ValueError) as exc:
            self._save(doc_id, "download_failed", last_error=str(exc)[:300])
            raise PatentWorkflowError("学术 PDF 获取失败；已记录原因且保留已有文献索引。") from exc
        return self.status(doc_id)

    def parse(self, doc_id: str, *, authorized: bool,
              artifacts: Path | None = None, converter: Any | None = None,
              max_pages: int = 200) -> dict[str, Any]:
        self._paper(doc_id)
        if not authorized:
            raise PatentWorkflowError("离线解析 PDF 需要明确的处理授权。")
        current = self._row(doc_id)
        if not current:
            raise PatentWorkflowError("当前论文尚未下载，无法解析。")
        self._guard_busy(current)
        if current["state"] == "parsed_unverified":
            path = Path(current["parsed_json_path"])
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(self.parse_root.resolve()):
                return self.status(doc_id)
        if current["state"] not in {"downloaded", "parsed_unverified", "parse_failed"}:
            raise PatentWorkflowError("当前状态不允许解析；先取得合法 PDF 文件。")
        pdf = self._safe_object(current["pdf_local_path"], expected_root=self.pdf_root, suffix=".pdf")
        digest = sha256(pdf.read_bytes()).hexdigest()
        if digest != current["pdf_sha256"]:
            raise PatentWorkflowError("本地 PDF 校验失败，停止解析以防止证据被替换。")
        output = self.parse_root / (doc_id + "-" + digest + ".json")
        if output.is_symlink():
            raise PatentWorkflowError("PDF 解析结果路径被符号链接替换。")
        self._save(doc_id, "parsing", claim=True, last_error="")
        try:
            result = self.parse_impl(pdf, output, authorized=True,
                                     source_url=current["pdf_url"],
                                     artifacts=artifacts, converter=converter,
                                     max_pages=max_pages)
            blocks = int(result.get("blocks", 0))
            if blocks < 1:
                raise PatentWorkflowError("PDF 解析没有有效段落。")
            self._safe_object(str(output), expected_root=self.parse_root, suffix=".json")
            payload = json.loads(output.read_text(encoding="utf-8"))
            if payload.get("source_pdf_sha256") != digest:
                raise PatentWorkflowError("解析结果引用了不匹配的原始 PDF SHA256。")
            self.memory.write_machine_extraction(
                doc_id, pdf_sha256=digest, parsed_json_path=str(output),
                blocks=blocks, source_url=current["pdf_url"],
            )
            self._save(doc_id, "parsed_unverified", parsed_json_path=str(output),
                       parsed_blocks=blocks)
        except (PatentWorkflowError, OSError, KeyError, ValueError, RuntimeError) as exc:
            self._save(doc_id, "parse_failed", last_error=str(exc)[:300])
            raise PatentWorkflowError("本地 PDF 解析失败；原始 PDF 已保留，支持之后重试。") from exc
        return self.status(doc_id)

    def pages(self, doc_id: str, *, page: int, limit: int = 30) -> dict[str, Any]:
        self._paper(doc_id)
        row = self._row(doc_id)
        if row is None or row["state"] != "parsed_unverified":
            raise PatentWorkflowError("当前论文暂无可读取的机器页码证据。")
        path = self._safe_object(row["parsed_json_path"],
                                 expected_root=self.parse_root, suffix=".json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("source_pdf_sha256") != row["pdf_sha256"]:
            raise PatentWorkflowError("解析文件与已归档 PDF 证据哈希不匹配。")
        if not 1 <= int(page) <= 600 or not 1 <= int(limit) <= 60:
            raise PatentWorkflowError("页码或单次段落数量不合法。")
        rows = [x for x in payload.get("blocks", []) if x.get("page") == int(page)]
        return {
            "doc_id": doc_id, "page": int(page), "total_blocks_on_page": len(rows),
            "blocks": rows[:int(limit)], "source_pdf_sha256": row["pdf_sha256"],
            "review_status": "awaiting_original_pdf_review",
        }
