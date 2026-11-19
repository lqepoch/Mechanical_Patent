"""跨技术轴思想杂交、失败记忆、文字近似提醒与审核边界回归。"""
import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.core import Evidence, PatentWorkflowError, evidence_id, utc_now
from mechanical_patent.ideation_fission import FissionBoard, SCORE_FIELDS


def proposal(mechanism: str, axis: str, *, method: str = "TRIZ",
             parent_ids=None, **extra):
    data = {
        "title": "高海拔消防泵吸入系统创新假说",
        "technical_problem": "低气压与间歇气塞导致泵入口可用汽蚀余量不足",
        "mechanism": mechanism,
        "enabling_details": "采用定制旁路阀、单向排气腔及压力信号调节控制器，设计阀位失效复位。",
        "distinguishing_features": [mechanism + "形成双工况气液分离流路"],
        "assumptions": ["海拔2000m以上，0至20摄氏度水温"],
        "falsification_tests": ["NPSHa边界下进行流量和动态响应试验"],
        "expected_effect": "预期改善排气时间与入口压降，尚待试验",
        "technical_axis": axis,
        "inventive_method": method,
        "evidence_ids": [],
    }
    if parent_ids is not None:
        data["parent_ids"] = parent_ids
    data.update(extra)
    return data


def scores():
    return {field: 3 for field in SCORE_FIELDS}


class IdeaEvolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "RUN-1"
        self.folder.mkdir()
        (self.folder / "00_intake.json").write_text(
            json.dumps({"case_id": "FIRE-PUMP-01"}), encoding="utf-8"
        )
        self.board = FissionBoard(self.folder)

    def seed(self, mechanism, axis):
        item = self.board.register(proposal(mechanism, axis))
        self.board.evaluate(
            item["id"], scores(), "该构思可继续工程论证",
            [], "连续性方程与局部损失系数", ["吸入气塞可能导致失效"]
        )
        return item

    def test_cross_axis_pairing_and_true_two_parent_lineage(self):
        valve = self.seed("分级气液分离阀", "机械结构")
        control = self.seed("压降前馈控制器", "控制系统")
        plans = self.board.plan_crossovers()
        self.assertEqual(plans["status"], "awaiting_agent_crossbreeding")
        self.assertEqual(set(plans["tasks"][0]["parent_ids"]), {valve["id"], control["id"]})
        child = self.board.register(proposal(
            "机械排气腔与压降前馈控制交替启闭", "系统集成",
            method="组合创新", parent_ids=[valve["id"], control["id"]],
            synergy="当排气腔气含率突升时，前馈控制提前转换排气支路，抑制气塞演化",
            interface_definition="机械阀由电磁阀驱动，控制器输入压差信号，机械止回阀保证断电复位",
        ))
        self.assertEqual(child["generation"], 1)
        self.assertEqual(child["parent_id"], valve["id"])
        self.assertEqual(child["parent_ids"], [valve["id"], control["id"]])
        self.assertFalse(child["legal_patentability_verified"])
        self.assertFalse(child["experiment_verified"])
        stored = json.loads((self.folder / "05a_idea_fission.json").read_text())
        self.assertEqual(len(stored["candidates"]), 3)
        self.assertFalse(self.board.plan_crossovers()["tasks"])

    def test_crossing_requires_distinct_axes_and_explicit_synergy(self):
        a = self.seed("新型排气阀", "机械结构")
        b = self.seed("密封圈可拆卸机构", "机械结构")
        self.assertEqual(self.board.plan_crossovers()["tasks"], [])
        crossing = proposal("串并联排气组件", "系统集成",
                            method="组合创新", parent_ids=[a["id"], b["id"]],
                            synergy="改善压降", interface_definition="阀间采用法兰连接")
        with self.assertRaisesRegex(PatentWorkflowError, "两个不同"):
            self.board.register(crossing)
        crossing["parent_ids"] = [a["id"], "IF-NONEXIST"]
        with self.assertRaisesRegex(PatentWorkflowError, "父构思不存在"):
            self.board.register(crossing)
        crossing["parent_ids"] = [a["id"], b["id"]]
        crossing.pop("interface_definition")
        with self.assertRaises(PatentWorkflowError):
            self.board.register(crossing)

    def test_failed_route_remains_visible_and_produces_next_constraints(self):
        root = self.seed("机械旁路无源排气", "机械结构")
        result = self.board.reject(
            root["id"],
            "低气压工况阀腔存在无法排净的气塞",
            ["新方案必须实现无外部电源排气失效保护", "所有试验先核查NPSHa"],
        )
        self.assertTrue(result["retained_for_learning"])
        self.assertEqual(len(self.board.list_candidates()["candidates"]), 1)
        plan = self.board.plan(parent_id=root["id"])
        self.assertIn("新方案必须实现无外部电源排气失效保护",
                      plan["avoid_failed_constraints"])
        with self.assertRaisesRegex(PatentWorkflowError, "失败归档"):
            self.board.evaluate(root["id"], scores(), "再次提交", [], "流体压力", ["漏气"])
        with self.assertRaisesRegex(PatentWorkflowError, "已否定"):
            self.board.promote(root["id"])
        with self.assertRaisesRegex(PatentWorkflowError, "已经归档"):
            self.board.reject(root["id"], "重复", ["避免重复"])

    def test_near_duplicate_is_warning_not_legal_or_automatic_rejection(self):
        mechanism = "高海拔消防泵采用双通道旁路阀主动切换缓解入口流道的气塞累积并降低局部阻力"
        self.board.register(proposal(mechanism, "机械结构"))
        variant = self.board.register(proposal(mechanism + "，并在阀出口增加温度采样", "控制系统"))
        self.assertTrue(variant["text_overlap_neighbors"])
        self.assertGreaterEqual(variant["text_overlap_neighbors"][0]["text_overlap"], 0.72)
        self.assertFalse(variant["legal_patentability_verified"])
        with self.assertRaisesRegex(PatentWorkflowError, "完全重复"):
            self.board.register(proposal(mechanism, "材料"))

    def test_failure_repair_is_new_child_with_explicit_correction(self):
        original = self.board.register(proposal("高海拔泵入口使用无源细孔排气", "机械结构"))
        self.board.reject(original["id"], "细孔在结冰后堵塞",
                          ["需具备失电与低温结冰下的旁路保通能力"])
        unapproved = proposal("更换为主动热防冻排气", "流体与热")
        unapproved["parent_id"] = original["id"]
        with self.assertRaisesRegex(PatentWorkflowError, "显式修复"):
            self.board.register(unapproved)
        unapproved["repair_of_failed_route"] = True
        unapproved["repair_rationale"] = "设置热虹吸旁路并提供机械压差回退路径，应对结冰堵塞"
        child = self.board.register(unapproved)
        self.assertEqual(child["parent_ids"], [original["id"]])
        self.assertTrue(child["repairs_failed_route"])
        self.assertEqual(child["generation"], 1)

    def test_unverified_patent_claims_block_promotion(self):
        doc = Evidence(
            publication="CN123456789A", title="测试排气阀（仅模拟外部导入）",
            url="https://example.org/CN123456789A", source="unverified_fixture",
            retrieved_at=utc_now(), kind="patent", jurisdiction="CN",
            claims="一种进口排气阀，包括控制腔。", verified=False,
        )
        (self.folder / "04_evidence.json").write_text(
            json.dumps({"records": [doc.to_dict()]}), encoding="utf-8"
        )
        source = evidence_id(doc)
        candidate = proposal("低压主动排气方案", "机械结构")
        candidate["evidence_ids"] = [source]
        saved = self.board.register(candidate)
        self.board.evaluate(saved["id"], scores(), "基于导入文献的初评",
                            [source], "能量守恒关系", ["气塞和结冰"])
        with self.assertRaisesRegex(PatentWorkflowError, "经原始来源核验"):
            self.board.promote(saved["id"])

    def test_cross_parent_must_use_combinatorial_method(self):
        a = self.board.register(proposal("分级机械泵入口排气", "机械结构"))
        b = self.board.register(proposal("电动压力调节反馈", "控制系统"))
        invalid = proposal(
            "双机制联合", "系统集成", parent_ids=[a["id"], b["id"]],
            synergy="阀位和排气同步", interface_definition="阀杆传感器"
        )
        with self.assertRaisesRegex(PatentWorkflowError, "组合创新"):
            self.board.register(invalid)


if __name__ == "__main__":
    unittest.main()
