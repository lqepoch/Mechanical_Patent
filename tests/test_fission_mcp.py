"""想法裂变、标准 MCP 业务接口及来源/权限边界的离线回归。"""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.core import Evidence, PatentWorkflowError, evidence_id, utc_now
from mechanical_patent.ideation_fission import FissionBoard, SCORE_FIELDS
from mechanical_patent.mcp_server import PatentMCPService, create_server
from mechanical_patent.workflow import PatentResearch


class Source:
    def __init__(self, kind):
        self.kind = kind
        self.name = "离线源-" + kind

    def search(self, query, *, limit=10):
        if self.kind == "patent":
            return [Evidence(
                publication="EP123456B1", title="Pump valve system",
                url="https://example.org/patent/EP123456B1", source=self.name,
                retrieved_at=utc_now(), jurisdiction="EP", verified=True,
                abstract="Pressure-control inlet system.",
                claims="1. A pump valve. The inlet is controlled by a pressure sensor.",
                kind="patent",
            )]
        return [Evidence(
            publication="10.1000/pump-1", title="Hydraulic intake pressure",
            url="https://doi.org/10.1000/pump-1", source=self.name,
            retrieved_at=utc_now(), verified=True,
            abstract="Air pockets and pump suction NPSH.", kind="paper",
        )]


def candidate(patent_id, paper_id, *, axis="机械结构", mechanism="泵入口分级排气阀与旁路水力联动",
              parent_id="", method="TRIZ"):
    return {
        "title": "高海拔消防泵低压吸入控制机构",
        "technical_problem": "空气进入吸入口时，泵的可用汽蚀余量下降。",
        "mechanism": mechanism,
        "enabling_details": "入口旁路设置旋启止回阀，排气支路装单向微孔元件，压力传感器接逻辑控制器。",
        "distinguishing_features": ["旁路单向微孔排气与入口阀联动"],
        "assumptions": ["海拔2000-4000m", "气液两相流，水温0到20摄氏度"],
        "falsification_tests": ["开展稳态NPSH测量并观察排气支路流量"],
        "expected_effect": "预期缩短排气时间，尚需验证",
        "technical_axis": axis, "inventive_method": method,
        "parent_id": parent_id, "evidence_ids": [patent_id, paper_id],
    }


def scoring(feasibility=4):
    return {k: (feasibility if k == "技术可行性" else 3) for k in SCORE_FIELDS}


class FissionAndMCPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = PatentMCPService(Path(self.tmp.name) / "private")
        self.case_id, self.run_id = "TEST-CASE-001", "RUN-TEST0001"
        self.service.create_case(self.case_id, "消防泵入口控制", confidentiality="秘密")
        self.folder = self.service.root / "cases" / self.case_id / "runs" / self.run_id
        PatentResearch(Source("patent"), [Source("paper")], self.folder).run(
            "消防泵入口控制", ["pump valve"], ["pump NPSH"], case_id=self.case_id
        )
        self.service.workspace.import_case(self.folder)
        patents = json.loads((self.folder / "02_patents.json").read_text())["records"]
        papers = json.loads((self.folder / "03_papers.json").read_text())["records"]
        self.patent_id = evidence_id(Evidence.from_dict(patents[0]))
        self.paper_id = evidence_id(Evidence.from_dict(papers[0]))

    def test_fission_lineage_scores_and_full_dossier_handoff(self):
        plan = self.service.fission_plan(self.case_id, self.run_id, limit=4)
        self.assertEqual(plan["status"], "awaiting_agent_ideas")
        self.assertEqual(len(plan["tasks"]), 4)
        root = self.service.fission_register(self.case_id, self.run_id,
            candidate(self.patent_id, self.paper_id))
        self.assertEqual(root["generation"], 0)
        next_plan = self.service.fission_plan(self.case_id, self.run_id, parent_id=root["id"])
        self.assertEqual(next_plan["tasks"][0]["generation"], 1)
        child = self.service.fission_register(self.case_id, self.run_id, candidate(
            self.patent_id, self.paper_id, mechanism="多段旁路延迟回流控制机制",
            axis="控制系统", method="SCAMPER", parent_id=root["id"]
        ))
        self.assertEqual(child["parent_id"], root["id"])
        self.service.fission_evaluate(self.case_id, self.run_id, root["id"],
            scoring(4), "有可制造结构但仍需反证组合显而易见性",
            [self.patent_id], "水力损失与液气分离机理", ["气塞"])
        self.service.fission_evaluate(self.case_id, self.run_id, child["id"],
            scoring(3), "需试验验证阀门动态控制", [], "连续性方程",
            ["阀门响应滞后"])
        frontier = self.service.fission_frontier(self.case_id, self.run_id)
        self.assertEqual(len(frontier["ranked"]), 2)
        self.assertFalse(frontier["legal_conclusion"] != "none")
        with self.assertRaises(PatentWorkflowError):
            self.service.fission_promote(self.case_id, self.run_id, child["id"])
        promoted = self.service.fission_promote(self.case_id, self.run_id, root["id"])
        self.assertFalse(promoted["filing_authorized"])
        record = self.service.countersearch_record(
            self.case_id, self.run_id, root["id"], "入口阀按压力调整",
            self.patent_id, "The inlet is controlled by a pressure sensor."
        )
        self.assertTrue(record["citation_verified_against_stored_claims"])
        self.service.engineering_record(
            self.case_id, self.run_id, root["id"],
            "质量守恒及压力降方程",
            ["Q=A*v，m^3/s", "NPSHa=(p_atm-p_v)/(rho*g)-h_f"],
            ["入口水温稳定"], ["干转"], ["以气液分离工况试验核查"]
        )
        brief = {
            "candidate_id": root["id"], "title": "双阀消防泵入口控制原理",
            "technical_problem": "入口存在气塞", "solution": "入口阀与排气阀按压力联动",
            "mechanism": "初始排气后开启主通道，保持压力连续",
            "expected_effect": "预期缓解压力波动，尚无实测值",
            "verification_plan": "以入口压力和含气量为控制变量开展台架试验",
            "components": [{"number": "101", "name": "入口阀", "role": "主通道调节"}],
            "innovation_points": [{
                "feature": "入口双阀联动", "prior_difference": "相较于公开压力控制方案还需全文比对",
                "technical_effect": "预期使排气先于流量上升", "evidence_ids": [self.patent_id],
            }],
            "prior_art": [{"evidence_id": self.patent_id,
                           "known_solution": "公开的单阀压力调节",
                           "difference": "此构想增加排气与入口联动"}],
        }
        saved_brief = self.service.brief_save(self.case_id, self.run_id, root["id"], brief)
        self.assertTrue(saved_brief["saved"])
        self.assertIn("08a_technical_brief.tex", saved_brief["latex_artifact"])
        phase_a = self.service.brief_audit(self.case_id, self.run_id, root["id"])
        self.assertEqual(phase_a["status"], "awaiting_dual_human_review")
        self.assertFalse(phase_a["filing_authorized"])
        draft = {
            "title": "一种消防泵入口排气机构",
            "abstract": "在入口通过多级排气支路改善吸入条件，效果需要试验。",
            "claims": ["1. 一种消防泵入口排气机构，包括单向阀和旁路。"],
            "description": {
                "technical_field": "消防泵及流体输送",
                "background": "常规入口存在气液混合问题",
                "technical_problem": "抑制入口气泡造成的压力下降",
                "technical_solution": "单向阀与旁路水力联动，排气支路独立控制。",
                "beneficial_effects": "预期降低吸入脉动，尚未实测。",
                "embodiments": "单向阀与旁路水力联动，排气支路独立控制。",
                "drawings": "图1为入口机构连接图。",
            },
            "claim_support": [{"claim": 1,
                "specification_passage": "单向阀与旁路水力联动，排气支路独立控制。"}],
        }
        # 未经可信企业审批签名，不得由 AI 擅自进入申请格式写作。
        with self.assertRaises(PatentWorkflowError):
            self.service.draft_save(self.case_id, self.run_id, root["id"], draft)
        self.assertFalse(self.service.conversion_status(
            self.case_id, self.run_id, root["id"])["conversion_authorized"])
        audit = self.service.quality(self.case_id, self.run_id)
        self.assertFalse(audit["filing_authorized"])
        self.assertTrue(self.service.read_artifact(self.case_id, self.run_id,
                                                   "05a_idea_fission.json")["content"]["candidates"])

    def test_duplicate_and_ungrounded_reference_fail_closed(self):
        first = candidate(self.patent_id, self.paper_id)
        self.service.fission_register(self.case_id, self.run_id, first)
        with self.assertRaises(PatentWorkflowError):
            self.service.fission_register(self.case_id, self.run_id, first)
        bad = candidate(self.patent_id, self.paper_id, mechanism="另一个水力旁通阀")
        bad["evidence_ids"] = ["EV-FAKE"]
        with self.assertRaises(PatentWorkflowError):
            self.service.fission_register(self.case_id, self.run_id, bad)
        with self.assertRaises(PatentWorkflowError):
            self.service.fission_evaluate(self.case_id, self.run_id, "IF-UNKN",
                scoring(), "有待验证", ["EV-FAKE"], "连通水力公式", ["阀损坏"])

    def test_limit_generation_and_preserve_diversity(self):
        parent_id = ""
        for idx in range(5):
            item = candidate(self.patent_id, self.paper_id, parent_id=parent_id,
                             mechanism="采用级数为" + str(idx) + "的水力结构")
            saved = self.service.fission_register(self.case_id, self.run_id, item)
            parent_id = saved["id"]
        self.assertEqual(saved["generation"], 4)
        with self.assertRaises(PatentWorkflowError):
            self.service.fission_plan(self.case_id, self.run_id, parent_id)

    def test_security_outbound_and_traversal(self):
        self.assertFalse(self.service.status(self.case_id)["outbound_approved"])
        with self.assertRaises(PatentWorkflowError):
            self.service.research(self.case_id, ["patent test"], ["paper test"])
        for bad in ("../TEST-CASE-001", "../../etc", "bad/child"):
            with self.assertRaises(PatentWorkflowError):
                self.service.status(bad)
        with self.assertRaises(PatentWorkflowError):
            self.service.read_artifact(self.case_id, "../RUN-TEST0001", "00_intake.json")
        with self.assertRaises(PatentWorkflowError):
            self.service.read_artifact(self.case_id, self.run_id, "../../index.sqlite3")

    def test_no_unproven_simulation_or_unsupported_claim_quotes(self):
        item = self.service.fission_register(self.case_id, self.run_id,
            candidate(self.patent_id, self.paper_id))
        self.service.fission_evaluate(self.case_id, self.run_id, item["id"],
            scoring(), "初步工作机理", [self.patent_id], "流量连续性", ["入口气塞"])
        self.service.fission_promote(self.case_id, self.run_id, item["id"])
        with self.assertRaises(PatentWorkflowError):
            self.service.countersearch_record(self.case_id, self.run_id, item["id"],
                "差异", self.patent_id, "这段权利要求并不存在")
        with self.assertRaises(PatentWorkflowError):
            self.service.engineering_record(
                self.case_id, self.run_id, item["id"], "流量守恒",
                ["Q=A*v"], ["满管"], ["冲击"], ["压力测试"],
                verification_status="simulated",
            )


    def test_external_mcp_import_never_claims_verified(self):
        run_id = self.service.create_run(self.case_id)["run_id"]
        sample = {
            "publication": "CN123456789A", "title": "一种液气分离装置",
            "url": "https://example.org/CN123456789A", "source": "external-patsnap-mcp",
            "kind": "patent", "abstract": "高海拔消防泵进水系统",
            "claims": "1. 液气分离结构。", "verified": True,
        }
        result = self.service.import_sources(
            self.case_id, run_id, [sample, sample],
            patent_queries=["pump priming"], paper_queries=[]
        )
        self.assertEqual(result["status"], "unverified_imported")
        records = self.service.read_artifact(self.case_id, run_id,
                                             "02_patents.json")["content"]["records"]
        self.assertEqual(len(records), 1)
        self.assertFalse(records[0]["verified"])
        self.assertTrue(self.service.read_artifact(
            self.case_id, run_id, "04b_technology_graph.json")["content"]["nodes"])
        with self.assertRaises(PatentWorkflowError):
            self.service.import_sources(self.case_id, run_id,
                [dict(sample, url="http://untrusted.example")], patent_queries=["pump"])

    def test_official_mcp_protocol_contract_when_installed(self):
        try:
            from mcp import Client
        except ImportError:
            self.skipTest("未安装可选 MCP SDK；CI 的 MCP job 将执行协议层验证。")
        server = create_server(self.service)

        async def run():
            async with Client(server) as client:
                tools = await client.list_tools()
                names = {x.name for x in (tools.tools if hasattr(tools, "tools") else tools)}
                for name in ("patent_case_create", "patent_research", "patent_idea_plan",
                             "patent_idea_register", "patent_idea_evaluate", "patent_idea_frontier",
                             "patent_idea_crossovers", "patent_idea_reject",
                             "patent_countersearch_record", "patent_engineering_record",
                             "patent_draft_save", "patent_brief_save", "patent_brief_audit", "patent_conversion_status",
                             "patent_quality_audit", "patent_run_create",
                             "patent_source_import"):
                    self.assertIn(name, names)
                result = await client.call_tool("patent_capabilities", {})
                self.assertFalse(result.is_error if hasattr(result, "is_error") else result.isError)
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
