"""可恢复、配额受控的多源文献批量发现。

发现/保存与 AI 理解分离：检索到一篇文献立即落库并写 MD；
断线后保留完整批次记录，未完成检索不得冒充全球检索完成。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import time
from typing import Any

from .core import Evidence, PatentWorkflowError
from .literature_memory import LiteratureMemoryStore


@dataclass(frozen=True)
class HarvestBudget:
    max_documents: int = 1000
    page_size: int = 100
    max_pages: int = 30
    max_seconds: int = 600

    def __post_init__(self) -> None:
        if not 1 <= self.max_documents <= 10000:
            raise PatentWorkflowError("每个检索词的文献预算须在1至10000条之间。")
        if not 1 <= self.page_size <= 100:
            raise PatentWorkflowError("每次请求最多100条文献。")
        if not 1 <= self.max_pages <= 200:
            raise PatentWorkflowError("每个检索词最多200页。")
        if not 10 <= self.max_seconds <= 3600:
            raise PatentWorkflowError("检索时间预算须在10至3600秒之间。")


class LiteratureHarvester:
    def __init__(self, memory: LiteratureMemoryStore):
        self.memory = memory

    @staticmethod
    def _checkpoint_id(provider_name: str, query: str) -> str:
        return sha256((provider_name + "\x00" + query.strip()).encode("utf-8")).hexdigest()

    def harvest(
        self, provider: Any, query: str, *,
        budget: HarvestBudget | None = None, refresh: bool = False,
    ) -> dict[str, Any]:
        """恢复已保存游标；Crossref 老游标失效后通过幂等去重从第一页重检。"""
        limits = budget or HarvestBudget()
        if not query or len(query.strip()) > 240:
            raise PatentWorkflowError("检索词不能为空且不得超过240字符。")
        if not hasattr(provider, "search_page"):
            raise PatentWorkflowError("供应商缺少受控分页接口。")
        name = str(getattr(provider, "name", "unknown"))
        key = self._checkpoint_id(name, query)
        checkpoint = self.memory.get_checkpoint(key)
        resumed = False
        pages, records, cursor = 0, 0, "*"
        if checkpoint and not refresh:
            try:
                age = (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(checkpoint["updated_at"])
                ).total_seconds()
            except (TypeError, ValueError):
                age = float("inf")
            if checkpoint["state"] == "complete" and age < 86400:
                return {
                    "provider": name, "query_sha256": key,
                    "status": "cached_complete", "pages": checkpoint["pages"],
                    "records_seen": checkpoint["records"], "new": 0,
                    "updated": 0, "unchanged": 0, "resumed": False,
                }
            if checkpoint["state"] == "partial" and age < 240:
                cursor = checkpoint["cursor"] or "*"
                pages, records = checkpoint["pages"], checkpoint["records"]
                resumed = True

        new, updated, unchanged = 0, 0, 0
        started = time.monotonic()
        state, failure = "partial", ""
        previous = None
        local_pages = 0
        while (
            records < limits.max_documents
            and local_pages < limits.max_pages
            and time.monotonic() - started < limits.max_seconds
        ):
            requested = min(limits.page_size, limits.max_documents - records)
            # EPO OPS 官方对检索请求有更严格的公平使用限制：单页≤20。
            if name == "epo-ops":
                requested = min(requested, 20)
                if local_pages:
                    time.sleep(6.2)
            try:
                page = provider.search_page(query, cursor=cursor, limit=requested)
                incoming = page.get("records", [])
                if not isinstance(incoming, list) or any(
                    not isinstance(item, Evidence) for item in incoming
                ):
                    raise PatentWorkflowError("供应商返回无效文献列表。")
                if len(incoming) > requested:
                    raise PatentWorkflowError("供应商超出单页采集预算。")
                counts = self.memory.ingest_many(incoming)
                new += counts["new"]
                updated += counts["updated"]
                unchanged += counts["unchanged"]
                local_pages += 1
                pages += 1
                records += len(incoming)
                next_cursor = page.get("next_cursor")
                if next_cursor is not None and (
                    not isinstance(next_cursor, str) or len(next_cursor) > 4096
                ):
                    raise PatentWorkflowError("供应商返回的游标无效。")
                if not incoming or not next_cursor:
                    state, cursor = "complete", None
                else:
                    if next_cursor in {previous, cursor}:
                        raise PatentWorkflowError("供应商分页游标未前进，阻止重复抓取。")
                    previous, cursor = cursor, next_cursor
                self.memory.save_checkpoint(
                    key, name, query.strip(), cursor, pages, records, state,
                )
                if state == "complete":
                    break
            except (PatentWorkflowError, OSError, ValueError) as exc:
                failure = str(exc)[:300]
                state = "failed"
                self.memory.save_checkpoint(
                    key, name, query.strip(), cursor, pages, records, state, failure,
                )
                break
        return {
            "provider": name, "query_sha256": key, "status": state,
            "pages": pages, "records_seen": records, "new": new,
            "updated": updated, "unchanged": unchanged,
            "resumed": resumed, "error": failure,
            "global_exhaustiveness_confirmed": False,
        }
