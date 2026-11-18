"""三级专利知识星图：按案卷隔离的 SQLite 物化图与证据相关性。

数据源只能是案卷中已保存的公开文献元数据与显式标注。
词项关联/相似度是检索线索，永远不视为技术事实、法律创造性或侵权判断。
不请求网络、语言模型或远程 embedding API。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any

from .citations import normalize_doi
from .core import Evidence, PatentWorkflowError, evidence_id, save_json, utc_now

SCHEMA_VERSION = "1.0"
MAX_DOCUMENTS = 10000
MAX_JSON_BYTES = 25_000_000
MAX_NODES = 1000
STOP_WORDS = frozenset({
    "the", "and", "for", "with", "from", "that", "are", "this",
    "system", "device", "method", "using", "一种", "装置", "系统", "方法",
})
TECH_TERMS = (
    "消防泵", "离心泵", "真空泵", "汽蚀", "空化", "气液分离", "高海拔",
    "低温", "吸水", "引水", "叶轮", "泵轴", "阀门", "传感器", "控制器",
    "消防车", "副车架", "取力器", "空气悬架", "功率分配", "液压",
    "压力反馈", "流量控制", "机械密封", "换热", "防冻",
    "npsh", "cavitation", "priming", "impeller", "power takeoff",
)
WORDS = re.compile(r"[a-zA-Z][a-zA-Z0-9-]{2,}")
CJK = re.compile(r"[\u4e00-\u9fff]{2,}")
IDENTIFIER = re.compile(r"EV-[0-9A-F]{12}\Z")


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    if path.stat().st_size > MAX_JSON_BYTES:
        raise PatentWorkflowError("图谱输入超过单文件25MB安全上限。")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PatentWorkflowError("图谱输入文件损坏：" + path.name) from exc
    if not isinstance(data, dict):
        raise PatentWorkflowError("图谱输入文件应为对象：" + path.name)
    return data


def _tokenize(text: str) -> Counter[str]:
    """确定性多语种字词检索；中文采用局部 n-gram，未假定分词等于概念事实。"""
    result: Counter[str] = Counter()
    text = text[:14000].lower()
    for token in WORDS.findall(text):
        if token not in STOP_WORDS:
            result[token] += 1
    for term in TECH_TERMS:
        count = text.count(term)
        if count:
            result[term] += min(count, 12) * 3
    for block in CJK.findall(text):
        # 控制噪声及计算量；包含二、三字连续片段以跨中英文摘要寻找相近文本。
        for n in (2, 3):
            for i in range(max(0, len(block) - n + 1)):
                term = block[i:i + n]
                if term not in STOP_WORDS:
                    result[term] += 1
    return Counter(dict(result.most_common(600)))


def _documents(case_dir: Path) -> dict[str, dict[str, Any]]:
    payload = _read(case_dir / "04_evidence.json")
    records = payload.get("records", [])
    if not isinstance(records, list) or len(records) > MAX_DOCUMENTS:
        raise PatentWorkflowError("案卷文献记录非法或超出单案卷1万条预算。")
    documents: dict[str, dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        try:
            item = Evidence.from_dict(raw)
        except (TypeError, KeyError, ValueError):
            continue
        if item.kind not in {"paper", "patent"}:
            continue
        doc_id = evidence_id(item)
        text = "\n".join([item.title, item.abstract, item.claims])
        candidate = {
            "id": doc_id, "kind": item.kind, "title": item.title,
            "publication": item.publication, "url": item.url,
            "date": item.publication_date, "verified": item.verified,
            "source": item.source, "text": text,
            "sha256": sha256(text.encode("utf-8")).hexdigest(),
        }
        previous = documents.get(doc_id)
        if previous is None or (item.verified, len(text)) > (
            previous["verified"], len(previous["text"])
        ):
            documents[doc_id] = candidate
    return documents


def _similarity(tokens: dict[str, Counter[str]], *, top_k: int,
                threshold: float) -> list[tuple[str, str, float]]:
    """TF-IDF 倒排索引产生候选对，避免 O(N²) 全量配对。仅发现文本相关性。"""
    df: Counter[str] = Counter()
    for terms in tokens.values():
        df.update(terms.keys())
    count = len(tokens)
    vectors: dict[str, dict[str, float]] = {}
    inverted: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for doc_id, terms in tokens.items():
        values = {
            term: (1 + math.log(freq)) * (1 + math.log((count + 1) / (1 + df[term])))
            for term, freq in terms.items()
            if count <= 5 or df[term] <= max(3, int(count * 0.30))
        }
        length = math.sqrt(sum(v * v for v in values.values())) or 1.0
        vectors[doc_id] = {term: value / length for term, value in values.items()}
        for term, value in vectors[doc_id].items():
            inverted[term].append((doc_id, value))
    scores: dict[tuple[str, str], float] = defaultdict(float)
    for postings in inverted.values():
        if len(postings) > 3000:
            continue
        for idx, (left, lscore) in enumerate(postings):
            for right, rscore in postings[idx + 1:]:
                pair = (left, right) if left < right else (right, left)
                scores[pair] += lscore * rscore
    per_doc: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for (left, right), score in scores.items():
        if score >= threshold:
            per_doc[left].append((score, right))
            per_doc[right].append((score, left))
    allowed: set[tuple[str, str]] = set()
    for key, neighbors in per_doc.items():
        for _, neighbor in sorted(neighbors, key=lambda x: (-x[0], x[1]))[:top_k]:
            allowed.add(tuple(sorted((key, neighbor))))
    return [(a, b, round(scores[(a, b)], 5)) for a, b in sorted(allowed)]


def _connection(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=15.0)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=15000")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
      CREATE TABLE IF NOT EXISTS nodes (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
        attributes_json TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS edges (
        source TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
        target TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
        relation TEXT NOT NULL, method TEXT NOT NULL,
        score REAL, source_ref TEXT NOT NULL DEFAULT '',
        details_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(source, target, relation, method)
      );
      CREATE TABLE IF NOT EXISTS document_facts (
        fact_id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        subject TEXT NOT NULL, predicate TEXT NOT NULL, object TEXT NOT NULL,
        quote TEXT NOT NULL, location TEXT NOT NULL,
        content_sha256 TEXT NOT NULL, review_status TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS ix_facts_doc ON document_facts(document_id);
      CREATE TABLE IF NOT EXISTS index_meta (
        key TEXT PRIMARY KEY, value TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS ix_edges_source ON edges(source);
      CREATE INDEX IF NOT EXISTS ix_edges_target ON edges(target);
    """)
    return db


def _node(nodes: dict[str, dict[str, Any]], id_: str, kind: str,
          title: str, **attributes: Any) -> None:
    if id_ not in nodes:
        nodes[id_] = {"id": id_, "kind": kind, "title": title,
                      "attributes": attributes}


def _edge(edges: dict[tuple[str, str, str, str], dict[str, Any]],
          src: str, dst: str, relation: str, method: str, *,
          score: float | None = None, source_ref: str = "",
          details: dict[str, Any] | None = None) -> None:
    key = (src, dst, relation, method)
    edges[key] = {"source": src, "target": dst, "relation": relation,
                  "method": method, "score": score, "source_ref": source_ref,
                  "details": details or {}}


FACT_PREDICATES = frozenset({
    "包含", "连接", "控制", "检测", "支撑", "传递", "阻断",
    "改善", "抑制", "驱动", "测量", "依赖", "解决", "属于",
})


def record_document_fact(case_dir: Path, document_id: str, *,
                         subject: str, predicate: str, object: str,
                         quote: str, location: str = "") -> dict[str, Any]:
    """由宿主 AI 提交有原文锚点的候选三元组；引文匹配不等于关系已核实。"""
    case = Path(case_dir)
    if not IDENTIFIER.fullmatch(document_id):
        raise PatentWorkflowError("文献证据编号无效。")
    docs = _documents(case)
    doc = docs.get(document_id)
    if doc is None:
        raise PatentWorkflowError("本案卷未包含对应原始文献。")
    if not isinstance(predicate, str) or predicate not in FACT_PREDICATES:
        raise PatentWorkflowError("技术关系未纳入已审核的谓词表。")
    for value in (subject, object):
        if not isinstance(value, str) or not 2 <= len(value.strip()) <= 120:
            raise PatentWorkflowError("技术实体需为2至120字的可审阅文本。")
    if not isinstance(quote, str) or not 6 <= len(quote.strip()) <= 600:
        raise PatentWorkflowError("必须提供6至600字的原文引句。")
    if not isinstance(location, str) or len(location) > 120:
        raise PatentWorkflowError("原文位置字段长度超限。")
    norm = lambda s: " ".join(s.split()).casefold()
    if norm(quote) not in norm(doc["text"]):
        raise PatentWorkflowError("原文引文在当前已存标题、摘要或权利要求中不可核对。")
    value = [document_id, subject.strip(), predicate, object.strip(), norm(quote)]
    fact_id = "FACT-" + sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()[:20]
    with _connection(case / "knowledge.sqlite3") as db:
        db.execute(
            "INSERT OR IGNORE INTO document_facts VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fact_id, document_id, subject.strip(), predicate, object.strip(),
             quote.strip(), location.strip(), doc["sha256"], "AI待人工复核"),
        )
        db.commit()
    return {"fact_id": fact_id, "document_id": document_id,
            "quote_matches_archived_text": True,
            "technical_relation_verified": False,
            "legal_novelty_verified": False,
            "next_action": "须核查原始公开文件页码/权要及技术关系，再由工程师审阅。"}


def _doc_memory(case: Path, documents: dict[str, dict[str, Any]],
                tokens: dict[str, Counter[str]], relations: list[dict[str, Any]]) -> None:
    folder = case / "document_memory" / "generated"
    folder.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in relations:
        if edge["relation"] in {"文本相似", "引用"}:
            grouped[edge["source"]].append(edge)
            grouped[edge["target"]].append(edge)
    for doc_id, doc in sorted(documents.items()):
        # 不写入原始全文，不覆盖人工维护的 document_memory/manual 目录。
        clean = lambda x: str(x).replace("\n", " ").replace("\r", " ").replace("|", "/")[:350]
        lines = [
            "# " + clean(doc["title"]), "",
            "- 文献 ID：" + doc_id,
            "- 类型：" + ("专利" if doc["kind"] == "patent" else "论文"),
            "- 公开号 / DOI：" + clean(doc["publication"]),
            "- 来源：" + clean(doc["url"]),
            "- 原文核验：" + ("已标注核验" if doc["verified"] else "待独立核验"),
            "- 内容摘要指纹：sha256:" + doc["sha256"],
            "- 说明：机器生成索引，非人工证据判定；每次重建更新本文件。", "",
            "## 自动归纳的词项（文本统计，待语义复核）", "",
            ", ".join(t for t, _ in tokens[doc_id].most_common(15)) or "暂无", "",
            "## 图谱邻接文献", "",
        ]
        for edge in sorted(grouped[doc_id],
                           key=lambda e: (-(e["score"] or 0), e["target"]))[:12]:
            other = edge["target"] if edge["source"] == doc_id else edge["source"]
            if other in documents:
                lines.append("- " + clean(documents[other]["title"]) +
                             " [" + other + "]：" + edge["relation"] +
                             (f"（词项相似度 {edge['score']:.3f}）"
                              if edge["score"] is not None else "（已记录引用）"))
        lines += ["", "## 人工技术归纳", "",
                  "请将已核查的机理、权项/页码、创新迁移判断及其来源"
                  "写在 document_memory/manual/" + doc_id + ".md；自动流程不会覆盖。", ""]
        (folder / (doc_id + ".md")).write_text("\n".join(lines), encoding="utf-8")


def index_case_atlas(case_dir: Path, *, top_k: int = 8,
                     threshold: float = 0.15) -> dict[str, Any]:
    case = Path(case_dir)
    if not (case / "00_intake.json").is_file():
        raise PatentWorkflowError("知识星图只能基于真实已有研究案卷构建。")
    if not 1 <= top_k <= 25 or not 0.0 < threshold <= 1.0:
        raise PatentWorkflowError("相似图谱参数不合法。")
    docs = _documents(case)
    tokens = {doc_id: _tokenize(d["text"]) for doc_id, d in docs.items()}
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    with _connection(case / "knowledge.sqlite3") as stored:
        facts = [dict(row) for row in stored.execute(
            "SELECT * FROM document_facts ORDER BY fact_id")]
    for doc_id, doc in sorted(docs.items()):
        _node(nodes, doc_id, "专利文献" if doc["kind"] == "patent" else "论文文献",
              doc["title"], publication=doc["publication"], url=doc["url"],
              verified=doc["verified"], date=doc["date"], source=doc["source"],
              content_sha256=doc["sha256"])
        for term, _ in tokens[doc_id].most_common(12):
            concept_id = "TERM-" + sha256(term.encode("utf-8")).hexdigest()[:16]
            _node(nodes, concept_id, "候选词项", term, provenance="deterministic_text_extraction")
            _edge(edges, doc_id, concept_id, "提及词项", "lexical", source_ref=doc_id)
    for left, right, score in _similarity(tokens, top_k=top_k, threshold=threshold):
        _edge(edges, left, right, "文本相似", "tfidf_cosine",
              score=score, details={"status": "algorithmic_candidate_not_legal_evidence"})
    cited = _read(case / "04c_paper_citations.json")
    doi_ids: dict[str, str] = {}
    for doc_id, doc in docs.items():
        if doc["kind"] == "paper":
            try:
                doi_ids[normalize_doi(doc["publication"])] = doc_id
            except PatentWorkflowError:
                continue
    for ref in cited.get("edges", []):
        if not isinstance(ref, dict):
            continue
        try:
            src = doi_ids.get(normalize_doi(str(ref.get("citing_doi", ""))))
            dst = doi_ids.get(normalize_doi(str(ref.get("cited_doi", ""))))
        except PatentWorkflowError:
            continue
        if src and dst:
            _edge(edges, src, dst, "引用", "opencitations",
                  source_ref="04c_paper_citations.json",
                  details={"status": "citation_metadata_only"})
    # 继承已存在的技术图谱中明确归属关系；禁止臆造新技术机理事实。
    lineage = _read(case / "04b_technology_graph.json")
    for node in lineage.get("nodes", []):
        if not isinstance(node, dict):
            continue
        key, kind, title = node.get("id"), node.get("kind"), node.get("title")
        if (isinstance(key, str) and isinstance(kind, str) and
                isinstance(title, str) and len(key) <= 200):
            _node(nodes, key, kind, title, **(node.get("attributes") if
                  isinstance(node.get("attributes"), dict) else {}))
    for edge in lineage.get("edges", []):
        if not isinstance(edge, dict):
            continue
        src, dst, relation = edge.get("source"), edge.get("target"), edge.get("relation")
        if src in nodes and dst in nodes and isinstance(relation, str):
            _edge(edges, src, dst, relation, "existing_lineage",
                  source_ref=str(edge.get("evidence_id") or "04b_technology_graph.json"))
    for fact in facts:
        doc_id = fact["document_id"]
        if doc_id not in docs or fact["content_sha256"] != docs[doc_id]["sha256"]:
            continue
        subject_id = "CONCEPT-" + sha256(fact["subject"].encode()).hexdigest()[:16]
        object_id = "CONCEPT-" + sha256(fact["object"].encode()).hexdigest()[:16]
        _node(nodes, subject_id, "候选技术实体", fact["subject"],
              provenance="quote_matched_ai_extraction")
        _node(nodes, object_id, "候选技术实体", fact["object"],
              provenance="quote_matched_ai_extraction")
        _edge(edges, doc_id, subject_id, "提及候选技术实体", "ai_review_pending",
              source_ref=doc_id, details={"fact_id": fact["fact_id"]})
        _edge(edges, subject_id, object_id, fact["predicate"], "ai_review_pending",
              source_ref=doc_id, details={"fact_id": fact["fact_id"],
              "quote": fact["quote"], "location": fact["location"],
              "review_status": "AI待人工复核"})
    digest = sha256(json.dumps({
        "facts": facts,
        "docs": {k: d["sha256"] for k, d in sorted(docs.items())},
        "citations": cited.get("edges", []), "lineage": lineage,
        "top_k": top_k, "threshold": threshold,
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    dbpath = case / "knowledge.sqlite3"
    with _connection(dbpath) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            current = db.execute(
                "SELECT value FROM index_meta WHERE key='digest'").fetchone()
            if current and current["value"] == digest:
                db.commit()
                return {"status": "unchanged", "documents": len(docs),
                        "nodes": len(nodes), "edges": len(edges),
                        "database": str(dbpath), "digest": digest}
            db.execute("DELETE FROM edges")
            db.execute("DELETE FROM nodes")
            db.executemany("INSERT INTO nodes VALUES (?, ?, ?, ?)",
                [(n["id"], n["kind"], n["title"],
                  json.dumps(n["attributes"], ensure_ascii=False, sort_keys=True))
                 for n in nodes.values()])
            db.executemany("INSERT INTO edges VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(e["source"], e["target"], e["relation"], e["method"],
                  e["score"], e["source_ref"],
                  json.dumps(e["details"], ensure_ascii=False, sort_keys=True))
                 for e in edges.values()])
            db.execute("INSERT OR REPLACE INTO index_meta VALUES('digest', ?)", (digest,))
            db.execute("INSERT OR REPLACE INTO index_meta VALUES('updated_at', ?)", (utc_now(),))
            db.execute("INSERT OR REPLACE INTO index_meta VALUES('schema_version', ?)",
                       (SCHEMA_VERSION,))
            db.commit()
        except Exception:
            db.rollback()
            raise
    # 只在数据库提交成功后重建派生 Markdown，不修改原始案卷数据。
    _doc_memory(case, docs, tokens, list(edges.values()))
    return {"status": "indexed", "documents": len(docs), "nodes": len(nodes),
            "edges": len(edges), "database": str(dbpath), "digest": digest}


def _present(scope: str, nodes: list[dict[str, Any]],
             edges: list[dict[str, Any]], *, total_nodes: int,
             digest: str = "") -> dict[str, Any]:
    data = {
        "schema_version": SCHEMA_VERSION, "scope": scope,
        "nodes": nodes, "edges": edges,
        "total_nodes": total_nodes, "truncated": total_nodes > len(nodes),
        "index_digest": digest,
        "disclaimer": "相似、共词及推断关系仅用于文献发现，不能证明新颖性、创造性、侵权或因果关系。",
    }
    data["elements"] = {
        "nodes": [{"data": {"id": n["id"], "label": n["title"],
                            "kind": n["kind"], **n["attributes"]}}
                  for n in nodes],
        "edges": [{"data": {"id": "EDGE-" + sha256(
                        (e["source"] + "|" + e["target"] + "|" +
                         e["relation"] + "|" + e["method"]).encode("utf-8")
                        ).hexdigest()[:16],
                            **e}} for e in edges],
    }
    return data


def case_atlas(case_dir: Path, *, scope: str = "project",
               document_id: str = "", max_nodes: int = 250,
               min_score: float = 0.0) -> dict[str, Any]:
    if scope not in {"project", "document"} or not 1 <= max_nodes <= MAX_NODES:
        raise PatentWorkflowError("图谱范围或节点上限无效。")
    if not 0 <= min_score <= 1:
        raise PatentWorkflowError("相似度阈值需在0至1之间。")
    dbpath = Path(case_dir) / "knowledge.sqlite3"
    if not dbpath.is_file():
        raise PatentWorkflowError("图谱尚未索引；请先运行 atlas-index / patent_knowledge_index。")
    with _connection(dbpath) as db:
        rows = db.execute("SELECT * FROM nodes ORDER BY id").fetchall()
        nodes = [{"id": r["id"], "kind": r["kind"], "title": r["title"],
                  "attributes": json.loads(r["attributes_json"])} for r in rows]
        relations = db.execute("SELECT * FROM edges ORDER BY source,target,relation").fetchall()
        edges = [{"source": r["source"], "target": r["target"],
                  "relation": r["relation"], "method": r["method"],
                  "score": r["score"], "source_ref": r["source_ref"],
                  "details": json.loads(r["details_json"])} for r in relations
                 if r["score"] is None or r["score"] >= min_score]
        digest_row = db.execute("SELECT value FROM index_meta WHERE key='digest'").fetchone()
    if scope == "document":
        if not IDENTIFIER.fullmatch(document_id):
            raise PatentWorkflowError("单文档查询须指定真实 EV-xxxxxxxxxxxx 证据编号。")
        known = {n["id"] for n in nodes}
        if document_id not in known:
            raise PatentWorkflowError("请求的证据未出现在本项目知识星图。")
        adjacent = [e for e in edges if document_id in (e["source"], e["target"])]
        chosen = {document_id}
        for e in sorted(adjacent, key=lambda x: (-(x["score"] or 0), x["target"])):
            other = e["target"] if e["source"] == document_id else e["source"]
            if len(chosen) >= max_nodes:
                break
            chosen.add(other)
    else:
        # 每个项目保留所有专利与论文优先，不允许主题词淹没文献节点。
        selected = sorted(nodes, key=lambda n: (
            0 if n["id"].startswith("EV-") else
            1 if n["kind"] == "发明候选" else 2,
            n["id"],
        ))[:max_nodes]
        chosen = {n["id"] for n in selected}
    visible = [n for n in nodes if n["id"] in chosen]
    visible_edges = [e for e in edges if e["source"] in chosen and e["target"] in chosen]
    return _present(scope, visible, visible_edges, total_nodes=len(nodes),
                    digest=digest_row["value"] if digest_row else "")


def global_public_atlas(workspace_dir: Path, *, max_nodes: int = 250) -> dict[str, Any]:
    """公开发布投影，绝不扫描秘密/内部案卷；企业共享需另接真实身份 ABAC。"""
    if not 1 <= max_nodes <= MAX_NODES:
        raise PatentWorkflowError("全局星图节点预算无效。")
    root = Path(workspace_dir).resolve()
    database = root / "index.sqlite3"
    if not database.is_file():
        raise PatentWorkflowError("工作区尚不存在授权索引。")
    with sqlite3.connect(str(database)) as conn:
        public = {row[0] for row in conn.execute(
            "SELECT case_id FROM cases WHERE confidentiality='公开'")}
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    seen: dict[str, list[str]] = defaultdict(list)
    cases_root = root / "cases"
    for case_id in sorted(public):
        run_root = cases_root / case_id / "runs"
        if not run_root.is_dir() or run_root.is_symlink():
            continue
        for folder in sorted(run_root.glob("RUN-*")):
            if folder.is_symlink() or not folder.is_dir():
                continue
            if not folder.resolve().is_relative_to(run_root.resolve()):
                continue
            if not (folder / "knowledge.sqlite3").is_file():
                continue
            run_id = folder.name
            project_node = "CASE-" + sha256(case_id.encode()).hexdigest()[:16]
            _node(nodes, project_node, "公开项目", case_id, visibility="public")
            with _connection(folder / "knowledge.sqlite3") as conn:
                for row in conn.execute(
                    "SELECT id,kind,title,attributes_json FROM nodes WHERE kind IN ('专利文献','论文文献')"):
                    item = json.loads(row["attributes_json"])
                    # 公共图只保留公开文献的著录字段；不带任何摘要、发明构思或私密路径。
                    global_id = project_node + ":" + row["id"]
                    _node(nodes, global_id, row["kind"], row["title"],
                          publication=item.get("publication", ""),
                          url=item.get("url", ""), verified=item.get("verified", False),
                          visibility="public", run_id=run_id)
                    _edge(edges, project_node, global_id, "包含公开文献", "project_membership")
                    key = (row["kind"] + "|" + str(item.get("publication", "")).upper())
                    seen[key].append(global_id)
    for ids in seen.values():
        unique = sorted(set(ids))
        # 共用文献属于“同一文献”关系，不代表项目之间的商业/技术授权。
        for a, b in zip(unique, unique[1:]):
            _edge(edges, a, b, "同一公开文献", "same_publication")
    all_nodes = sorted(nodes.values(), key=lambda x: (
        0 if x["kind"] == "公开项目" else 1, x["id"]))
    visible = all_nodes[:max_nodes]
    selected = {n["id"] for n in visible}
    visible_edges = [e for e in edges.values()
                     if e["source"] in selected and e["target"] in selected]
    return _present("global_public", visible, visible_edges,
                    total_nodes=len(nodes))
