"""工程可读方案、模板组合与 TeX 输入边界测试。"""
import tempfile
from pathlib import Path
import unittest

from mechanical_patent.core import PatentWorkflowError
from mechanical_patent.technical_brief import render_brief, tex_escape, validate_brief


def brief():
    return {
        "candidate_id": "INV-A1", "title": "消防泵#1结构%测试",
        "technical_problem": "入口形成气塞", "solution": "联动结构",
        "mechanism": "机械阀与传感器按工况动作",
        "expected_effect": "预计减小压力波动，尚未实测",
        "verification_plan": "实施低压试验并记录入口压力",
        "components": [{"number": "101", "name": "入口阀", "role": "改变进水口压力"}],
        "process_steps": [{"trigger": "启泵", "action": "开启旁路", "result": "排气"}],
        "innovation_points": [{"feature": "两阀顺序动作", "prior_difference": "需全文对比",
                               "technical_effect": "理论上减小气塞", "evidence_ids": ["EV-A1"]}],
        "prior_art": [{"evidence_id": "EV-A1", "known_solution": "已有排气方案",
                       "difference": "联动动作阈值不同"}],
        "risks": [{"failure": "泄漏", "mitigation": "压力测试"}],
        "figures": [{"kind": "structure", "caption": "结构图", "asset": ""}],
        "profile": "auto",
    }


class BriefTests(unittest.TestCase):
    def test_only_requested_modules_render(self):
        with tempfile.TemporaryDirectory() as folder:
            data = brief()
            document, result = render_brief(data, Path(folder), known_evidence={"EV-A1"})
            self.assertEqual(result["profile"], "hybrid")
            self.assertIn(r"\section{结构和接口说明}", document)
            self.assertIn(r"\section{执行步骤与条件逻辑}", document)
            self.assertIn(r"\section{待补图纸清单}", document)
            self.assertIn(r"\section{相关公开技术与差异}", document)
            self.assertIn(r"\#1", document)
            self.assertIn(r"\%测试", document)
            self.assertNotIn("权利要求书", document)
            self.assertFalse(result["application_authorized"])

    def test_control_profile_skips_mechanical_table(self):
        with tempfile.TemporaryDirectory() as folder:
            data = brief()
            data.pop("components")
            data.pop("figures")
            data.pop("risks")
            data.pop("prior_art")
            document, result = render_brief(data, Path(folder), known_evidence={"EV-A1"})
            self.assertEqual(result["profile"], "control")
            self.assertNotIn(r"\section{结构和接口说明}", document)
            self.assertNotIn(r"\section{按需选用的技术图示}", document)

    def test_reject_invented_source_and_application_text(self):
        data = brief()
        with self.assertRaises(PatentWorkflowError):
            validate_brief(data, known_evidence=set())
        data["innovation_points"][0]["evidence_ids"] = []
        data["claims"] = ["1. 非法越阶段"]
        with self.assertRaises(PatentWorkflowError):
            validate_brief(data)

    def test_no_latex_injection(self):
        self.assertEqual(tex_escape(r"\input{secret}"), r"\textbackslash{}input\{secret\}")
        with tempfile.TemporaryDirectory() as folder:
            data = brief()
            data["title"] = r"\input{../../secret.tex}"
            document, _ = render_brief(data, Path(folder), known_evidence={"EV-A1"})
            self.assertNotIn(r"\input{../../secret.tex}", document)

    def test_relative_figure_safety_and_missing_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            data = brief()
            data["figures"][0]["asset"] = "figures/../secret.pdf"
            with self.assertRaises(PatentWorkflowError):
                render_brief(data, path, known_evidence={"EV-A1"})
            data["figures"][0]["asset"] = "figures/structure.pdf"
            _, result = render_brief(data, path, known_evidence={"EV-A1"})
            self.assertEqual(len(result["missing_figures"]), 1)
            (path / "figures").mkdir()
            (path / "figures" / "structure.pdf").write_bytes(b"mock-PDF")
            document, result = render_brief(data, path, known_evidence={"EV-A1"})
            self.assertEqual(result["missing_figures"], [])
            self.assertIn(r"\includegraphics[width=.9\linewidth]{figures/structure.pdf}", document)


if __name__ == "__main__":
    unittest.main()
