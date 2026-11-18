"""Evidence-grounded diagram source, mock worker, and integrity regression."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mechanical_patent.core import PatentWorkflowError
from mechanical_patent.figure_pipeline import prepare_figures, read_figure_plan
from mechanical_patent.figure_worker import render_figures, sync_figures


def sample():
    return {
        "candidate_id": "INV-DEMO-1", "title": "消防泵辅助吸水控制",
        "technical_problem": "入口气塞", "solution": "入口阀与排气阀依次动作",
        "mechanism": "压力达到阈值后切换阀门，效果待验证",
        "expected_effect": "预期减少压力波动", "verification_plan": "低压吸水台架试验",
        "components": [
            {"number": "101", "name": "进水阀", "role": "调节主流量"},
            {"number": "102", "name": "排气阀", "role": "排出气体"},
        ],
        "diagram_relations": [
            {"source": "101", "target": "102", "kind": "hydraulic", "label": "连通支路"},
        ],
        "process_steps": [
            {"trigger": "启泵", "action": "先排气", "result": "降低含气量"},
            {"trigger": "压力稳定", "action": "开启主入口", "result": "进入工作状态"},
        ],
        "sequence_messages": [
            {"sender": "压力传感器", "receiver": "控制器", "message": "入口压力异常"},
            {"sender": "控制器", "receiver": "排气阀", "message": "开启排气", "type": "call"},
        ],
        "innovation_points": [{
            "feature": "双阀时序", "prior_difference": "待核对",
            "technical_effect": "预期减缓气塞", "evidence_ids": [],
        }],
    }


class FigurePipelineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.brief = sample()
        self.path = self.root / "08a_technical_brief.json"
        self.path.write_text(json.dumps(self.brief, ensure_ascii=False), encoding="utf-8")

    def test_generates_editable_sources_without_geometry_claims(self):
        plan = prepare_figures(self.root, candidate_id=self.brief["candidate_id"])
        self.assertEqual([e["kind"] for e in plan["entries"]], ["principle", "flowchart", "sequence"])
        self.assertFalse(plan["filing_authorized"])
        graph = (self.root / plan["entries"][0]["source"]).read_text(encoding="utf-8")
        self.assertIn("<mxfile", graph)
        self.assertIn("101 进水阀", graph)
        self.assertTrue(all(not e["geometry_proven"] for e in plan["entries"]))
        mmd = (self.root / plan["entries"][1]["source"]).read_text(encoding="utf-8")
        self.assertTrue(mmd.startswith("flowchart TD"))
        self.assertIn("S1 --> S2", mmd)
        self.assertEqual(prepare_figures(self.root, candidate_id=self.brief["candidate_id"])["entries"],
                         plan["entries"])

    def test_missing_explicit_links_cannot_generate_structure_or_sequence(self):
        self.brief.pop("diagram_relations")
        self.brief.pop("sequence_messages")
        self.path.write_text(json.dumps(self.brief, ensure_ascii=False), encoding="utf-8")
        plan = prepare_figures(self.root, candidate_id=self.brief["candidate_id"])
        self.assertEqual([e["kind"] for e in plan["entries"]], ["flowchart"])
        self.assertEqual(len(plan["unavailable"]), 2)

    def test_reject_relation_to_undefined_component(self):
        self.brief["diagram_relations"][0]["target"] = "999"
        self.path.write_text(json.dumps(self.brief, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(PatentWorkflowError):
            prepare_figures(self.root, candidate_id=self.brief["candidate_id"])

    def test_mermaid_cannot_inject_newline_commands(self):
        self.brief["process_steps"][0]["action"] = 'open"]\nclick S1 "https://evil.test"'
        self.path.write_text(json.dumps(self.brief, ensure_ascii=False), encoding="utf-8")
        plan = prepare_figures(self.root, candidate_id=self.brief["candidate_id"])
        content = (self.root / plan["entries"][1]["source"]).read_text(encoding="utf-8")
        self.assertNotIn("\nclick S1", content)
        self.assertIn("&quot;", content)

    def test_manifest_source_content_tampering_is_rejected(self):
        plan = prepare_figures(self.root, candidate_id=self.brief["candidate_id"])
        source = self.root / plan["entries"][0]["source"]
        source.write_text("altered", encoding="utf-8")
        with self.assertRaises(PatentWorkflowError):
            read_figure_plan(self.root)
        with self.assertRaises(PatentWorkflowError):
            prepare_figures(self.root, candidate_id=self.brief["candidate_id"])

    def test_render_sync_and_revoke_prior_signatures(self):
        plan = prepare_figures(self.root, candidate_id=self.brief["candidate_id"])
        pdf = b"%PDF-1.6\n" + b"0" * 250 + b"\n%%EOF\n"

        def mocked_binary(args, *, cwd, timeout):
            if "-o" in args:
                dest = Path(args[args.index("-o") + 1])
            else:
                dest = Path(args[args.index("--output") + 1])
            dest.write_bytes(pdf)

        with patch("mechanical_patent.figure_worker._binary", side_effect=lambda name: name), \
                patch("mechanical_patent.figure_worker._run", side_effect=mocked_binary):
            report = render_figures(self.root)
        self.assertEqual(report["status"], "rendered")
        updated = sync_figures(self.root, candidate_id=self.brief["candidate_id"])
        self.assertEqual(updated["status"], "synced")
        self.assertTrue(updated["technical_review_invalidated"])
        self.assertTrue(updated["application_conversion_invalidated"])
        self.assertEqual(len(json.loads(self.path.read_text(encoding="utf-8"))["figures"]), 3)
        self.assertIn(r"\includegraphics", (self.root / "08a_technical_brief.tex").read_text(encoding="utf-8"))
        self.assertEqual(sync_figures(self.root, candidate_id=self.brief["candidate_id"])["status"], "already_synced")
        (self.root / plan["entries"][0]["asset"]).write_bytes(pdf + b"extra")
        with self.assertRaises(PatentWorkflowError):
            sync_figures(self.root, candidate_id=self.brief["candidate_id"])

    def test_failed_worker_cannot_sync(self):
        prepare_figures(self.root, candidate_id=self.brief["candidate_id"])
        with patch("mechanical_patent.figure_worker._binary", return_value="mmdc"), \
                patch("mechanical_patent.figure_worker._run", side_effect=PatentWorkflowError("offline")):
            report = render_figures(self.root)
        self.assertEqual(report["status"], "partial_failure")
        with self.assertRaises(PatentWorkflowError):
            sync_figures(self.root, candidate_id=self.brief["candidate_id"])


if __name__ == "__main__":
    unittest.main()
