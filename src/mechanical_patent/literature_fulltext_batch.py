"""获授权论文 PDF 批处理：项目级检查点、逐文献失败隔离与重试预算。"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import time
from typing import Any

from .core import PatentWorkflowError, utc_now
from .literature_fulltext import LiteratureFullText, RIGHTS_BASES


class FullTextBatchRunner:
    """单项目 SQLite 检查点。每条论文必须独立提供可审查的版权依据。"""

    def __init__(self, pipeline: LiteratureFullText):
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
    def _validate_manifest(items: Any) -> list[dict[str, Any]]:
        if not isinstance(items, list) or not 1 <= len(items) <= 1000:
            raise PatentWorkflowError("全文批次必须包含1-1000条文献。")
        result = []
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                raise PatentWorkflowError("批次条目须为 JSON 对象。")
            doc_id = item.get("doc_id")
            if not isinstance(doc_id, str) or doc_id in seen:
                raise PatentWorkflowError("批次文献编号缺失或重复。")
            seen.add(doc_id)
            source = item.get("source")
            if source not in {"local", "remote"}:
                raise PatentWorkflowError("来源类型仅允许 local 或 remote。")
            rights = item.get("rights_basis")
            reference = item.get("rights_reference")
            if rights not in RIGHTS_BASES or not isinstance(reference, str):
                raise PatentWorkflowError("缺少已获批的原文许可证与凭据。")
            if source == "local":
                if not isinstance(item.get("input"), str) or not item["input"].strip():
                    raise PatentWorkflowError("本地来源需要 input 路径。")
            else:
                hosts = item.get("allowed_hosts")
                if not isinstance(hosts, list) or not hosts or not all(
                    isinstance(h, str) and h.strip() for h in hosts
                ):
                    raise PatentWorkflowError("远程来源必须明确域名白名单。")
            if not isinstance(item.get("parse", True), bool):
                raise PatentWorkflowError("parse 必须为布尔值。")
            result.append(item)
        return result

    def run(
        self, manifest: dict[str, Any], *, authorized: bool,
        outbound_approved: bool = False,
        artifacts: Path | None = None,
        converter: Any | None = None,
        max_documents: int = 100, max_seconds: int = 900,
        max_total_bytes: int = 2 * 1024 * 1024 * 1024,
        max_attempts: int = 3,
        refresh: bool = False,
    ) -> dict[str, Any]:
        if not authorized:
            raise PatentWorkflowError("全文批量处理必须先取得组织级资料使用授权。")
        if not isinstance(manifest, dict):
            raise PatentWorkflowError("全文清单必须是 JSON 对象。")
        items = self._validate_manifest(manifest.get("items"))
        if not 1 <= max_documents <= 1000:
            raise PatentWorkflowError("每轮最多处理1000个文件。")
        if not 10 <= max_seconds <= 3600:
            raise PatentWorkflowError("批次最长运行时间范围为10-3600秒。")
        if not 1000 <= max_total_bytes <= 10 * 1024 * 1024 * 1024:
            raise PatentWorkflowError("批量 PDF 字节预算范围无效。")
        if not 1 <= max_attempts <= 10:
            raise PatentWorkflowError("每条文献失败重试预算必须在1-10之间。")
        if any(item["source"] == "remote" for item in items) and not outbound_approved:
            raise PatentWorkflowError("批次包含远程 PDF，缺少本轮外发审批。")
        serialized = json.dumps(items, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
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
        done, skipped, failed, bytes_total, processed = 0, 0, 0, 0, 0
        messages: list[dict[str, str]] = []
        began = time.monotonic()
        for item in items:
            if processed >= max_documents or time.monotonic() - began > max_seconds:
                break
            doc_id = item["doc_id"]
            with self.pipeline.memory.connect() as db:
                previous = db.execute(
                    "SELECT state,attempts,pdf_sha256 FROM fulltext_batch_items "
                    "WHERE batch_id=? AND doc_id=?", (batch_id, doc_id),
                ).fetchone()
            if not refresh and previous["state"] == "done":
                state = self.pipeline.status(doc_id)
                if (state.get("pdf_sha256") == previous["pdf_sha256"]
                        and state.get("state") in {"staged", "parsed_unreviewed"}
                        and (not item.get("parse", True) or state["state"] == "parsed_unreviewed")):
                    skipped += 1
                    continue
            if not refresh and previous["attempts"] >= max_attempts:
                skipped += 1
                continue
            if bytes_total >= max_total_bytes:
                break
            processed += 1
            try:
                if item["source"] == "local":
                    state = self.pipeline.import_local(
                        doc_id, Path(item["input"]), authorized=True,
                        rights_basis=item["rights_basis"],
                        rights_reference=item["rights_reference"],
                        source_url=str(item.get("source_url") or ""),
                    )
                else:
                    state = self.pipeline.fetch(
                        doc_id, allowed_hosts=set(item["allowed_hosts"]),
                        authorized=True, rights_basis=item["rights_basis"],
                        rights_reference=item["rights_reference"],
                        outbound_approved=True,
                    )
                pdf = self.pipeline._local(state["pdf_relpath"])
                length = pdf.stat().st_size
                if bytes_total + length > max_total_bytes:
                    raise PatentWorkflowError("本轮文件体量超出预算；可调高授权额度后恢复。")
                bytes_total += length
                if item.get("parse", True) and state["state"] != "parsed_unreviewed":
                    state = self.pipeline.parse(
                        doc_id, authorized=True, artifacts=artifacts,
                        converter=converter,
                    )
                with self.pipeline.memory.connect(write=True) as db:
                    db.execute(
                        "UPDATE fulltext_batch_items SET state='done',attempts=attempts+1,"
                        "pdf_sha256=?,last_error='',updated_at=? WHERE batch_id=? AND doc_id=?",
                        (state["pdf_sha256"], utc_now(), batch_id, doc_id),
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
                messages.append({"doc_id": doc_id, "reason": str(exc)[:180]})
        with self.pipeline.memory.connect() as db:
            rows = db.execute(
                "SELECT state,COUNT(*) AS n FROM fulltext_batch_items "
                "WHERE batch_id=? GROUP BY state", (batch_id,),
            ).fetchall()
        counts = {row["state"]: row["n"] for row in rows}
        complete = counts.get("done", 0) == len(items)
        return {
            "batch_id": batch_id,
            "status": "complete" if complete else "partial",
            "total": len(items), "completed_total": counts.get("done", 0),
            "pending": counts.get("pending", 0),
            "failed_pending_retry": counts.get("failed", 0),
            "processed_this_run": processed, "done_this_run": done,
            "skipped_this_run": skipped, "failed_this_run": failed,
            "bytes_processed_this_run": bytes_total,
            "errors": messages[:50],
            "full_text_verified": False,
        }
