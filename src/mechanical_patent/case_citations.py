"""将学术论文 DOI 引证扩展纳入专利研发案卷，保留每批检索原始证据。"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .audit import append_audit_event, verify_audit_chain
from .citations import OpenCitationsClient, create_citation_graph
from .core import PatentWorkflowError, save_json, utc_now
from .lineage import build_case_graph

MAX_CUMULATIVE_EDGES = 5000
MAX_QUERY_HISTORY = 1000


def _read_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise PatentWorkflowError("旧引证案卷无法读取；拒绝静默覆盖研究证据。") from exc
    if not isinstance(value, dict):
        raise PatentWorkflowError("旧引证案卷格式错误。")
    return value


def update_case_citations(
    case_dir: Path, seed_dois: list[str], *,
    client: OpenCitationsClient | None = None,
    direction: str = "both", max_links: int = 25,
) -> dict[str, Any]:
    """每次检索生成不可覆盖的批次快照，并更新机器可用的合并索引和关联图谱。"""
    case = Path(case_dir)
    intake = case / "00_intake.json"
    if not intake.is_file():
        raise PatentWorkflowError("找不到既有研究案卷；请先运行 research。")
    prior_audit = verify_audit_chain(case)
    if not prior_audit["valid"]:
        raise PatentWorkflowError("事件哈希链异常，禁止追加新的引证检索证据。")
    graph = create_citation_graph(
        seed_dois, client=client, direction=direction, max_links=max_links
    )
    existing = _read_object(case / "04c_paper_citations.json")
    prior_edges = existing.get("edges", [])
    prior_queries = existing.get("queries", [])
    prior_nodes = existing.get("nodes", [])
    if not isinstance(prior_edges, list) or not isinstance(prior_queries, list) or not isinstance(prior_nodes, list):
        raise PatentWorkflowError("旧引证索引结构不合法。")
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    for item in prior_edges + graph["edges"]:
        if isinstance(item, dict) and item.get("citing_doi") and item.get("cited_doi"):
            edges[(item["citing_doi"], item["cited_doi"])] = item
    if len(edges) > MAX_CUMULATIVE_EDGES or len(prior_queries) + len(graph["queries"]) > MAX_QUERY_HISTORY:
        raise PatentWorkflowError("累计引证预算超限，需分案卷或归档历史批次。")
    node_flags: dict[str, bool] = {}
    for item in prior_nodes + graph["nodes"]:
        if isinstance(item, dict) and isinstance(item.get("doi"), str):
            node_flags[item["doi"]] = node_flags.get(item["doi"], False) or bool(item.get("is_seed", False))
    for item in edges.values():
        for key in ("citing_doi", "cited_doi"):
            node_flags.setdefault(item[key], False)
    merged = {
        "schema_version": "1.0",
        "provider": "opencitations-index-v2",
        "updated_at": utc_now(),
        "seed_dois": sorted(set(existing.get("seed_dois", []) + graph["seed_dois"])),
        "nodes": [
            {"doi": doi, "is_seed": seed} for doi, seed in sorted(node_flags.items())
        ],
        "edges": list(edges.values()),
        "queries": prior_queries + graph["queries"],
        "errors": list(existing.get("errors", [])) + graph["errors"],
        "status": "partial" if existing.get("errors") or graph["errors"] else graph["status"],
        "limitations": graph["limitations"],
        "next_doi_candidates": [
            doi for doi in sorted(node_flags) if not node_flags[doi]
        ][:200],
    }

    raw = json.dumps(graph, ensure_ascii=False, sort_keys=True).encode("utf-8")
    snapshot_id = sha256(raw).hexdigest()
    archive_file = case / "citation_batches" / (snapshot_id + ".json")
    if not archive_file.exists():
        save_json(archive_file, graph)
    save_json(case / "04c_paper_citations.json", merged)
    build_case_graph(case)
    append_audit_event(
        case,
        stage="论文检索",
        action="扩展学术引用与被引关系",
        actor="系统工具", role="系统",
        payload={
            "seed_count": len(graph["seed_dois"]),
            "queries": len(graph["queries"]),
            "new_edges": len(graph["edges"]),
            "batch_sha256": snapshot_id,
            "partial": bool(graph["errors"]),
        },
    )
    manifest = _read_object(case / "manifest.json")
    hashes = dict(manifest.get("sha256", {}))
    for name in ("04c_paper_citations.json", "04b_technology_graph.json"):
        hashes[name] = sha256((case / name).read_bytes()).hexdigest()
    save_json(case / "manifest.json", {
        "case_id": manifest.get("case_id"),
        "updated_at": utc_now(), "sha256": hashes,
        "audit_chain_head": verify_audit_chain(case)["head_sha256"],
    })
    return {
        "status": merged["status"],
        "case_dir": str(case),
        "batch_sha256": snapshot_id,
        "total_edges": len(edges), "total_nodes": len(node_flags),
        "new_edges": len(graph["edges"]),
        "query_errors": graph["errors"],
        "next_doi_candidates": len(merged["next_doi_candidates"]),
        "citation_graph_file": "04c_paper_citations.json",
        "technology_graph_file": "04b_technology_graph.json",
        "filing_authorized": False,
    }
