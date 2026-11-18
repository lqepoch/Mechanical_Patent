"""项目隔离的文献长期记忆：每篇一份 Markdown + SQLite FTS5 检索索引。

数据供应商返回的著录/摘要是待核查资料，不自动声称已阅读全文。
保留研究人员和 AI 的后续批注；重新检索只更新机器生成区。
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any, Iterable, Iterator

from .core import Evidence, PatentWorkflowError, deduplicate, evidence_id, utc_now


AUTO_END = "<!-- END GENERATED BIBLIOGRAPHY -->"
ANALYSIS_START = "<!-- BEGIN RESEARCH NOTES: PRESERVED ACROSS REFRESH -->"
ALLOWED_BASIS = frozenset({"metadata", "abstract", "claims", "full_text"})
MAX_NOTES = 250_000


def _digest(data: Any) -> str:
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _safe_markdown(value: str, maximum: int = 50000) -> str:
    # External records are data, never instructions. Prevent fake template delimiters.
    return str(value or "")[:maximum].replace("<!--", "&lt;!--").replace("-->", "--&gt;")


def _atomic_text(path: Path, content: str) -> None:
    if path.is_symlink():
        raise PatentWorkflowError("文献记忆文件禁止符号链接。")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise PatentWorkflowError("文献记忆目录禁止符号链接。")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=".memory-",
        delete=False,
    ) as handle:
        temp = Path(handle.name)
        os.chmod(temp, 0o600)
        try:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


class LiteratureMemoryStore:
    """一个研发项目一个独立 SQLite + 一篇文献一份稳定 Markdown。"""

    def __init__(self, project_root: Path):
        folder = Path(project_root).expanduser()
        if folder.is_symlink():
            raise PatentWorkflowError("项目根目录禁止使用符号链接。")
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.project_root = folder.resolve()
        self.root = self.project_root / "knowledge"
        if self.root.is_symlink():
            raise PatentWorkflowError("知识库目录禁止使用符号链接。")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db_path = self.root / "literature.sqlite3"
        self._initialize()

    @contextmanager
    def connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def _initialize(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documents(
                  doc_id TEXT PRIMARY KEY,
                  kind TEXT NOT NULL,
                  publication TEXT NOT NULL,
                  title TEXT NOT NULL,
                  source TEXT NOT NULL,
                  source_url TEXT NOT NULL,
                  published_at TEXT NOT NULL,
                  metadata_verified INTEGER NOT NULL,
                  abstract TEXT NOT NULL,
                  claims TEXT NOT NULL,
                  content_hash TEXT NOT NULL,
                  note_path TEXT NOT NULL,
                  analysis_count INTEGER NOT NULL DEFAULT 0,
                  first_seen TEXT NOT NULL,
                  last_seen TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_literature_kind ON documents(kind, published_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_literature_publication
                  ON documents(kind, publication);
                CREATE TABLE IF NOT EXISTS harvest_checkpoints(
                  query_id TEXT PRIMARY KEY,
                  provider TEXT NOT NULL,
                  query_text TEXT NOT NULL,
                  cursor TEXT,
                  pages INTEGER NOT NULL,
                  records INTEGER NOT NULL,
                  state TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS resume_audit(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  analyst TEXT NOT NULL, old_hash TEXT NOT NULL,
                  new_hash TEXT NOT NULL, recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS note_audit(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  doc_id TEXT NOT NULL REFERENCES documents(doc_id),
                  analyst TEXT NOT NULL,
                  basis TEXT NOT NULL,
                  source_positions TEXT NOT NULL,
                  note_hash TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
            """)
            # Additive migration: keep existing private project DBs and research notes.
            existing = {row["name"] for row in db.execute("PRAGMA table_info(documents)")}
            if "pdf_url" not in existing:
                db.execute("ALTER TABLE documents ADD COLUMN pdf_url TEXT NOT NULL DEFAULT ''")
            if "paper_metadata_json" not in existing:
                db.execute("ALTER TABLE documents ADD COLUMN paper_metadata_json TEXT NOT NULL DEFAULT '{}'")
            try:
                db.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5("
                    "doc_id UNINDEXED, title, publication, abstract, claims, research_notes,"
                    "tokenize='trigram')"
                )
            except sqlite3.OperationalError:
                # 有些精简发行版缺少 FTS5/trigram；仍允许准确的 LIKE 回退。
                pass
        self._bootstrap_resume()

    def _bootstrap_resume(self) -> None:
        path = self.root / "RESEARCH_RESUME.md"
        if not path.exists():
            _atomic_text(path, (
                "# 项目研究恢复入口\n\n"
                "## 当前研究问题与范围\n\n待研究者填写。\n\n"
                "## 已确认的工程事实与证据编号\n\n待核对原始文献后填写。\n\n"
                "## 技术分歧、反例与未解决疑点\n\n待补充。\n\n"
                "## 候选创新方向与验证任务\n\n待补充。\n\n"
                "## 下一轮检索计划与停止条件\n\n待补充。\n\n"
                "每次重新开启 AI 会话，先读取本文件，再通过检索工具按需加载单篇记忆。\n"
            ))

    def _note_path(self, doc_id: str, kind: str) -> Path:
        if not re.fullmatch(r"EV-[A-F0-9]{12}", doc_id):
            raise PatentWorkflowError("无效的文献编号。")
        return self.root / "documents" / ("patents" if kind == "patent" else "papers") / (doc_id + ".md")

    def _generated(self, record: Evidence, doc_id: str) -> str:
        fields = {
            "id": doc_id, "kind": record.kind, "publication": record.publication,
            "title": record.title, "source": record.source,
            "source_url": record.url, "publication_date": record.publication_date,
            "fetched_at": record.retrieved_at, "metadata_from_provider": record.verified,
            "full_text_verified": False,
            "pdf_url": record.pdf_url,
            "paper_metadata": record.paper_metadata if record.kind == "paper" else {},
        }
        head = "\n".join(
            key + ": " + json.dumps(value, ensure_ascii=False) for key, value in fields.items()
        )
        return (
            "---\n" + head + "\n---\n\n"
            "# " + _safe_markdown(record.title, 400) + "\n\n"
            "## 原始著录数据\n\n"
            "文献标识：" + _safe_markdown(record.publication, 160) + "\n\n"
            "来源链接：" + _safe_markdown(record.url, 2000) + "\n\n"
            "公开日期：" + _safe_markdown(record.publication_date, 80) + "\n\n"
            "来源：" + _safe_markdown(record.source, 100) + "\n\n"
            "## 来源摘要（未视为全文）\n\n"
            + (_safe_markdown(record.abstract, 12000) or "未检索到摘要。") + "\n\n"
            "## 权利要求摘录（如来源提供）\n\n"
            + (_safe_markdown(record.claims, 15000) or "尚未获取原始权利要求。") + "\n\n"
            "## 证据级别\n\n"
            "供应商元数据：" + ("已获取" if record.verified else "导入记录，待核实")
            + "；全文阅读与技术结论：尚未核实。\n\n"
            + AUTO_END + "\n\n"
        )

    def _fts_enabled(self, db: sqlite3.Connection) -> bool:
        return db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents_fts'"
        ).fetchone() is not None

    def _index_fts(self, db: sqlite3.Connection, doc_id: str, *, body: str) -> None:
        if not self._fts_enabled(db):
            return
        row = db.execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
        db.execute("DELETE FROM documents_fts WHERE doc_id=?", (doc_id,))
        db.execute(
            "INSERT INTO documents_fts(doc_id,title,publication,abstract,claims,research_notes)"
            " VALUES(?,?,?,?,?,?)",
            (doc_id, row["title"], row["publication"], row["abstract"],
             row["claims"], body.split(ANALYSIS_START, 1)[-1][:MAX_NOTES]),
        )

    def ingest_many(self, documents: Iterable[Evidence]) -> dict[str, int]:
        records = deduplicate([
            item for item in documents if item.kind in {"patent", "paper"}
        ])
        counts = {"new": 0, "updated": 0, "unchanged": 0}
        with self.connect(write=True) as db:
            for record in records:
                doc_id = evidence_id(record)
                fingerprint = _digest({
                    key: value for key, value in record.to_dict().items()
                    if key != "retrieved_at"
                })
                old = db.execute(
                    "SELECT * FROM documents WHERE doc_id=?",
                    (doc_id,),
                ).fetchone()
                if old is not None and record.kind == "paper":
                    # Preserve multi-provider provenance even across separate harvest batches.
                    from .paper_sources import merge_paper_records
                    previous = Evidence(
                        publication=old["publication"], title=old["title"],
                        url=old["source_url"], source=old["source"],
                        retrieved_at=record.retrieved_at, kind="paper",
                        abstract=old["abstract"], publication_date=old["published_at"],
                        verified=bool(old["metadata_verified"]), pdf_url=old["pdf_url"],
                        paper_metadata=json.loads(old["paper_metadata_json"] or "{}"),
                    )
                    record = merge_paper_records([previous, record])[0]
                    fingerprint = _digest({
                        key: value for key, value in record.to_dict().items()
                        if key != "retrieved_at"
                    })
                file = self._note_path(doc_id, record.kind)
                if file.is_symlink():
                    raise PatentWorkflowError("检测到文献文件符号链接，拒绝写入。")
                if old and old["note_path"] != str(file.relative_to(self.root)):
                    raise PatentWorkflowError("文献路径发生异常变更。")
                if old and old["content_hash"] == fingerprint and file.is_file():
                    db.execute(
                        "UPDATE documents SET last_seen=? WHERE doc_id=?",
                        (utc_now(), doc_id),
                    )
                    counts["unchanged"] += 1
                    continue
                tail = (
                    file.read_text(encoding="utf-8").split(AUTO_END, 1)[-1].strip()
                    if file.is_file() and AUTO_END in file.read_text(encoding="utf-8")
                    else ANALYSIS_START + "\n\n"
                         "## 技术问题、作用效果与物理机理\n\n待分析。\n\n"
                         "## 关键结构 / 控制流程 / 参数与工况\n\n待分析。\n\n"
                         "## 已有技术限制、缺点及反证线索\n\n待分析。\n\n"
                         "## 可迁移的创新方向与跨文献关联\n\n待分析。\n\n"
                         "## 后续需要读取的原文页码及工程验证问题\n\n待补充。"
                )
                body = self._generated(record, doc_id) + tail + "\n"
                _atomic_text(file, body)
                now = utc_now()
                db.execute(
                    "INSERT INTO documents(doc_id,kind,publication,title,source,source_url,"
                    "published_at,metadata_verified,abstract,claims,content_hash,note_path,"
                    "first_seen,last_seen,pdf_url,paper_metadata_json)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                    " ON CONFLICT(doc_id) DO UPDATE SET "
                    "title=excluded.title,source=excluded.source,source_url=excluded.source_url,"
                    "published_at=excluded.published_at,metadata_verified=excluded.metadata_verified,"
                    "abstract=excluded.abstract,claims=excluded.claims,content_hash=excluded.content_hash,"
                    "pdf_url=excluded.pdf_url,paper_metadata_json=excluded.paper_metadata_json,"
                    "last_seen=excluded.last_seen",
                    (doc_id, record.kind, record.publication, record.title, record.source,
                     record.url, record.publication_date, int(record.verified),
                     record.abstract[:12000], record.claims[:50000], fingerprint,
                     str(file.relative_to(self.root)), now, now, record.pdf_url,
                     json.dumps(record.paper_metadata, ensure_ascii=False, sort_keys=True)),
                )
                self._index_fts(db, doc_id, body=body)
                counts["updated" if old else "new"] += 1
        self._refresh_index()
        return counts

    def _refresh_index(self) -> None:
        with self.connect() as db:
            rows = db.execute(
                "SELECT doc_id,kind,title,note_path FROM documents ORDER BY kind,title,doc_id"
            ).fetchall()
        items = ["# 项目文献总目录\n", "包含已发现文献；是否完成原始全文核查请查看各篇记录。\n"]
        for row in rows:
            title = _safe_markdown(row["title"], 150).replace("[", "［").replace("]", "］")
            items.append(
                "- [" + title + "](<" + row["note_path"].replace(" ", "%20") + ">) "
                + "(" + row["kind"] + "，" + row["doc_id"] + ")"
            )
        _atomic_text(self.root / "INDEX.md", "\n".join(items) + "\n")

    def search(self, query: str, *, limit: int = 20, kind: str | None = None) -> list[dict[str, Any]]:
        if not isinstance(query, str) or not query.strip():
            raise PatentWorkflowError("检索词不能为空。")
        if kind is not None and kind not in {"patent", "paper"}:
            raise PatentWorkflowError("文献类型必须为 patent 或 paper。")
        limit = max(1, min(int(limit), 100))
        term = query.strip()[:160]
        with self.connect() as db:
            hits: list[sqlite3.Row] = []
            if len(term) >= 3 and self._fts_enabled(db):
                try:
                    sql = (
                        "SELECT d.*,bm25(documents_fts) AS rank FROM documents_fts "
                        "JOIN documents d ON d.doc_id=documents_fts.doc_id "
                        "WHERE documents_fts MATCH ?"
                    )
                    params: list[Any] = ['"' + term.replace('"', '""') + '"']
                    if kind:
                        sql += " AND d.kind=?"
                        params.append(kind)
                    hits = db.execute(
                        sql + " ORDER BY rank, d.published_at DESC LIMIT ?",
                        [*params, limit],
                    ).fetchall()
                except sqlite3.OperationalError:
                    hits = []
            if not hits:
                escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                pattern = "%" + escaped + "%"
                sql = (
                    "SELECT * FROM documents WHERE (title LIKE ? ESCAPE '\\' "
                    "OR publication LIKE ? ESCAPE '\\' OR abstract LIKE ? ESCAPE '\\' "
                    "OR claims LIKE ? ESCAPE '\\')"
                )
                params = [pattern] * 4
                if kind:
                    sql += " AND kind=?"
                    params.append(kind)
                hits = db.execute(
                    sql + " ORDER BY published_at DESC,doc_id LIMIT ?",
                    [*params, limit],
                ).fetchall()
            return [
                {
                    "doc_id": r["doc_id"], "kind": r["kind"], "title": r["title"],
                    "publication": r["publication"], "published_at": r["published_at"],
                    "source": r["source"], "source_url": r["source_url"],
                    "note_path": r["note_path"],
                    "abstract_excerpt": r["abstract"][:500],
                    "metadata_verified": bool(r["metadata_verified"]),
                    "analysis_count": r["analysis_count"],
                } for r in hits
            ]

    def paper_source(self, doc_id: str) -> dict[str, Any]:
        """Return local paper source metadata only; no arbitrary file paths or remote queries."""
        if not re.fullmatch(r"EV-[A-F0-9]{12}", doc_id):
            raise PatentWorkflowError("文献编号不合法。")
        with self.connect() as db:
            row = db.execute(
                "SELECT doc_id,kind,publication,title,source,source_url,pdf_url,"
                "paper_metadata_json FROM documents WHERE doc_id=?", (doc_id,),
            ).fetchone()
        if row is None or row["kind"] != "paper":
            raise PatentWorkflowError("项目知识库中找不到指定论文。")
        return {
            "doc_id": row["doc_id"], "publication": row["publication"],
            "title": row["title"], "source": row["source"],
            "source_url": row["source_url"], "pdf_url": row["pdf_url"],
            "paper_metadata": json.loads(row["paper_metadata_json"] or "{}"),
        }

    def read(self, doc_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT doc_id,kind,note_path,content_hash,analysis_count "
                "FROM documents WHERE doc_id=?", (doc_id,),
            ).fetchone()
        if row is None:
            raise PatentWorkflowError("项目知识库中不存在此文献。")
        path = self._note_path(row["doc_id"], row["kind"])
        if path.is_symlink() or not path.is_file():
            raise PatentWorkflowError("文献记忆丢失或路径不安全，需修复索引。")
        content = path.read_text(encoding="utf-8")
        if len(content) > MAX_NOTES + 100_000:
            raise PatentWorkflowError("记忆文件超过最大读取限制。")
        return {"doc_id": row["doc_id"], "markdown": content,
                "path": str(path), "content_hash": row["content_hash"],
                "analysis_count": row["analysis_count"]}

    def write_analysis(
        self, doc_id: str, *, analyst: str, basis: str,
        analysis: dict[str, str], source_positions: list[str] | None = None,
    ) -> dict[str, Any]:
        if basis not in ALLOWED_BASIS:
            raise PatentWorkflowError("未知的文献分析依据。")
        positions = source_positions or []
        if basis == "full_text" and not positions:
            raise PatentWorkflowError("声称阅读原文全文时必须提供页码/章节引用。")
        if not isinstance(analysis, dict) or not analysis:
            raise PatentWorkflowError("分析必须为非空结构化对象。")
        allowed = {"plain_summary", "technical_mechanism", "structures_and_parameters",
                   "technical_effect", "limitations", "counterevidence",
                   "innovation_hooks", "cross_document_links", "open_questions"}
        if set(analysis) - allowed or any(not isinstance(x, str) for x in analysis.values()):
            raise PatentWorkflowError("分析字段不合法。")
        if len(json.dumps(analysis, ensure_ascii=False)) > 30000:
            raise PatentWorkflowError("单次文献批注长度超限。")
        actor = str(analyst).strip()[:100]
        if not actor:
            raise PatentWorkflowError("必须填写批注来源身份。")
        current = self.read(doc_id)
        entries = "\n\n### 研究批注 " + utc_now() + "\n\n"
        entries += "- 分析者：" + _safe_markdown(actor) + "\n"
        entries += "- 依据：" + basis + "（不代表完成独立核验）\n"
        entries += "- 原文位置：" + ", ".join(_safe_markdown(x, 200) for x in positions[:30]) + "\n\n"
        for field, value in analysis.items():
            entries += "#### " + field + "\n\n" + _safe_markdown(value, 30000) + "\n\n"
        old = current["markdown"]
        if len(old) + len(entries) > MAX_NOTES:
            raise PatentWorkflowError("文献记忆过大；请先归档历史批注再添加。")
        path = self._note_path(doc_id, "patent" if "/patents/" in current["path"] else "paper")
        _atomic_text(path, old + entries)
        with self.connect(write=True) as db:
            db.execute(
                "UPDATE documents SET analysis_count=analysis_count+1,last_seen=? WHERE doc_id=?",
                (utc_now(), doc_id),
            )
            db.execute(
                "INSERT INTO note_audit(doc_id,analyst,basis,source_positions,note_hash,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (doc_id, actor, basis, json.dumps(positions, ensure_ascii=False),
                 sha256(entries.encode("utf-8")).hexdigest(), utc_now()),
            )
            self._index_fts(db, doc_id, body=old + entries)
        return {"doc_id": doc_id, "analysis_count": current["analysis_count"] + 1,
                "note_sha256": sha256((old + entries).encode("utf-8")).hexdigest()}

    def stats(self) -> dict[str, Any]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT kind, COUNT(*) AS n,SUM(CASE WHEN analysis_count>0 THEN 1 ELSE 0 END)"
                " AS analyzed FROM documents GROUP BY kind"
            ).fetchall()
            checkpoints = db.execute(
                "SELECT COUNT(*) FROM harvest_checkpoints WHERE state='partial'"
            ).fetchone()[0]
        return {"database": str(self.db_path),
                "by_kind": {r["kind"]: {"documents": r["n"], "analyzed": r["analyzed"]}
                            for r in rows}, "partial_queries": checkpoints,
                "resume_file": str(self.root / "RESEARCH_RESUME.md")}

    def get_checkpoint(self, query_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM harvest_checkpoints WHERE query_id=?", (query_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def save_checkpoint(
        self, query_id: str, provider: str, query: str,
        cursor: str | None, pages: int, records: int, state: str, error: str = "",
    ) -> None:
        if state not in {"partial", "complete", "failed"}:
            raise PatentWorkflowError("检索任务状态无效。")
        with self.connect(write=True) as db:
            db.execute(
                "INSERT INTO harvest_checkpoints(query_id,provider,query_text,cursor,pages,"
                "records,state,updated_at,error) VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(query_id) DO UPDATE SET cursor=excluded.cursor,pages=excluded.pages,"
                "records=excluded.records,state=excluded.state,updated_at=excluded.updated_at,"
                "error=excluded.error",
                (query_id, provider, query, cursor, pages, records, state, utc_now(), error[:1000]),
            )


    def pending_analysis(self, *, limit: int = 30) -> list[dict[str, Any]]:
        """分批提供 AI 下一轮要读的文献，避免一次性注入1000篇全文。"""
        with self.connect() as db:
            rows = db.execute(
                "SELECT doc_id,kind,title,publication,source_url,note_path,"
                "abstract FROM documents WHERE analysis_count=0 "
                "ORDER BY published_at DESC,doc_id LIMIT ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        return [
            {"doc_id": r["doc_id"], "kind": r["kind"], "title": r["title"],
             "publication": r["publication"], "source_url": r["source_url"],
             "note_path": r["note_path"], "abstract_excerpt": r["abstract"][:700]}
            for r in rows
        ]

    def read_resume(self) -> dict[str, Any]:
        path = self.root / "RESEARCH_RESUME.md"
        if path.is_symlink():
            raise PatentWorkflowError("研究恢复入口禁止符号链接。")
        body = path.read_text(encoding="utf-8")
        return {"markdown": body, "sha256": sha256(body.encode("utf-8")).hexdigest(),
                "path": str(path)}

    def update_resume(
        self, markdown: str, *, expected_sha256: str, analyst: str,
    ) -> dict[str, str]:
        """带乐观锁的研究状态更新；旧版快照归档，避免多 Agent 覆写。"""
        if not isinstance(markdown, str) or not 30 <= len(markdown) <= 50000:
            raise PatentWorkflowError("研究恢复摘要长度须为30至50000字符。")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256 or ""):
            raise PatentWorkflowError("更新项目摘要需要先读取当前 SHA256。")
        analyst = str(analyst).strip()[:100]
        if not analyst:
            raise PatentWorkflowError("需要研究总结提交者标识。")
        path = self.root / "RESEARCH_RESUME.md"
        with self.connect(write=True) as db:
            current = self.read_resume()
            if current["sha256"] != expected_sha256:
                raise PatentWorkflowError("项目研究摘要已被另一个智能体修改，必须重新读取合并。")
            history = self.root / "resume_history" / (expected_sha256 + ".md")
            if not history.is_file():
                _atomic_text(history, current["markdown"])
            body = markdown.rstrip() + "\n"
            _atomic_text(path, body)
            digest = sha256(body.encode("utf-8")).hexdigest()
            db.execute(
                "INSERT INTO resume_audit(analyst,old_hash,new_hash,recorded_at)"
                " VALUES(?,?,?,?)",
                (analyst, expected_sha256, digest, utc_now()),
            )
        return {"sha256": digest, "previous_sha256": expected_sha256,
                "path": str(path)}
