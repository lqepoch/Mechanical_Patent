"""项目 SQLite 隔离、实时索引、LaTeX 源稿和前沿变种的离线回归。"""
from dataclasses import replace
from datetime import datetime, timezone
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from mechanical_patent.core import Evidence, PatentWorkflowError, utc_now
from mechanical_patent.frontier_radar import FrontierRadar
from mechanical_patent.latex_manuscript import ManuscriptWorkspace
from mechanical_patent.mcp_server import PatentMCPService, create_server
from mechanical_patent.patent_index import PatentIndex
from mechanical_patent.project_storage import ProjectStorage
from mechanical_patent.workflow import PatentResearch


class ProjectResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.a = PatentMCPService(self.base,"PM80")
        self.b = PatentMCPService(self.base,"PM120")
        self.a.create_case("CASE-A","高海拔消防泵吸水机构")
        self.b.create_case("CASE-B","消防车辆水力系统")

    def _evidence(self, claims="1. An inlet valve.") -> Evidence:
        return Evidence(
            publication="EP1234567A1",title="Variable priming flow regulator",
            url="https://example.org/patents/EP1234567A1",source="simulated-epo",
            retrieved_at=utc_now(),kind="patent",verified=True,
            publication_date="2026-11-12",jurisdiction="EP",abstract="Pump inlet",
            claims=claims,
        )

    def _approved(self):
        task=self.a.workspace.claim(
            "CASE-A",role="保密与权限智能体",actor="权限审核员")
        self.assertTrue(task)
        self.a.workspace.finish(task["task_id"],actor="权限审核员",
                                result={"outbound_approved":True})

    def test_databases_are_project_local_and_case_ids_are_strict(self):
        self.assertNotEqual(self.a.project.db_path,self.b.project.db_path)
        self.assertTrue(self.a.project.db_path.is_file())
        self.assertTrue(self.b.project.db_path.is_file())
        self.assertEqual(self.a.project.describe()["project_id"],"PM80")
        self.assertFalse(self.a.project.describe()["cross_project_access"])
        with self.assertRaises(PatentWorkflowError):
            self.b.status("CASE-A")
        with self.assertRaises(PatentWorkflowError):
            ProjectStorage(self.base,"../PM80")
        with self.assertRaises(PatentWorkflowError):
            ProjectStorage(self.base,"PM80/../../secret")
        self.assertFalse((self.base/"index.sqlite3").exists())

    def test_reject_symlink_project_and_db(self):
        parent=self.base/"projects"
        linked=parent/"LINKED"
        try:
            linked.symlink_to(self.a.project.root,target_is_directory=True)
        except (PermissionError,NotImplementedError,OSError):
            self.skipTest("平台无法建立符号链接")
        with self.assertRaises(PatentWorkflowError):
            ProjectStorage(self.base,"LINKED")

    def test_live_refresh_idempotent_delta_failure_and_history(self):
        index=PatentIndex(self.a.workspace)
        record=self._evidence()
        calls=[]
        def search(query,limit):
            calls.append((query,limit))
            return [record]
        x=index.refresh("CASE-A","pump inlet","epo-fixture",search)
        self.assertEqual((x["new"],x["changed"]),(1,0))
        self.assertFalse(x["global_completeness"])
        self.assertEqual(index.refresh("CASE-A","pump inlet","epo-fixture",search)["new"],0)
        self.assertEqual(len(index.history("CASE-A","EP1234567A1")),1)
        record=replace(record,claims="1. A different inlet valve.")
        z=index.refresh("CASE-A","pump inlet","epo-fixture",search)
        self.assertEqual(z["changed"],1)
        self.assertEqual(len(index.history("CASE-A","EP1234567A1")),2)
        self.assertEqual(len(calls),3)
        self.assertEqual(index.search("CASE-A","EP123")["freshness"],"recent_provider_check")
        self.assertEqual(index.search("CASE-A","%")["count"],0)
        with self.assertRaises(PatentWorkflowError):
            index.refresh("CASE-A","pump inlet","epo-fixture",
                          lambda *_: (_ for _ in ()).throw(OSError("429 rate limit")))
        current=index.search("CASE-A","pump")
        self.assertEqual(current["freshness"],"stale_or_unchecked")
        self.assertEqual(current["count"],1)
        self.assertEqual(current["last_check"]["status"],"failed")
        with self.assertRaises(PatentWorkflowError):
            index.search("CASE-B")
        self.assertEqual(PatentIndex(self.b.workspace).search("CASE-B")["count"],0)

    def test_latex_sections_versions_and_pandoc_output(self):
        source=ManuscriptWorkspace(self.a.project)
        doc=source.create("CASE-A","高海拔消防泵 — 技术论文")
        p=doc["manuscript_id"]
        self.assertEqual(doc["project_id"],"PM80")
        self.assertTrue((self.a.project.root/"cases"/"CASE-A"/"manuscripts"/p/"main.tex").is_file())
        first=source.edit("CASE-A",p,"methods",
            r"\section{泵吸入理论}"+"\n"+r"质量连续性方程为 $Q=Av$。")
        second=source.edit("CASE-A",p,"methods",
            r"\section{泵吸入理论}"+"\n"+r"$NPSH_a = \frac{p_a-p_v}{\rho g}-h_f$。")
        self.assertEqual((first["revision"],second["revision"]),(1,2))
        self.assertEqual(len(source.revisions("CASE-A",p,"methods")),2)
        with self.assertRaises(PatentWorkflowError):
            source.edit("CASE-A",p,"methods",r"\input{/etc/passwd}")
        with self.assertRaises(PatentWorkflowError):
            source.edit("CASE-A",p,"methods",r"\immediate\openout15=secret")
        with self.assertRaises(PatentWorkflowError):
            source.export("CASE-A",p,"pdf")
        with self.assertRaises(PatentWorkflowError):
            ManuscriptWorkspace(self.b.project).read("CASE-A",p,"methods")
        self.assertIn("NPSH",source.read("CASE-A",p,"methods")["content"])

    def test_pandoc_real_export_if_installed(self):
        import shutil
        if shutil.which("pandoc") is None:
            self.skipTest("Pandoc 非必需开发依赖；独立 CI 任务安装并实测。")
        writer=ManuscriptWorkspace(self.a.project)
        paper=writer.create("CASE-A","Pump Study")
        writer.edit("CASE-A",paper["manuscript_id"],"introduction",
                    r"\section{Introduction}"+"\nHydraulic flow test.")
        for fmt in ("md","html","docx"):
            out=writer.export("CASE-A",paper["manuscript_id"],fmt)
            self.assertGreater(out["size_bytes"],20)
            self.assertFalse(out["pdf_compile_performed"])

    def test_frontier_online_records_are_labeled_metadata_only(self):
        self._approved()
        def fake_openalex(url):
            q=parse_qs(urlsplit(url).query)
            self.assertEqual(q["sort"],["publication_date:desc"])
            self.assertIn("from_publication_date",q["filter"][0])
            return {"results":[{"id":"https://openalex.org/W123456",
                  "title":"Recent fire pump intake research",
                  "publication_date":datetime.now(timezone.utc).date().isoformat(),
                  "doi":"https://doi.org/10.1234/pump",
                  "primary_topic":{"display_name":"Hydraulic engineering"}}]}
        radar=FrontierRadar(self.a.project,fetch_json=fake_openalex)
        res=radar.scan("CASE-A",["fire pump control"],90,5)
        self.assertEqual(len(res["observations"]),1)
        self.assertFalse(res["patent_novelty_assessed"])
        self.assertEqual(res["errors"],[])
        with self.assertRaises(PatentWorkflowError):
            FrontierRadar(self.b.project,fetch_json=fake_openalex).scan("CASE-B",["fire pump"])
        with self.a.workspace.connect() as db:
            saved=db.execute("SELECT COUNT(*) AS n FROM frontier_observations").fetchone()["n"]
        self.assertEqual(saved,1)

    def test_existing_patent_title_drives_fission_not_forged_ideas(self):
        run=self.a.create_run("CASE-A")["run_id"]
        folder=self.a._folder("CASE-A",run)
        from mechanical_patent.core import save_json
        save_json(folder/"02_patents.json",{"records":[self._evidence().to_dict()]})
        radar=FrontierRadar(self.a.project,fetch_json=lambda _: {})
        result=radar.variants("CASE-A",folder,"Variable priming flow regulator")
        self.assertEqual(result["source"]["publication"],"EP1234567A1")
        self.assertEqual(len(result["variants"]),6)
        self.assertTrue(result["source"]["claims_available"])
        self.assertEqual(radar.variants("CASE-A",folder,"Unknown new patent")["status"],
                         "source_discovery_required")
        with self.assertRaises(PatentWorkflowError):
            radar.variants("CASE-B",folder,"EP1234567A1")

    def test_mcp_new_tools_are_discoverable(self):
        try:
            from mcp import Client
        except ImportError:
            self.skipTest("使用 MCP SDK v2 的 CI 独立任务测试协议。")
        server=create_server(self.a)
        async def run():
            async with Client(server) as client:
                x=await client.list_tools()
                names={v.name for v in (x.tools if hasattr(x,"tools") else x)}
                expected={"patent_project_info","patent_index_refresh",
                          "patent_index_search","patent_index_history","patent_frontier_scan",
                          "patent_variant_plan","patent_manuscript_create",
                          "patent_manuscript_read","patent_manuscript_edit",
                          "patent_manuscript_revisions","patent_manuscript_export"}
                self.assertFalse(expected-names)
                answer=await client.call_tool("patent_project_info",{})
                self.assertFalse(answer.is_error if hasattr(answer,"is_error") else answer.isError)
        asyncio.run(run())


if __name__=="__main__":
    unittest.main()
