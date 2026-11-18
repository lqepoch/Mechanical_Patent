"""证据、技术方案、独立反证和审计链的端到端静态质量测试。"""
import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.audit import append_audit_event, verify_audit_chain
from mechanical_patent.core import PatentWorkflowError, evidence_id, save_json
from mechanical_patent.lineage import build_case_graph
from mechanical_patent.quality import audit_research_case, inspect_research_case
from mechanical_patent.workflow import PatentResearch
from test_workflow import FakeProvider


class QualityAndGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _create_case(self):
        path = self.root / "case"
        PatentResearch(
            FakeProvider("专利模拟接口", "patent"),
            [FakeProvider("学术模拟接口", "paper")], path,
        ).run("消防泵进水口控制", ["pump inlet"], ["hydraulic flow"])
        return path

    def test_incomplete_case_is_blocked_and_audited(self):
        path = self._create_case()
        quality = audit_research_case(path)
        self.assertEqual(quality["status"], "research_incomplete")
        self.assertTrue(quality["issues"])
        self.assertFalse(quality["filing_authorized"])
        self.assertTrue(verify_audit_chain(path)["valid"])
        self.assertEqual(verify_audit_chain(path)["count"], 2)
        self.assertTrue((path / "10_enterprise_quality.json").is_file())
        self.assertTrue((path / "manifest.json").is_file())

    def test_full_evidence_lineage_quality_still_requires_human(self):
        path = self._create_case()
        patents = json.loads((path / "02_patents.json").read_text())["records"]
        papers = json.loads((path / "03_papers.json").read_text())["records"]
        from mechanical_patent.core import Evidence
        pat_id = evidence_id(Evidence.from_dict(patents[0]))
        paper_id = evidence_id(Evidence.from_dict(papers[0]))
        idea = {
            "id": "INV-001", "title": "双阀防空化控制",
            "mechanism": "先调节入口阀再开启排气阀以降低瞬态压力变化",
            "enabling_details": "入口压力传感器接控制器；两阀按时间顺序动作",
            "distinguishing_features": ["入口压力负反馈与两阀顺序动作"],
            "evidence_ids": [pat_id, paper_id],
            "inventive_method": "TRIZ",
            "falsification_tests": ["试验压力阶跃条件并记录入口气泡"],
        }
        save_json(path / "05_inventions.json", {"candidates": [idea]})
        save_json(path / "06_countersearch.json", {
            "claim_charts": [
                {
                    "candidate_id": "INV-001",
                    "feature": "两阀的控制顺序",
                    "evidence": [{"evidence_id": pat_id, "quote": "1. A flow regulating valve"}],
                }
            ],
        })
        save_json(path / "07_engineering.json", {
            "assessments": [
                {
                    "candidate_id": "INV-001",
                    "physical_principle": "控制阀门开度影响流量及压差",
                    "equations_and_units": ["Q=A*v，单位 m3/s"],
                    "assumptions": ["液体密度固定", "管道充满水"],
                    "failure_modes": ["气堵", "传感器故障"],
                    "falsification_tests": ["测量阀动作前后的压力波动"],
                    "verification_status": "hypothesis_only",
                }
            ],
        })
        draft = {
            "title": "一种消防泵的双阀入口控制装置",
            "abstract": "通过可控双阀调节入口压力。",
            "claims": ["1. 一种泵入口控制装置，包括压力传感器及顺序驱动的阀门。"],
            "description": {
                "technical_field": "涉及消防泵控制技术。",
                "background": "传统单阀入口控制易产生较大瞬态变化。",
                "technical_problem": "解决入口压力快速变化问题。",
                "technical_solution": "相应的安装方案：压力传感器连接控制器，阀 A 先动作。",
                "beneficial_effects": "可降低预期压力变化，实际效果有待试验。",
                "embodiments": "相应的安装方案：压力传感器连接控制器，阀 A 先动作。",
                "drawings": "图1为入口双阀结构示意图。",
            },
            "claim_support": [
                {
                    "claim": 1,
                    "specification_passage": "相应的安装方案：压力传感器连接控制器，阀 A 先动作。",
                }
            ],
        }
        save_json(path / "08_application.json", {
            "selected_candidate_id": "INV-001", "draft": draft,
        })
        graph = build_case_graph(path)
        self.assertGreaterEqual(len(graph["nodes"]), 6)
        self.assertTrue(any(x["relation"] == "来源于" for x in graph["edges"]))
        quality = inspect_research_case(path)
        self.assertEqual(quality["issues"], [])
        self.assertEqual(quality["status"], "needs_human_review")
        self.assertEqual(quality["metrics"]["source_anchored_quotes"], 1)
        saved = audit_research_case(path)
        self.assertFalse(saved["filing_authorized"])
        self.assertTrue(verify_audit_chain(path)["valid"])

    def test_tampering_is_detected(self):
        path = self._create_case()
        file = path / "events" / "000001.json"
        payload = json.loads(file.read_text(encoding="utf-8"))
        payload["actor"] = "攻击者试图伪造"
        file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        verification = verify_audit_chain(path)
        self.assertFalse(verification["valid"])
        with self.assertRaises(PatentWorkflowError):
            append_audit_event(
                path, stage="质量审核", action="再次检查",
                actor="系统", role="系统", payload={"reason": "audit test"},
            )


if __name__ == "__main__":
    unittest.main()
