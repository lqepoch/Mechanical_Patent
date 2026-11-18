"""将已授权、实际存在的 PDF 与 Docling 页码 JSON 绑定至单案卷文献。

不联网下载，不调用语言模型。PDF SHA256 与解析 JSON 必须匹配；
所有段落可回溯到该 PDF、页码和 Docling block 序号。自动解析本身
不代表原文语义、版权、专利权利要求或工程结论已获人工核验。
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from typing import Any

from .core import PatentWorkflowError, save_json, utc_now
from .literature_memory import LiteratureMemoryStore
from .pdf_extraction import MAX_ITEMS, MAX_ITEM_LENGTH, MAX_PDF_BYTES, MAX_PAGES, MAX_TOTAL_CHARS

ID_PATTERN = re.compile(r"EV-[A-F0-9]{12}\Z")
ANCHOR_PATTERN = re.compile(r"p([1-9][0-9]{0,3}):b([1-9][0-9]{0,6})\Z")
SHA_PATTERN = re.compile(r"[a-f0-9]{64}\Z")
MAX_PARSED_BYTES = 18 * 1024 * 1024


def _within_case(path: Path, root: Path, *, extension: str) -> Path:
    item = Path(path)
    if item.is_symlink() or not item.is_file() or item.suffix.lower() != extension:
        raise PatentWorkflowError("只允许案卷内已有的、无符号链接的原始资料文件。")
    real = item.resolve()
    if not real.is_relative_to(root):
        raise PatentWorkflowError("原文路径超出当前案卷，拒绝跨项目读取。")
    return real


def _copy_immutable(src: Path, dst: Path) -> None:
    if dst.is_symlink() or dst.parent.is_symlink():
        raise PatentWorkflowError("证据归档路径禁止符号链接。")
    dst.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if dst.exists():
        return
    with tempfile.NamedTemporaryFile(dir=dst.parent, prefix=".pdf-copy-", delete=False) as tmp:
        temp = Path(tmp.name)
        os.chmod(temp, 0o600)
        try:
            with src.open("rb") as handle:
                shutil.copyfileobj(handle, tmp, 1024 * 1024)
            tmp.flush()
            os.fsync(tmp.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        temp.replace(dst)
    finally:
        temp.unlink(missing_ok=True)


class FullTextEvidence:
    """提供全文索引、精确原文短引核验和可审计的多版本证据。"""

    def __init__(self, memory: LiteratureMemoryStore):
        self.memory = memory
        self.root = memory.root / "fulltext"
        if self.root.is_symlink():
            raise PatentWorkflowError("全文证据目录不能为符号链接。")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with memory.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS fulltext_sources(
                  doc_id TEXT PRIMARY KEY REFERENCES documents(doc_id) ON DELETE CASCADE,
                  pdf_sha256 TEXT NOT NULL,
                  parsed_sha256 TEXT NOT NULL,
                  parser TEXT NOT NULL,
                  parser_version TEXT NOT NULL,
                  source_url TEXT NOT NULL,
                  blocks INTEGER NOT NULL,
                  review_status TEXT NOT NULL,
                  captured_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fulltext_blocks(
                  doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                  block INTEGER NOT NULL,
                  page INTEGER,
                  label TEXT NOT NULL,
                  body TEXT NOT NULL,
                  body_sha256 TEXT NOT NULL,
                  bbox_json TEXT NOT NULL,
                  PRIMARY KEY(doc_id, block)
                );
                CREATE INDEX IF NOT EXISTS idx_fulltext_page
                  ON fulltext_blocks(doc_id,page,block);
                CREATE TABLE IF NOT EXISTS fulltext_revisions(
                  doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                  parsed_sha256 TEXT NOT NULL,
                  pdf_sha256 TEXT NOT NULL,
                  archive_json TEXT NOT NULL,
                  archive_pdf TEXT NOT NULL,
                  captured_at TEXT NOT NULL,
                  PRIMARY KEY(doc_id,parsed_sha256)
                );
            """)
            try:
                db.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS fulltext_fts USING fts5("
                    "doc_id UNINDEXED, block UNINDEXED, body, tokenize='trigram')"
                )
            except sqlite3.OperationalError:
                pass

    @staticmethod
    def _fts_available(db: sqlite3.Connection) -> bool:
        return db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fulltext_fts'"
        ).fetchone() is not None

    @staticmethod
    def _check_id(doc_id: str) -> str:
        if not isinstance(doc_id, str) or not ID_PATTERN.fullmatch(doc_id):
            raise PatentWorkflowError("必须使用当前案卷的稳定 EV- 证据编号。")
        return doc_id

    def _directory(self, doc_id: str) -> Path:
        folder = self.root / self._check_id(doc_id)
        if folder.is_symlink():
            raise PatentWorkflowError("全文文献归档目录禁止符号链接。")
        return folder

    def attach(
        self, doc_id: str, parsed_json: Path, source_pdf: Path, *,
        authorized: bool = False,
    ) -> dict[str, Any]:
        """将已解析 JSON 和原始 PDF 成对校验、独立归档及索引。

        解析 JSON 可能来自非可信的外部管道，数据全量做大小/类型/位置检查；
        不根据其中任意文本自动宣称人工核对通过。
        """
        self._check_id(doc_id)
        if not authorized:
            raise PatentWorkflowError("必须获得使用和本地存储全文资料的明确授权。")
        pdf = _within_case(source_pdf, self.memory.project_root, extension=".pdf")
        parsed = _within_case(parsed_json, self.memory.project_root, extension=".json")
        if not 5 <= pdf.stat().st_size <= MAX_PDF_BYTES:
            raise PatentWorkflowError("原始 PDF 大小超出允许范围。")
        if not 10 <= parsed.stat().st_size <= MAX_PARSED_BYTES:
            raise PatentWorkflowError("Docling JSON 解析结果超过允许范围。")
        digest = sha256()
        with pdf.open("rb") as handle:
            if not handle.read(5).startswith(b"%PDF-"):
                raise PatentWorkflowError("原文文件不具备 PDF 格式头。")
            handle.seek(0)
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        pdf_sha = digest.hexdigest()
        data = json.loads(parsed.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("parser") != "docling":
            raise PatentWorkflowError("解析结果必须为现有 Docling 结构化证据契约。")
        if data.get("source_pdf_sha256") != pdf_sha:
            raise PatentWorkflowError("PDF SHA256 与 JSON 来源不一致，阻断错误文献绑定。")
        if data.get("review_status") != "awaiting_original_pdf_review":
            raise PatentWorkflowError("解析器不得自称已完成人工原文核验。")
        parser_version = str(data.get("parser_version") or "")[:100]
        source_url = str(data.get("source_url") or "")[:2048]
        if source_url:
            from urllib.parse import urlsplit
            url = urlsplit(source_url)
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise PatentWorkflowError("源文献链接必须为无账号密码的 HTTPS URL。")
        raw_blocks = data.get("blocks")
        if not isinstance(raw_blocks, list) or not 1 <= len(raw_blocks) <= MAX_ITEMS:
            raise PatentWorkflowError("解析证据缺少有效的 Docling 段落。")
        blocks: list[tuple[int, int | None, str, str, str, str]] = []
        total = 0
        seen: set[int] = set()
        for raw in raw_blocks:
            if not isinstance(raw, dict):
                raise PatentWorkflowError("Docling 段落必须为 JSON 对象。")
            block = raw.get("block")
            page = raw.get("page")
            body = raw.get("text")
            if type(block) is not int or not 1 <= block <= MAX_ITEMS or block in seen:
                raise PatentWorkflowError("Docling 段落序号重复或超限。")
            if page is not None and (type(page) is not int or not 1 <= page <= MAX_PAGES):
                raise PatentWorkflowError("Docling 原文页码必须为正整数或明确缺失。")
            if not isinstance(body, str) or not body.strip() or len(body) > MAX_ITEM_LENGTH:
                raise PatentWorkflowError("Docling 段落文本格式或长度无效。")
            total += len(body)
            if total > MAX_TOTAL_CHARS:
                raise PatentWorkflowError("PDF 正文超过安全的文献处理预算。")
            label = str(raw.get("label", ""))[:100]
            bbox = raw.get("bbox")
            if bbox is not None:
                if not isinstance(bbox, dict) or set(bbox) - {"l", "t", "r", "b"}:
                    raise PatentWorkflowError("PDF 坐标字段格式错误。")
                if any(
                    isinstance(v, bool) or not isinstance(v, (int, float))
                    or not math.isfinite(v) for v in bbox.values()
                ):
                    raise PatentWorkflowError("PDF 坐标包含非有限数值。")
            seen.add(block)
            blocks.append((
                block, page, label, body, sha256(body.encode("utf-8")).hexdigest(),
                json.dumps(bbox, ensure_ascii=False, sort_keys=True),
            ))
        blocks.sort(key=lambda item: item[0])
        normalized_sha = sha256(
            json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        folder = self._directory(doc_id)
        with self.memory.connect() as db:
            meta = db.execute(
                "SELECT doc_id,source_url FROM documents WHERE doc_id=?", (doc_id,)
            ).fetchone()
            old = db.execute(
                "SELECT pdf_sha256,parsed_sha256 FROM fulltext_sources WHERE doc_id=?",
                (doc_id,),
            ).fetchone()
        if meta is None:
            raise PatentWorkflowError("请先将该文献元数据登记到当前案卷，禁止悬空全文。")
        if old and old["parsed_sha256"] == normalized_sha:
            return {
                "doc_id": doc_id, "status": "unchanged",
                "pdf_sha256": pdf_sha, "parsed_sha256": normalized_sha,
                "blocks": len(blocks), "review_status": "awaiting_original_pdf_review",
            }
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        pdf_dest = folder / ("source-" + pdf_sha + ".pdf")
        json_dest = folder / ("docling-" + normalized_sha + ".json")
        _copy_immutable(pdf, pdf_dest)
        if not json_dest.exists():
            save_json(json_dest, data)
        if not SHA_PATTERN.fullmatch(pdf_sha):
            raise PatentWorkflowError("无法验证原始资料哈希。")
        with self.memory.connect(write=True) as db:
            db.execute("DELETE FROM fulltext_blocks WHERE doc_id=?", (doc_id,))
            if self._fts_available(db):
                db.execute("DELETE FROM fulltext_fts WHERE doc_id=?", (doc_id,))
            db.executemany(
                "INSERT INTO fulltext_blocks(doc_id,block,page,label,body,body_sha256,bbox_json)"
                " VALUES(?,?,?,?,?,?,?)",
                [(doc_id, *row) for row in blocks],
            )
            if self._fts_available(db):
                db.executemany(
                    "INSERT INTO fulltext_fts(doc_id,block,body) VALUES(?,?,?)",
                    [(doc_id, row[0], row[3]) for row in blocks],
                )
            db.execute(
                "INSERT INTO fulltext_sources(doc_id,pdf_sha256,parsed_sha256,parser,"
                "parser_version,source_url,blocks,review_status,captured_at)"
                " VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(doc_id) DO UPDATE SET "
                "pdf_sha256=excluded.pdf_sha256,parsed_sha256=excluded.parsed_sha256,"
                "parser=excluded.parser,parser_version=excluded.parser_version,"
                "source_url=excluded.source_url,blocks=excluded.blocks,"
                "review_status=excluded.review_status,captured_at=excluded.captured_at",
                (doc_id, pdf_sha, normalized_sha, "docling", parser_version,
                 source_url or meta["source_url"], len(blocks),
                 "awaiting_original_pdf_review", utc_now()),
            )
            db.execute(
                "INSERT OR IGNORE INTO fulltext_revisions(doc_id,parsed_sha256,pdf_sha256,"
                "archive_json,archive_pdf,captured_at) VALUES(?,?,?,?,?,?)",
                (doc_id, normalized_sha, pdf_sha,
                 str(json_dest.relative_to(self.memory.root)),
                 str(pdf_dest.relative_to(self.memory.root)), utc_now()),
            )
        status = "updated" if old else "attached"
        return {
            "doc_id": doc_id, "status": status, "pdf_sha256": pdf_sha,
            "parsed_sha256": normalized_sha, "blocks": len(blocks),
            "page_anchors": sum(row[1] is not None for row in blocks),
            "review_status": "awaiting_original_pdf_review",
            "source_url": source_url or meta["source_url"],
            "stale_previous_notes": bool(old and old["pdf_sha256"] != pdf_sha),
        }

    def status(self, doc_id: str) -> dict[str, Any]:
        self._check_id(doc_id)
        with self.memory.connect() as db:
            row = db.execute(
                "SELECT * FROM fulltext_sources WHERE doc_id=?", (doc_id,)
            ).fetchone()
        if row is None:
            return {"doc_id": doc_id, "attached": False, "status": "no_parsed_fulltext"}
        return {"doc_id": doc_id, "attached": True, **dict(row),
                "status": "parsed_unreviewed"}

    def validate_positions(self, doc_id: str, positions: list[str]) -> None:
        if not positions or len(positions) > 30:
            raise PatentWorkflowError("全文结论必须有1至30个真实的页码段落证据。")
        self._check_id(doc_id)
        with self.memory.connect() as db:
            for value in positions:
                match = ANCHOR_PATTERN.fullmatch(value) if isinstance(value, str) else None
                if not match:
                    raise PatentWorkflowError("原文证据定位格式须为 p2:b5（页码:段落）。")
                row = db.execute(
                    "SELECT page FROM fulltext_blocks WHERE doc_id=? AND block=?",
                    (doc_id, int(match.group(2))),
                ).fetchone()
                if row is None or row["page"] != int(match.group(1)):
                    raise PatentWorkflowError("原文页码/段落在当前文献解析版本中不存在。")

    def quote(self, doc_id: str, position: str, verbatim: str) -> dict[str, Any]:
        """仅证实字符串存在于已提取段落，不能代替原始 PDF 的专业核验。"""
        self.validate_positions(doc_id, [position])
        if not isinstance(verbatim, str) or not 3 <= len(verbatim) <= 1000:
            raise PatentWorkflowError("必须提供3至1000字符的待核对原文短引。")
        block = int(ANCHOR_PATTERN.fullmatch(position).group(2))
        with self.memory.connect() as db:
            row = db.execute(
                "SELECT page,body,body_sha256 FROM fulltext_blocks "
                "WHERE doc_id=? AND block=?", (doc_id, block),
            ).fetchone()
            source = db.execute(
                "SELECT pdf_sha256,source_url FROM fulltext_sources WHERE doc_id=?",
                (doc_id,),
            ).fetchone()
        found = verbatim in row["body"]
        return {
            "doc_id": doc_id, "anchor": position, "exact_match": found,
            "page": row["page"], "block_sha256": row["body_sha256"],
            "pdf_sha256": source["pdf_sha256"], "source_url": source["source_url"],
            "verification_level": "parsed_text_match_only",
            "quote_sha256": sha256(verbatim.encode("utf-8")).hexdigest() if found else None,
        }

    def search(
        self, query: str, *, doc_id: str | None = None, limit: int = 20,
    ) -> list[dict[str, Any]]:
        """按每个原文段落查找真实匹配页码，返回可验证 p#:b# 锚点。"""
        if not isinstance(query, str) or not query.strip():
            raise PatentWorkflowError("原文检索词不能为空。")
        if doc_id is not None:
            self._check_id(doc_id)
        limit = max(1, min(int(limit), 100))
        term = query.strip()[:160]
        with self.memory.connect() as db:
            hits: list[sqlite3.Row] = []
            if len(term) >= 3 and self._fts_available(db):
                try:
                    sql = (
                        "SELECT b.doc_id,b.block,b.page,b.label,b.body,b.body_sha256,"
                        "s.pdf_sha256,s.source_url, bm25(fulltext_fts) AS rank "
                        "FROM fulltext_fts JOIN fulltext_blocks b "
                        "ON b.doc_id=fulltext_fts.doc_id AND b.block=fulltext_fts.block "
                        "JOIN fulltext_sources s ON s.doc_id=b.doc_id "
                        "WHERE fulltext_fts MATCH ?"
                    )
                    params: list[Any] = ['"' + term.replace('"', '""') + '"']
                    if doc_id:
                        sql += " AND b.doc_id=?"
                        params.append(doc_id)
                    hits = db.execute(
                        sql + " ORDER BY rank, b.doc_id,b.block LIMIT ?",
                        [*params, limit],
                    ).fetchall()
                except sqlite3.OperationalError:
                    hits = []
            if not hits:
                escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                sql = (
                    "SELECT b.doc_id,b.block,b.page,b.label,b.body,b.body_sha256,"
                    "s.pdf_sha256,s.source_url FROM fulltext_blocks b "
                    "JOIN fulltext_sources s ON s.doc_id=b.doc_id "
                    "WHERE b.body LIKE ? ESCAPE '\\'"
                )
                params = ["%" + escaped + "%"]
                if doc_id:
                    sql += " AND b.doc_id=?"
                    params.append(doc_id)
                hits = db.execute(
                    sql + " ORDER BY b.doc_id,b.page,b.block LIMIT ?",
                    [*params, limit],
                ).fetchall()
            return [{
                "doc_id": row["doc_id"], "anchor": (
                    f"p{row['page']}:b{row['block']}" if row["page"] is not None else None
                ), "page": row["page"], "block": row["block"],
                "label": row["label"], "excerpt": row["body"][:700],
                "text_sha256": row["body_sha256"],
                "pdf_sha256": row["pdf_sha256"], "source_url": row["source_url"],
                "review_status": "awaiting_original_pdf_review",
            } for row in hits]
