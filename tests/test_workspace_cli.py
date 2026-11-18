"""工作流命令行与研发案卷自动索引的离线回归测试。"""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.cli import main


def invoke(args):
    stream = StringIO()
    with redirect_stdout(stream):
        code = main(args)
    return code, stream.getvalue()


class WorkspaceCLITests(unittest.TestCase):
    def test_case_creation_claim_and_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "index.sqlite3"
            prefix = ["workspace", "--db", str(db)]
            code, output = invoke(prefix + [
                "create", "--case-id", "FIRE-001",
                "--direction", "提高消防车快速吸水性能",
            ])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)["revision"], 1)
            code, output = invoke(prefix + [
                "claim", "--case-id", "FIRE-001",
                "--role", "保密与权限智能体", "--actor", "权限管理员",
            ])
            self.assertEqual(code, 0)
            task = json.loads(output)
            self.assertEqual(task["step"], "保密审批")
            result = Path(folder) / "privacy.json"
            result.write_text('{"outbound_approved":false}', encoding="utf-8")
            code, output = invoke(prefix + [
                "finish", "--task-id", str(task["task_id"]),
                "--actor", "权限管理员", "--result-file", str(result),
            ])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)["status"], "已完成")
            code, output = invoke(prefix + [
                "status", "--case-id", "FIRE-001",
            ])
            self.assertEqual(code, 0)
            state = json.loads(output)
            self.assertEqual(state["status"], "研究中")
            self.assertEqual(state["tasks"][0]["status"], "已完成")

    def test_research_auto_indexes_into_sqlite_without_model_api(self):
        with tempfile.TemporaryDirectory() as folder:
            case = Path(folder) / "fresh"
            code, output = invoke([
                "research", "--direction", "双阀消防泵吸水技术",
                "--patent-provider", "none", "--paper-provider", "none",
                "--case-dir", str(case),
            ])
            self.assertEqual(code, 0)
            self.assertIn("本地文献索引", output)
            db = Path(folder) / "index.sqlite3"
            self.assertTrue(db.exists())
            intake = json.loads((case / "00_intake.json").read_text(encoding="utf-8"))
            code, state = invoke([
                "workspace", "--db", str(db),
                "status", "--case-id", intake["case_id"],
            ])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(state)["revision"], 1)

    def test_bound_research_keeps_case_and_blocks_unapproved_external_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "index.sqlite3"
            directory = Path(folder) / "research"
            from mechanical_patent.local_workspace import LocalPatentWorkspace
            workspace = LocalPatentWorkspace(db)
            workspace.create_case("PM-ALPHA", "新型气液分离结构研发")
            self.assertFalse(workspace.can_egress("PM-ALPHA"))
            # 不触网的任务仍可由当前 AI 在已有案卷中保存并索引。
            code, output = invoke([
                "research", "--workflow-case-id", "PM-ALPHA",
                "--direction", "高海拔进水控制",
                "--patent-provider", "none", "--paper-provider", "none",
                "--workspace-db", str(db), "--case-dir", str(directory),
            ])
            self.assertEqual(code, 0)
            self.assertEqual(
                json.loads((directory / "00_intake.json").read_text())["case_id"],
                "PM-ALPHA",
            )
            self.assertEqual(workspace.status("PM-ALPHA")["revision"], 1)
            # 对外论文检索即使有命令行开关，也必须先有案卷保密批准。
            blocked, _ = invoke([
                "research", "--workflow-case-id", "PM-ALPHA",
                "--direction", "高海拔进水控制",
                "--patent-provider", "none",
                "--paper-provider", "crossref",
                "--paper-query", "cavitation flow",
                "--allow-search-exposure", "--workspace-db", str(db),
                "--case-dir", str(Path(folder) / "blocked"),
            ])
            self.assertEqual(blocked, 3)
            self.assertFalse((Path(folder) / "blocked").exists())
            task = workspace.claim(
                "PM-ALPHA", role="保密与权限智能体", actor="保密审核员"
            )
            workspace.finish(task["task_id"], actor="保密审核员", result={
                "outbound_approved": True,
            })
            self.assertTrue(workspace.can_egress("PM-ALPHA"))

    def test_invalid_document_location_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "index.sqlite3"
            code, _ = invoke([
                "workspace", "--db", str(db),
                "source", "--case-id", "UNKNOWN", "--doc-id", "EV-UNKNOWN",
            ])
            self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main()
