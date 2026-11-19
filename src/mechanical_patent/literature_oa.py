"""经案卷审批的 DOI → Unpaywall OA 候选补全；只写项目私有文献库。"""
from __future__ import annotations

import json
import re
from typing import Any

from .core import Evidence, PatentWorkflowError, utc_now
from .literature_memory import LiteratureMemoryStore
from .paper_sources import UnpaywallEnricher


def enrich_unpaywall(
    memory: LiteratureMemoryStore, doc_id: str, *,
    authorized: bool, provider: Any | None = None,
) -> dict[str, Any]:
    """Caller must also enforce case/project approval before invoking.

    URL discovery is metadata-only. This tool NEVER downloads the article or
    grants a license; FulltextPipeline.queue rechecks provider OA + license.
    """
    if not authorized:
        raise PatentWorkflowError("Unpaywall 查询缺少明确的外发授权。")
    if not isinstance(doc_id, str) or not re.fullmatch(r"EV-[0-9A-F]{12}", doc_id):
        raise PatentWorkflowError("无效的论文证据编号。")
    with memory.connect() as db:
        row = db.execute(
            "SELECT kind,publication,title,source,source_url,published_at,"
            "metadata_verified,abstract,pdf_url,metadata_json "
            "FROM documents WHERE doc_id=?", (doc_id,),
        ).fetchone()
    if row is None or row["kind"] != "paper":
        raise PatentWorkflowError("未找到项目知识库中指定的论文。")
    meta = json.loads(row["metadata_json"] or "{}")
    doi = str(meta.get("doi") or row["publication"]).strip().lower()
    if not re.fullmatch(r"10\.[0-9]{4,9}/\S+", doi):
        raise PatentWorkflowError("该文献没有标准 DOI；不能以原生编号调用 Unpaywall。")
    evidence = Evidence(
        kind="paper", publication=row["publication"], title=row["title"],
        url=row["source_url"], source=row["source"], retrieved_at=utc_now(),
        abstract=row["abstract"], publication_date=row["published_at"],
        verified=bool(row["metadata_verified"]), pdf_url=row["pdf_url"],
        paper_metadata=meta,
    )
    result = (provider or UnpaywallEnricher()).enrich(evidence)
    memory.ingest_many([result])
    return {
        "doc_id": doc_id, "doi": doi, "pdf_url": result.pdf_url,
        "oa_status": result.paper_metadata.get("oa_status") or "",
        "license": result.paper_metadata.get("license") or "",
        "full_text_verified": False,
        "download_authorized": False,
        "notice": "发现的候选地址不表示已获取、已阅读或具备再分发许可。",
    }
