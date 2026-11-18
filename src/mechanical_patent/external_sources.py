"""第三方已授权专利 MCP 的规范化导入：始终撤销未经独立核验的证据状态。"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from .audit import append_audit_event, verify_audit_chain
from .core import Evidence, PatentWorkflowError, coverage, deduplicate, save_json, utc_now
from .lineage import build_case_graph
from .workflow import PatentResearch, _bounded_terms


def create_offline_run(service: Any, case_id: str) -> dict[str, Any]:
    case = service._case(case_id)
    run_id = "RUN-" + uuid4().hex[:16].upper()
    path = service.root / "cases" / case_id / "runs" / run_id
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    PatentResearch(
        None, [], path, memory_root=service.root / "cases" / case_id
    ).run(case["direction"], case_id=case_id)
    return {"case_id": case_id, "run_id": run_id,
            "external_requests_sent": 0, "status": "awaiting_authorized_source_import",
            "filing_authorized": False}


def import_external_sources(service: Any, case_id: str, run_id: str,
                            records: list[dict[str, Any]],
                            patent_queries: list[str] | None,
                            paper_queries: list[str] | None) -> dict[str, Any]:
    folder = service._folder(case_id, run_id)
    if not isinstance(records, list) or not 1 <= len(records) <= 100:
        raise PatentWorkflowError("一次只接收1-100条公开专利或论文记录。")
    if len(json.dumps(records, ensure_ascii=False)) > 500_000:
        raise PatentWorkflowError("一次导入上限500KB。")
    pq, lq = _bounded_terms(patent_queries), _bounded_terms(paper_queries)
    if not pq and not lq:
        raise PatentWorkflowError("须提供已执行过的实际检索式以便审计。")
    incoming = []
    for raw in records:
        if not isinstance(raw, dict):
            raise PatentWorkflowError("文献记录必须是结构化对象。")
        item = dict(raw)
        item["retrieved_at"] = utc_now()
        try:
            parsed = Evidence.from_dict(item, imported=True)
        except (ValueError, KeyError, TypeError) as exc:
            raise PatentWorkflowError("文献缺失必要著录信息或真实 HTTPS 来源。") from exc
        if parsed.kind not in {"patent", "paper"}:
            raise PatentWorkflowError("接口只接收专利或学术论文。")
        incoming.append(parsed)

    paths = {name: folder / name for name in (
        "01_search_plan.json", "02_patents.json", "03_papers.json", "04_evidence.json"
    )}
    data = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items()}
    plan, patent, paper, merged = (data[key] for key in paths)
    plan["patent_queries"] = list(dict.fromkeys(plan.get("patent_queries", []) + pq))
    plan["paper_queries"] = list(dict.fromkeys(plan.get("paper_queries", []) + lq))
    if len(plan["patent_queries"]) > 8 or len(plan["paper_queries"]) > 8:
        raise PatentWorkflowError("每个渠道最多记录8条检索式。")
    old_patents = [Evidence.from_dict(x) for x in patent.get("records", [])]
    old_papers = [Evidence.from_dict(x) for x in paper.get("records", [])]
    old_all = [Evidence.from_dict(x) for x in merged.get("records", [])]
    patents = deduplicate(old_patents + [x for x in incoming if x.kind == "patent"])
    papers = deduplicate(old_papers + [x for x in incoming if x.kind == "paper"])
    all_sources = deduplicate(old_all + incoming)
    patent["records"] = [x.to_dict() for x in patents]
    patent["coverage"] = coverage(patents, patent.get("coverage", {}).get("provider_errors", []))
    patent["provider_queries"] = plan["patent_queries"]
    paper["records"] = [x.to_dict() for x in papers]
    paper["metadata_verified"] = sum(x.verified for x in papers)
    paper["with_abstract"] = sum(bool(x.abstract.strip()) for x in papers)
    paper["provider_queries"] = plan["paper_queries"]
    merged["records"] = [x.to_dict() for x in all_sources]
    merged["counts_by_kind"] = {
        kind: sum(x.kind == kind for x in all_sources)
        for kind in ("patent", "paper", "web", "standard", "manual")
    }
    merged["external_import_status"] = "unverified_requires_original_document_review"

    for name in paths:
        save_json(paths[name], data[name])
    build_case_graph(folder)
    indexed = service.workspace.import_case(folder)
    memory_indexed = service._memory(case_id).ingest_many(incoming)
    append_audit_event(
        folder, stage="专利检索", action="导入第三方待核验文献",
        actor="MCP导入工具", role="系统", payload={
            "received": len(incoming),
            "patents": sum(x.kind == "patent" for x in incoming),
            "papers": sum(x.kind == "paper" for x in incoming),
        },
    )
    hashes = {
        p.name: sha256(p.read_bytes()).hexdigest() for p in folder.glob("*.json")
        if p.name != "manifest.json"
    }
    save_json(folder / "manifest.json", {
        "created_at": utc_now(), "sha256": hashes,
        "audit_chain_head": verify_audit_chain(folder)["head_sha256"],
        "note": "导入文件不自动确认真实性，需人工或独立原文核验。",
    })
    return {"run_id": run_id, "received": len(incoming),
            "indexed": indexed.get("indexed", {}),
            "memory_indexed": memory_indexed, "status": "unverified_imported",
            "source_review_pending": True, "filing_authorized": False}
