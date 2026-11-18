"""多 Agent 工作流、双源核验、方向重审、本地索引的离线集成测试。"""
import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.core import Evidence, PatentWorkflowError
from mechanical_patent.local_workspace import LocalPatentWorkspace, WORKFLOW_STEPS


def evidence(kind: str) -> Evidence:
    return Evidence(
        publication="CN202610000001A" if kind == "patent" else "10.1234/pump.flow",
        title="消防泵进水口控制" if kind == "patent" else "泵入口空化机理",
        url="https://example.org/" + kind + "/publication",
        source="经过本地模拟的授权数据库",
        retrieved_at="2026-11-18T08:00:00+00:00",
        publication_date="2026-01-01", jurisdiction="CN" if kind == "patent" else "",
        abstract="高海拔消防泵入口空气与液体管理技术",
        claims="1. 一种泵入口结构。" if kind == "patent" else "",
        verified=True, kind=kind,
    )


class LocalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = LocalPatentWorkspace(self.root / "index.sqlite3")

    def _complete_searches(self, case_id: str):
        privacy = self.db.claim(case_id, role="保密与权限智能体", actor="保密岗")
        self.assertIsNotNone(privacy)
        self.db.finish(privacy["task_id"], actor="保密岗", result={"outbound_approved": True})
        patent = self.db.claim(case_id, role="全球专利检索智能体", actor="专利岗")
        paper = self.db.claim(case_id, role="学术论文检索智能体", actor="论文岗")
        self.assertEqual(patent["step"], "专利检索")
        self.assertEqual(paper["step"], "论文检索")
        self.assertIsNone(self.db.claim(case_id, role="全球专利检索智能体", actor="另一个员工"))
        self.db.finish(patent["task_id"], actor="专利岗", result={"queries": ["pump inlet"]})
        self.db.finish(paper["task_id"], actor="论文岗", result={"queries": ["cavitation"]})

    def test_first_run_creates_ordered_tasks_and_parallel_searches(self):
        row = self.db.create_case("X001", "研发消防车吸水泵新的结构方案")
        self.assertEqual(len(row["tasks"]), len(WORKFLOW_STEPS))
        self.assertEqual(row["confidentiality"], "秘密")
        self.assertIsNone(self.db.claim("X001", role="全球专利检索智能体", actor="P1"))
        self._complete_searches("X001")
        verify = self.db.claim("X001", role="证据核验智能体", actor="核验岗")
        self.assertEqual(verify["step"], "证据核验")
        with self.assertRaises(PatentWorkflowError):
            self.db.finish(verify["task_id"], actor="核验岗", result={"coverage_report": "数据库检索完整说明"})
        patent_id = self.db.upsert_document("X001", evidence("patent"))
        paper_id = self.db.upsert_document("X001", evidence("paper"))
        self.assertIn("EV-", patent_id)
        with self.assertRaises(PatentWorkflowError):
            self.db.finish(verify["task_id"], actor="核验岗", result={"coverage_report": "报告"})
        for doc_id in (patent_id, paper_id):
            response = self.db.review_document(
                "X001", doc_id, actor="核验员",
                accepted=True, rationale="已核对原始官方网站的出版著录数据和标题",
                public_pdf_url="https://example.org/original-patent.pdf" if doc_id == patent_id else None,
            )
            self.assertEqual(response["verification_status"], "已核验")
        self.db.finish(verify["task_id"], actor="核验岗", result={"coverage_report": "已列出双源检索覆盖范围和失败源"})
        direction = self.db.claim("X001", role="技术方向评审智能体", actor="技术总师")
        self.assertEqual(direction["step"], "方向评审")
        with self.assertRaises(PatentWorkflowError):
            self.db.finish(direction["task_id"], actor="技术总师", result={
                "decision": "继续", "rationale": "已经核对了双源文献，还需要展开机理验证",
                "evidence_ids": ["EV-UNKNOWN"],
            })
        self.db.finish(direction["task_id"], actor="技术总师", result={
            "decision": "继续", "rationale": "已结合专利与论文比较验证技术方向仍具有可研究空间",
            "evidence_ids": [patent_id, paper_id],
        })
        inventor = self.db.claim("X001", role="多路线创新智能体", actor="创新 A")
        self.assertEqual(inventor["step"], "多路线创新")
        self.assertEqual(self.db.status("X001")["revision"], 1)
        found = self.db.search_documents("消防泵", case_id="X001")
        self.assertEqual(len(found), 2)
        online = self.db.pdf_source("X001", patent_id)
        self.assertEqual(online["public_pdf_url"], "https://example.org/original-patent.pdf")

    def test_no_sources_requires_explicit_waiver_and_direction_revision(self):
        self.db.create_case("X002", "研发高海拔双向进水方案")
        self._complete_searches("X002")
        verify = self.db.claim("X002", role="证据核验智能体", actor="审阅")
        with self.assertRaises(PatentWorkflowError):
            self.db.finish(verify["task_id"], actor="审阅", result={"coverage_report": "无数据"})
        self.db.finish(verify["task_id"], actor="审阅", result={
            "coverage_report": "授权数据源暂时无结果",
            "gap_waiver": True, "gap_rationale": "原始来源无法访问，后续必须重新检查",
        })
        direction = self.db.claim("X002", role="技术方向评审智能体", actor="研究主管")
        self.db.finish(direction["task_id"], actor="研究主管", result={
            "decision": "改换方向",
            "rationale": "关键技术原理缺少足够文献支持，且问题表述需要重新定义",
            "evidence_ids": [],
        })
        self.assertEqual(self.db.status("X002")["status"], "方向调整中")
        with self.assertRaises(PatentWorkflowError):
            self.db.claim("X002", role="多路线创新智能体", actor="任何人")
        self.assertEqual(self.db.next_revision(
            "X002", actor="研究主管", new_direction="探索带独立气液分离单元的进水系统",
            rationale="原研究方向约束不明确，重新定义机械结构和验证边界",
        ), 2)
        self.assertEqual(self.db.status("X002")["revision"], 2)
        self.assertEqual(len(self.db.status("X002")["tasks"]), len(WORKFLOW_STEPS))
        self.assertIsNotNone(self.db.claim("X002", role="保密与权限智能体", actor="保密岗"))

    def test_import_untrusted_case_preserves_metadata_and_review(self):
        folder = self.root / "case-upload"
        folder.mkdir()
        (folder / "00_intake.json").write_text(json.dumps({
            "case_id": "X003", "direction": "消防车气液分离结构"
        }), encoding="utf-8")
        (folder / "02_patents.json").write_text(json.dumps({
            "records": [evidence("patent").to_dict()]
        }), encoding="utf-8")
        (folder / "03_papers.json").write_text(json.dumps({
            "records": [evidence("paper").to_dict()]
        }), encoding="utf-8")
        imported = self.db.import_case(folder)
        self.assertEqual(imported["indexed"], {"patent": 1, "paper": 1})
        rows = self.db.search_documents("pump", case_id="X003")
        self.assertEqual(len(rows), 0)
        rows = self.db.search_documents("消防泵", case_id="X003")
        self.assertEqual(len(rows), 2)
        with self.db.connect() as conn:
            verified = [x[0] for x in conn.execute(
                "SELECT metadata_verified FROM documents WHERE case_id='X003'"
            ).fetchall()]
        self.assertEqual(verified, [0, 0])
        doc_id = rows[0]["doc_id"]
        self.db.review_document(
            "X003", doc_id, actor="资料核对人", accepted=True,
            rationale="独立联网查看了公开原文并核对标题与公开日期",
        )
        self.assertEqual(self.db.pdf_source("X003", doc_id)["verification_status"], "已核验")

    def test_wrong_actor_or_expired_lease_cannot_finish(self):
        self.db.create_case("X004", "发动机泵耦合改善")
        lease = self.db.claim("X004", role="保密与权限智能体", actor="本人", lease_seconds=60)
        with self.assertRaises(PatentWorkflowError):
            self.db.finish(lease["task_id"], actor="冒充者", result={"outbound_approved": True})
        with self.db.connect(write=True) as db:
            db.execute("UPDATE tasks SET lease_expires=? WHERE id=?",
                       ("2000-01-01T00:00:00+00:00", lease["task_id"]))
        with self.assertRaises(PatentWorkflowError):
            self.db.finish(lease["task_id"], actor="本人", result={"outbound_approved": True})
        retry = self.db.claim("X004", role="保密与权限智能体", actor="同事")
        self.assertEqual(retry["task_id"], lease["task_id"])
        self.assertEqual(self.db.status("X004")["tasks"][0]["attempts"], 2)


if __name__ == "__main__":
    unittest.main()
