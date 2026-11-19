"""复用 canonical FulltextPipeline 的获授权多文献批次检查点和预算控制。

只调度已有的逐篇许可审核 / 租约 / 安全下载 / Docling 索引实现，
不建立第二套 PDF 事实库或全文状态机。
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import time
from typing import Any, Callable

from .core import PatentWorkflowError, utc_now
from .literature_fulltext import FulltextPipeline
from .pdf_archive import MAX_PDF_BYTES, download_pdf
from .pdf_extraction import parse_local_pdf

_ID = re.compile(r"EV-[0-9A-F]{12}\Z")
_BATCH_ID = re.compile(r"FTB-[0-9A-F]{20}\Z")


class FullTextBatchRunner:
    """单项目 SQLite 检查点；版权、租约和内容审查均委托 FulltextPipeline。"""

    def __init__(self, pipeline: FulltextPipeline):
        self.pipeline = pipeline
        with pipeline.memory.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS fulltext_batches (
                  batch_id TEXT PRIMARY KEY,
                  manifest_sha256 TEXT NOT NULL,
                  total INTEGER NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fulltext_batch_items (
                  batch_id TEXT NOT NULL REFERENCES fulltext_batches(batch_id),
                  doc_id TEXT NOT NULL,
                  ordinal INTEGER NOT NULL,
                  state TEXT NOT NULL DEFAULT 'pending',
                  attempts INTEGER NOT NULL DEFAULT 0,
                  pdf_sha256 TEXT NOT NULL DEFAULT '',
                  last_error TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL,
                  PRIMARY KEY(batch_id,doc_id)
                );
                CREATE INDEX IF NOT EXISTS idx_fulltext_batch_status
                  ON fulltext_batch_items(batch_id,state,ordinal);
            """)

    @staticmethod
    def _manifest(items: Any) -> list[dict[str, Any]]:
        if not isinstance(items, list) or not 1 <= len(items) <= 1000:
            raise PatentWorkflowError("全文批次须包含1至1000条文献。")
        seen: set[str] = set()
        result = []
        for item in items:
            if not isinstance(item, dict):
                raise PatentWorkflowError("全文批次条目格式错误。")
            doc_id = item.get("doc_id")
            if not isinstance(doc_id, str) or not _ID.fullmatch(doc_id) or doc_id in seen:
                raise PatentWorkflowError("文献编号非法或重复。")
            seen.add(doc_id)
            actor = item.get("rights_actor")
            ref = item.get("rights_reference")
            if not isinstance(actor, str) or len(actor.strip()) < 2:
                raise PatentWorkflowError("逐篇论文必须注明许可审核人员。")
            if not isinstance(ref, str) or len(ref.strip()) < 8:
                raise PatentWorkflowError("逐篇论文必须注明审核通过的版权记录。")
            hosts = item.get("allowed_hosts")
            if not isinstance(hosts, list) or not hosts or not all(
                isinstance(host, str) and host.strip() for host in hosts
            ):
                raise PatentWorkflowError("逐篇论文必须列明允许下载的域名。")
            if not isinstance(item.get("parse", True), bool):
                raise PatentWorkflowError("parse 参数须为布尔值。")
            result.append({
                "doc_id": doc_id,
                "rights_actor": actor.strip()[:100],
                "rights_reference": ref.strip()[:300],
                "allowed_hosts": list(dict.fromkeys(hosts)),
                "parse": item.get("parse", True),
            })
        return result

    def run(
        self, manifest: dict[str, Any], *, authorized: bool,
        outbound_approved: bool = False,
        artifacts: Path | None = None,
        converter: Any | None = None,
        downloader: Callable[..., dict[str, Any]] = download_pdf,
        parser: Callable[..., dict[str, Any]] = parse_local_pdf,
        max_documents: int = 100, max_seconds: int = 900,
        max_total_bytes: int = 2 * 1024 * 1024 * 1024,
        max_attempts: int = 3,
        refresh: bool = False,
    ) -> dict[str, Any]:
        if not authorized or not outbound_approved:
            raise PatentWorkflowError("全文批次需要明确的许可执行及本轮外发审批。")
        if not isinstance(manifest, dict):
            raise PatentWorkflowError("全文清单必须是 JSON 对象。")
        items = self._manifest(manifest.get("items"))
        if not 1 <= max_documents <= 1000:
            raise PatentWorkflowError("每轮文献处理数量预算须在1-1000之间。")
        if not 10 <= max_seconds <= 3600:
            raise PatentWorkflowError("最长任务执行预算须在10-3600秒之间。")
        if not 1000 <= max_total_bytes <= 10 * 1024 * 1024 * 1024:
            raise PatentWorkflowError("单轮全文字节预算无效。")
        if not 1 <= max_attempts <= 3:
            raise PatentWorkflowError("单篇最大重试次数必须在1-3之间。")
        serialized = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = sha256(serialized.encode("utf-8")).hexdigest()
        batch_id = "FTB-" + digest[:20].upper()
        now = utc_now()
        with self.pipeline.memory.connect(write=True) as db:
            db.execute(
                "INSERT INTO fulltext_batches(batch_id,manifest_sha256,total,created_at,updated_at)"
                " VALUES(?,?,?,?,?) ON CONFLICT(batch_id) DO UPDATE SET updated_at=excluded.updated_at",
                (batch_id, digest, len(items), now, now),
            )
            db.executemany(
                "INSERT OR IGNORE INTO fulltext_batch_items(batch_id,doc_id,ordinal,state,updated_at)"
                " VALUES(?,?,?,'pending',?)",
                [(batch_id, item["doc_id"], i, now) for i, item in enumerate(items)],
            )

        done, skipped, failed, processed, processed_bytes = 0, 0, 0, 0, 0
        errors: list[dict[str, str]] = []
        started = time.monotonic()
        for item in items:
            if processed >= max_documents or time.monotonic() - started > max_seconds:
                break
            doc_id = item["doc_id"]
            with self.pipeline.memory.connect() as db:
                entry = db.execute(
                    "SELECT state,attempts,pdf_sha256 FROM fulltext_batch_items "
                    "WHERE batch_id=? AND doc_id=?", (batch_id, doc_id),
                ).fetchone()
            job = self.pipeline.status(doc_id)
            job_stage = job.get("status", "not_planned")
            if not refresh and entry["state"] == "done":
                if (job.get("pdf_sha256") == entry["pdf_sha256"] and
                    ((item["parse"] and job_stage == "parsed")
                     or (not item["parse"] and job_stage in {"downloaded", "parsed"}))):
                    skipped += 1
                    continue
            if not refresh and entry["attempts"] >= max_attempts:
                skipped += 1
                continue
            if processed_bytes + 1000 > max_total_bytes:
                break
            processed += 1
            try:
                # 首次任务先登记可追查的版权批准；已经在处理中或
                # 已下载可复用的同版 PDF，直接沿用原租约状态机。
                if refresh or job_stage == "not_planned":
                    self.pipeline.queue(
                        doc_id, rights_actor=item["rights_actor"],
                        rights_reference=item["rights_reference"], authorized=True,
                    )
                remaining = max_total_bytes - processed_bytes
                output = self.pipeline.process(
                    doc_id, allowed_hosts=set(item["allowed_hosts"]),
                    authorized=True, artifacts=artifacts,
                    parse=item["parse"],
                    max_bytes=min(MAX_PDF_BYTES, remaining),
                    downloader=downloader, parser=parser, converter=converter,
                )
                if output.get("status") not in {"downloaded", "parsed"}:
                    raise PatentWorkflowError("本轮全文工作尚未完成获准的阶段。")
                local_length = 0
                if output.get("pdf_path"):
                    local = self.pipeline._safe_local(
                        output["pdf_path"], output["pdf_sha256"]
                    )
                    local_length = local.stat().st_size
                processed_bytes += local_length
                with self.pipeline.memory.connect(write=True) as db:
                    db.execute(
                        "UPDATE fulltext_batch_items SET state='done',attempts=attempts+1,"
                        "pdf_sha256=?,last_error='',updated_at=? WHERE batch_id=? AND doc_id=?",
                        (str(output.get("pdf_sha256") or ""), utc_now(), batch_id, doc_id),
                    )
                done += 1
            except Exception as exc:
                with self.pipeline.memory.connect(write=True) as db:
                    db.execute(
                        "UPDATE fulltext_batch_items SET state='failed',attempts=attempts+1,"
                        "last_error=?,updated_at=? WHERE batch_id=? AND doc_id=?",
                        (str(exc)[:240], utc_now(), batch_id, doc_id),
                    )
                failed += 1
                errors.append({"doc_id": doc_id, "reason": str(exc)[:180]})

        with self.pipeline.memory.connect() as db:
            states = db.execute(
                "SELECT state,COUNT(*) AS n FROM fulltext_batch_items "
                "WHERE batch_id=? GROUP BY state", (batch_id,),
            ).fetchall()
        counts = {row["state"]: row["n"] for row in states}
        return {
            "batch_id": batch_id,
            "status": "complete" if counts.get("done", 0) == len(items) else "partial",
            "total": len(items), "completed_total": counts.get("done", 0),
            "pending": counts.get("pending", 0),
            "failed_pending_retry": counts.get("failed", 0),
            "processed_this_run": processed, "done_this_run": done,
            "skipped_this_run": skipped, "failed_this_run": failed,
            "bytes_processed_this_run": processed_bytes,
            "errors": errors[:50], "full_text_verified": False,
        }

    def status(self, batch_id: str, *, limit: int = 100) -> dict[str, Any]:
        if not isinstance(batch_id, str) or not _BATCH_ID.fullmatch(batch_id):
            raise PatentWorkflowError("全文批次编号无效。")
        limit = max(1, min(int(limit), 200))
        with self.pipeline.memory.connect() as db:
            batch = db.execute(
                "SELECT batch_id,total,created_at,updated_at FROM fulltext_batches "
                "WHERE batch_id=?", (batch_id,),
            ).fetchone()
            if batch is None:
                raise PatentWorkflowError("本项目不存在指定全文批次。")
            counts = db.execute(
                "SELECT state,COUNT(*) AS n FROM fulltext_batch_items "
                "WHERE batch_id=? GROUP BY state", (batch_id,),
            ).fetchall()
            rows = db.execute(
                "SELECT doc_id,state,attempts,pdf_sha256,last_error FROM fulltext_batch_items "
                "WHERE batch_id=? ORDER BY ordinal LIMIT ?", (batch_id, limit),
            ).fetchall()
        tally = {r["state"]: r["n"] for r in counts}
        return {
            "batch_id": batch_id, "total": batch["total"],
            "created_at": batch["created_at"], "updated_at": batch["updated_at"],
            "counts": tally, "complete": tally.get("done", 0) == batch["total"],
            "items": [dict(r) for r in rows],
            "truncated": len(rows) < batch["total"],
        }
