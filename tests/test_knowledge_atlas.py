"""三级文献知识星图离线回归：证据、相似度、稳定索引、保密分区。"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from mechanical_patent.core import PatentWorkflowError, evidence_id, Evidence, save_json
from mechanical_patent.knowledge_atlas import (
    case_atlas, global_public_atlas, index_case_atlas, record_document_fact,
)


def record(identifier: str, title: str, kind: str = "patent", verified: bool = False):
    return {
        "publication": identifier, "title": title,
        "url": "https://example.org/" + identifier.replace("/", "_"),
        "source": "test-offline", "retrieved_at": "2026-11-18T00:00:00+00:00",
        "abstract": "消防泵 气液分离 结构 高海拔 NPSH 验证" if "消防泵" in title else
                    "液压 传动 取力器 空气悬架 压力反馈",
        "claims": "1. 包括机械密封与引水结构。" if kind == "patent" else "",
        "kind": kind, "verified": verified,
    }


class KnowledgeAtlasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.case = self.root / "PUMP" / "runs" / "RUN-ONE"
        self.case.mkdir(parents=True)
        self.docs = [
            record("CN111111111A", "高海拔消防泵的气液分离结构"),
            record("CN222222222A", "消防泵引水汽蚀控制装置"),
            record("10.1234/pump", "消防泵流体动力机理研究", kind="paper"),
            record("CN333333333A", "车辆取力器与空气悬架结构"),
        ]
        save_json(self.case / "00_intake.json", {"case_id": "PUMP"})
        save_json(self.case / "04_evidence.json", {"records": self.docs})
        save_json(self.case / "04b_technology_graph.json", {
            "nodes": [], "edges": [],
        })
        db = sqlite3.connect(self.root / "index.sqlite3")
        db.execute("CREATE TABLE cases (case_id TEXT, confidentiality TEXT)")
        db.execute("INSERT INTO cases VALUES ('PUMP','秘密')")
        db.execute("INSERT INTO cases VALUES ('PUBLIC','公开')")
        db.commit()
        db.close()

    def test_index_document_neighbors_memory_and_stable_digest(self):
        result = index_case_atlas(self.case, threshold=0.1)
        self.assertEqual(result["status"], "indexed")
        self.assertEqual(result["documents"], 4)
        again = index_case_atlas(self.case, threshold=0.1)
        self.assertEqual(again["status"], "unchanged")
        self.assertEqual(result["digest"], again["digest"])
        doc_id = evidence_id(Evidence.from_dict(self.docs[0]))
        view = case_atlas(self.case, scope="document", document_id=doc_id)
        self.assertEqual(view["scope"], "document")
        self.assertIn(doc_id, [n["id"] for n in view["nodes"]])
        self.assertTrue(view["edges"])
        self.assertTrue(all(x["source"] in {n["id"] for n in view["nodes"]}
                            for x in view["edges"]))
        generated = self.case / "document_memory" / "generated" / (doc_id + ".md")
        self.assertTrue(generated.is_file())
        self.assertIn("人工技术归纳", generated.read_text(encoding="utf-8"))

    def test_derived_memory_does_not_overwrite_manual(self):
        doc_id = evidence_id(Evidence.from_dict(self.docs[0]))
        manual = self.case / "document_memory" / "manual" / (doc_id + ".md")
        manual.parent.mkdir(parents=True)
        manual.write_text("人工技术假设，只供本案卷", encoding="utf-8")
        index_case_atlas(self.case)
        self.assertEqual(manual.read_text(encoding="utf-8"), "人工技术假设，只供本案卷")

    def test_global_public_does_not_reveal_secret(self):
        index_case_atlas(self.case)
        private = global_public_atlas(self.root)
        self.assertEqual(private["nodes"], [])
        public_case = self.root / "cases" / "PUBLIC" / "runs" / "RUN-ONE"
        public_case.mkdir(parents=True)
        save_json(public_case / "00_intake.json", {"case_id": "PUBLIC"})
        save_json(public_case / "04_evidence.json", {"records": [
            record("CN999999999A", "公开液压装置"),
        ]})
        index_case_atlas(public_case)
        global_view = global_public_atlas(self.root)
        self.assertTrue(global_view["nodes"])
        rendered = json.dumps(global_view, ensure_ascii=False)
        self.assertNotIn("高海拔消防泵", rendered)
        self.assertNotIn("PUMP", rendered)
        self.assertIn("CN999999999A", rendered)

    def test_document_and_budget_safety(self):
        index_case_atlas(self.case)
        with self.assertRaises(PatentWorkflowError):
            case_atlas(self.case, scope="document", document_id="../../index.sqlite3")
        with self.assertRaises(PatentWorkflowError):
            case_atlas(self.case, scope="project", max_nodes=1001)
        with self.assertRaises(PatentWorkflowError):
            index_case_atlas(self.case, threshold=-1)
        with self.assertRaises(PatentWorkflowError):
            case_atlas(self.case, scope="project", min_score=2.0)

    def test_document_facts_require_actual_quote_and_remain_unverified(self):
        doc_id = evidence_id(Evidence.from_dict(self.docs[0]))
        original = self.docs[0]["claims"]
        with self.assertRaises(PatentWorkflowError):
            record_document_fact(
                self.case, doc_id, subject="机械密封", predicate="包含",
                object="引水结构", quote="编造的不存在证据段落"
            )
        result = record_document_fact(
            self.case, doc_id, subject="机械密封", predicate="包含",
            object="引水结构", quote=original, location="权利要求1"
        )
        self.assertTrue(result["quote_matches_archived_text"])
        self.assertFalse(result["technical_relation_verified"])
        index_case_atlas(self.case)
        view = case_atlas(self.case, scope="project", max_nodes=100)
        candidates = [edge for edge in view["edges"]
                      if edge["method"] == "ai_review_pending"]
        self.assertTrue(candidates)
        self.assertTrue(all(edge["source_ref"] == doc_id for edge in candidates))
        with self.assertRaises(PatentWorkflowError):
            record_document_fact(
                self.case, doc_id, subject="密封", predicate="发明具有创造性",
                object="引水", quote=original
            )

    def test_model_relations_never_equate_to_patentability(self):
        result = index_case_atlas(self.case, threshold=0.01)
        view = case_atlas(self.case, max_nodes=100)
        self.assertEqual(result["documents"], 4)
        for edge in view["edges"]:
            if edge["relation"] == "文本相似":
                self.assertEqual(edge["method"], "tfidf_cosine")
                self.assertIn("not_legal_evidence", edge["details"]["status"])
        self.assertIn("不能证明", view["disclaimer"])


if __name__ == "__main__":
    unittest.main()
