"""跨专利、论文、发明构思与工程验证的可追踪技术图谱。

吸收 IdeaForge 的问题/矛盾/技术主张图谱思路，并保留 Trinno 风格的
假设和证伪实验记录。图谱仅表示已入库的关系，不能推出法律创造性。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .core import Evidence, PatentWorkflowError, evidence_id, save_json

NODE_TYPES = frozenset({
    "技术问题", "技术矛盾", "专利文献", "论文文献", "技术原理",
    "发明候选", "技术特征", "反证", "工程假设", "验证实验",
})
EDGE_TYPES = frozenset({
    "来源于", "支持", "反驳", "包含", "采用", "验证", "触发", "引用",
})


@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: str
    title: str
    attributes: dict[str, Any]


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    relation: str
    evidence_id: str = ""


class TechnologyGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []

    def add_node(self, node: GraphNode) -> None:
        if not node.id or node.kind not in NODE_TYPES or not node.title.strip():
            raise PatentWorkflowError("图谱节点缺少合法类型、唯一标识或名称。")
        if node.id in self.nodes:
            raise PatentWorkflowError(f"图谱节点重复：{node.id}")
        self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        if edge.relation not in EDGE_TYPES:
            raise PatentWorkflowError(f"图谱边类型无效：{edge.relation}")
        if edge.source not in self.nodes or edge.target not in self.nodes:
            raise PatentWorkflowError("图谱中出现悬空关系。")
        if edge.evidence_id and edge.evidence_id not in self.nodes:
            raise PatentWorkflowError("图谱关系的来源证据不存在。")
        if edge not in self.edges:
            self.edges.append(edge)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [asdict(n) for n in self.nodes.values()],
            "edges": [asdict(e) for e in self.edges],
            "explanation": (
                "节点间的关系仅来自显式的候选方案和引用字段；"
                "不将语义相似度或多方法共识当作专利法律创造性的证明。"
            ),
            "upstream_ideas": ["IdeaForge：问题—原理—技术特征图谱", "Trinno：假说—证伪试验记录"],
        }


def _read_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PatentWorkflowError(f"无效图谱数据来源：{path.name}")
    return payload


def build_case_graph(case_dir: Path) -> dict[str, Any]:
    """由明确的引用字段构建图谱；无明确来源时只保留待验证候选节点。"""
    folder = Path(case_dir)
    evidence = _read_object(folder / "04_evidence.json").get("records", [])
    ideas = _read_object(folder / "05_inventions.json").get("candidates", [])
    citation_graph = _read_object(folder / "04c_paper_citations.json")
    challenges = _read_object(folder / "06_countersearch.json").get("claim_charts", [])
    engineering = _read_object(folder / "07_engineering.json").get("assessments", [])
    graph = TechnologyGraph()
    known_evidence: set[str] = set()
    for raw in evidence if isinstance(evidence, list) else []:
        if not isinstance(raw, dict):
            continue
        try:
            record = Evidence.from_dict(raw)
        except (KeyError, ValueError, TypeError):
            continue
        if record.kind not in {"paper", "patent"}:
            continue
        source_id = evidence_id(record)
        known_evidence.add(source_id)
        graph.add_node(GraphNode(
            id=source_id, kind="专利文献" if record.kind == "patent" else "论文文献",
            title=record.title, attributes={
                "publication": record.publication, "url": record.url,
                "verified": record.verified, "date": record.publication_date,
            },
        ))
    # 对新发现的 DOI 只标记为引证元数据节点，不伪称读取过论文原文。
    # 已实际取得论文题目/摘要的既有文献节点优先保留，不被外部 DOI 覆盖。
    from .citations import normalize_doi
    citation_nodes = citation_graph.get("nodes", [])
    for node in citation_nodes if isinstance(citation_nodes, list) else []:
        if not isinstance(node, dict):
            continue
        try:
            doi = normalize_doi(str(node.get("doi") or ""))
        except PatentWorkflowError:
            continue
        node_id = "EV-" + sha256(("paper|" + doi.upper()).encode("utf-8")).hexdigest()[:12].upper()
        if node_id not in graph.nodes:
            graph.add_node(GraphNode(
                id=node_id, kind="论文文献", title="DOI：" + doi,
                attributes={
                    "publication": doi, "url": "https://doi.org/" + doi,
                    "verified": False, "citation_metadata_only": True,
                    "source": "opencitations-index-v2",
                    "is_seed": bool(node.get("is_seed", False)),
                },
            ))
    citation_edges = citation_graph.get("edges", [])
    for edge in citation_edges if isinstance(citation_edges, list) else []:
        if not isinstance(edge, dict):
            continue
        try:
            from_doi = normalize_doi(str(edge.get("citing_doi") or ""))
            to_doi = normalize_doi(str(edge.get("cited_doi") or ""))
        except PatentWorkflowError:
            continue
        from_id = "EV-" + sha256(("paper|" + from_doi.upper()).encode("utf-8")).hexdigest()[:12].upper()
        to_id = "EV-" + sha256(("paper|" + to_doi.upper()).encode("utf-8")).hexdigest()[:12].upper()
        if from_id in graph.nodes and to_id in graph.nodes:
            graph.add_edge(GraphEdge(from_id, to_id, "引用"))
    if not isinstance(ideas, list):
        ideas = []
    for i, idea in enumerate(ideas, 1):
        if not isinstance(idea, dict):
            continue
        candidate_id = str(idea.get("id") or f"待编号发明-{i}")
        graph.add_node(GraphNode(
            id=candidate_id, kind="发明候选", title=str(idea.get("title") or candidate_id),
            attributes={
                "method": idea.get("inventive_method", ""),
                "mechanism": idea.get("mechanism", ""),
                "assumptions": idea.get("assumptions", []),
                "status": "待工程/专利双重审核",
            },
        ))
        for source in idea.get("evidence_ids", []) if isinstance(idea.get("evidence_ids"), list) else []:
            if source in known_evidence:
                graph.add_edge(GraphEdge(candidate_id, source, "来源于", source))
        for n, feature in enumerate(idea.get("distinguishing_features", []), 1):
            text = feature if isinstance(feature, str) else str(feature)
            feature_id = f"{candidate_id}-特征{n}"
            graph.add_node(GraphNode(feature_id, "技术特征", text[:260], {}))
            graph.add_edge(GraphEdge(candidate_id, feature_id, "包含"))
    if isinstance(challenges, list):
        for i, chart in enumerate(challenges, 1):
            if not isinstance(chart, dict):
                continue
            candidate = str(chart.get("candidate_id") or "")
            node_id = f"反证-{i}"
            graph.add_node(GraphNode(node_id, "反证", str(chart.get("feature", "待明确反证特征")), {}))
            if candidate in graph.nodes:
                graph.add_edge(GraphEdge(node_id, candidate, "反驳"))
            for entry in chart.get("evidence", []) if isinstance(chart.get("evidence"), list) else []:
                if not isinstance(entry, dict):
                    continue
                source = entry.get("evidence_id")
                if source in known_evidence:
                    graph.add_edge(GraphEdge(node_id, source, "来源于", source))
    if isinstance(engineering, list):
        for i, ass in enumerate(engineering, 1):
            if not isinstance(ass, dict):
                continue
            candidate = str(ass.get("candidate_id") or "")
            for j, test in enumerate(ass.get("falsification_tests", []), 1):
                node_id = f"试验-{i}-{j}"
                graph.add_node(GraphNode(node_id, "验证实验", str(test)[:260], {
                    "status": ass.get("verification_status", "hypothesis_only"),
                }))
                if candidate in graph.nodes:
                    graph.add_edge(GraphEdge(candidate, node_id, "验证"))
    result = graph.to_dict()
    save_json(folder / "04b_technology_graph.json", result)
    return result
