"""多 Agent 科研循环：状态机、项目隔离、证据真实性和恢复的离线回归。"""
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.core import Evidence, PatentWorkflowError, utc_now
from mechanical_patent.project_storage import ProjectStorage
from mechanical_patent.research_cycle import ResearchCycle, ROLES


class ResearchCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = ProjectStorage(self.base, "mechanics")
        self.workspace = self.project.workspace
        self.workspace.create_case("CASE-01", "多物理场机械结构研究")
        self.lab = ResearchCycle(self.project)
        self.cycle = self.lab.create("CASE-01")["cycle_id"]

    def claim(self, step, actor):
        response = self.lab.claim(self.cycle, ROLES[step], actor, lease_seconds=300)
        self.assertIsNotNone(response, step)
        self.assertEqual(response["step"], step)
        return response["task_id"]

    def done(self, step, actor, result):
        task = self.claim(step, actor)
        return self.lab.finish(task, actor, result)

    def papers(self, reviewed=True):
        ids = []
        for kind in ("patent", "paper"):
            source = Evidence(
                publication="CN202610000001A" if kind == "patent" else "10.1234/verification",
                title="机械联动公开结构" if kind == "patent" else "机械流体耦合模型",
                url="https://example.org/source/" + kind,
                source="离线测试元数据", retrieved_at=utc_now(),
                publication_date="2026-01-01",
                abstract="一种研究公开数据", claims="1. 联动阀。" if kind == "patent" else "",
                verified=True, kind=kind,
            )
            doc_id = self.workspace.upsert_document("CASE-01", source)
            if reviewed:
                self.workspace.review_document(
                    "CASE-01", doc_id, actor="资料核验员",
                    accepted=True, rationale="仅在离线测试样本内审查来源元数据和标题",
                )
            ids.append(doc_id)
        return ids

    def through_evidence(self, reviewed=True):
        self.done("课题发现", "问题研究员", {
            "problem": "高变载荷导致密封泄漏", "measurable_goal": "记录泄漏率变化",
        })
        p = self.claim("专利检索", "检索员甲")
        q = self.claim("论文检索", "检索员乙")
        self.assertIsNone(self.lab.claim(self.cycle, ROLES["证据整合"], "分析师"))
        self.lab.finish(p, "检索员甲", {"coverage_report": "离线专利授权库检索", "remote_used": False})
        self.lab.finish(q, "检索员乙", {"coverage_report": "离线期刊检索", "remote_used": False})
        ids = self.papers(reviewed)
        return ids

    def through_countersearch(self):
        ids = self.through_evidence()
        self.done("证据整合", "分析师", {
            "evidence_ids": ids, "limitations": "仅核验元数据，尚无可靠实验结果",
        })
        hypotheses = [{
            "id": "H1", "mechanism": "压力自适应的机械预紧",
            "enabling_details": "带凸轮和弹簧的预紧组件",
            "evidence_ids": ids, "falsification_tests": ["台架泄漏率"],
        }, {
            "id": "H2", "mechanism": "流体旁路补偿",
            "enabling_details": "旁路阀及反馈控制器",
            "evidence_ids": ids, "falsification_tests": ["测量动态响应"],
        }]
        self.done("构思生成", "发明人甲", {"hypotheses": hypotheses})
        self.done("反证检索", "反方乙", {"challenges": [
            {"hypothesis_id": item["id"], "risk": "现有公开组合仍需排除",
             "evidence_ids": ids} for item in hypotheses
        ]})
        return ids

    def test_complete_lifecycle_with_no_filing_permission(self):
        self.through_countersearch()
        review_task = self.claim("独立裁决", "发明人甲")
        with self.assertRaises(PatentWorkflowError):
            self.lab.finish(review_task, "发明人甲", {
                "decision": "advance", "rationale": "主创不可自审", "selected_ids": ["H1"],
            })
        self.lab.fail(review_task, "发明人甲", "需要独立的真实评审员")
        self.done("独立裁决", "评委丙", {
            "decision": "advance", "rationale": "H1 可用台架直接证伪",
            "selected_ids": ["H1"],
        })
        self.done("技术验证", "试验员", {"assessments": [{
            "hypothesis_id": "H1", "level": "L1",
            "method": "守恒方程推导，未开展实体试验",
            "limitations": "未考虑制造公差", "artifacts": [],
        }]})
        outcome_task = self.claim("成果分流", "成果岗")
        with self.assertRaises(PatentWorkflowError):
            self.lab.finish(outcome_task, "成果岗", {
                "routes": [{"hypothesis_id": "H1", "target": "patent_application"}],
            })
        self.lab.finish(outcome_task, "成果岗", {
            "routes": [{"hypothesis_id": "H1", "target": "patent_candidate"},
                       {"hypothesis_id": "H1", "target": "paper_draft"}],
        })
        final = self.done("持续监测", "情报岗", {"followups": []})
        self.assertEqual(final["status"], "已完成")
        self.assertFalse(final["filing_authorized"])
        self.assertTrue(self.lab.verify_audit(self.cycle)["valid"])
        # 可重启后继续查询原状态，结果不会丢失。
        self.assertEqual(ResearchCycle(ProjectStorage(self.base, "mechanics")).status(self.cycle)["status"], "已完成")

    def test_unverified_evidence_and_remote_search_blocked(self):
        self.done("课题发现", "问题研究员", {
            "problem": "可观测失效问题", "measurable_goal": "测得失效阈值",
        })
        p = self.claim("专利检索", "检索员")
        with self.assertRaises(PatentWorkflowError):
            self.lab.finish(p, "检索员", {
                "coverage_report": "远程 API 检索", "remote_used": True,
            })
        self.lab.finish(p, "检索员", {
            "coverage_report": "离线库", "remote_used": False,
        })
        self.done("论文检索", "论文员", {
            "coverage_report": "离线论文库", "remote_used": False,
        })
        ids = self.papers(reviewed=False)
        task = self.claim("证据整合", "证据员")
        with self.assertRaises(PatentWorkflowError):
            self.lab.finish(task, "证据员", {
                "evidence_ids": ids, "limitations": "缺乏真实来源",
            })
        self.assertEqual(self.lab.status(self.cycle)["status"], "进行中")

    def test_iterate_retains_history_and_no_immediate_downstream(self):
        self.through_countersearch()
        status = self.done("独立裁决", "外审丙", {
            "decision": "iterate", "rationale": "H1 H2 缺少必要边界条件",
            "selected_ids": [],
        })
        self.assertEqual(status["status"], "待迭代")
        self.assertTrue(all(t["status"] == "已阻断" for t in status["tasks"]
                            if t["step"] in {"技术验证", "成果分流", "持续监测"}))
        reset = self.lab.iterate(self.cycle, "研究主任", "调整技术边界")
        self.assertEqual(reset["iteration"], 2)
        self.assertEqual(reset["ready_steps"], ["课题发现"])
        with self.project.workspace.connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM research_tasks WHERE cycle_id=?",
                (self.cycle,),
            ).fetchone()[0], 20)

    def test_artifacts_must_be_real_and_inside_current_project(self):
        self.through_countersearch()
        self.done("独立裁决", "外审丙", {
            "decision": "advance", "rationale": "H1 可以计算验证", "selected_ids": ["H1"],
        })
        artifact = self.project.root / "calculation.json"
        artifact.write_text('{"result":"calculated"}', encoding="utf-8")
        item = {"hypothesis_id": "H1", "level": "L2",
                "method": "本地计算程序", "limitations": "尚无实测",
                "artifacts": [{"path": "../outside.json", "sha256": "0"*64}]}
        task = self.claim("技术验证", "计算员")
        with self.assertRaises(PatentWorkflowError):
            self.lab.finish(task, "计算员", {"assessments": [item]})
        item["artifacts"] = [{"path": "calculation.json",
                              "sha256": sha256(artifact.read_bytes()).hexdigest()}]
        self.lab.finish(task, "计算员", {"assessments": [item]})
        self.assertTrue(self.lab.verify_audit(self.cycle)["valid"])

    def test_exhausted_retries_block_cycle(self):
        task = self.claim("课题发现", "问题研究员")
        self.lab.fail(task, "问题研究员", "输入不完整")
        for _ in range(2):
            task = self.claim("课题发现", "问题研究员")
            self.lab.fail(task, "问题研究员", "仍然缺失")
        self.assertEqual(self.lab.status(self.cycle)["status"], "已阻断")
        self.assertIsNone(self.lab.claim(self.cycle, ROLES["课题发现"], "问题研究员"))

    def test_project_boundaries(self):
        other = ProjectStorage(self.base, "other")
        second = ResearchCycle(other)
        with self.assertRaises(PatentWorkflowError):
            second.status(self.cycle)
        with self.assertRaises(PatentWorkflowError):
            second.create("CASE-01")


if __name__ == "__main__":
    unittest.main()
