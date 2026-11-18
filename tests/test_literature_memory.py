"""文献记忆、中文索引、分页恢复、项目隔离及元数据可信度回归。"""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from mechanical_patent.core import Evidence, PatentWorkflowError, evidence_id
from mechanical_patent.literature_harvest import HarvestBudget, LiteratureHarvester
from mechanical_patent.literature_memory import LiteratureMemoryStore
from mechanical_patent.papers import OpenAlexProvider, CrossrefProvider


def paper(number: int, *, abstract: str = "消防泵入口气液两相流空化") -> Evidence:
    return Evidence(
        publication=f"10.9000/fire-pump-{number:05d}",
        title=f"高海拔消防泵吸水研究 {number}",
        source="offline-fixture", url=f"https://doi.org/10.9000/fire-pump-{number:05d}",
        retrieved_at="2026-11-18T00:00:00+00:00",
        abstract=abstract, publication_date="2026-01-01", kind="paper",
        verified=False,
    )


def patent(number: int) -> Evidence:
    return Evidence(
        publication=f"CN20261000{number:04d}A",
        title="消防泵吸入口分离阀",
        source="offline-patent", url=f"https://example.org/CN20261000{number:04d}A",
        retrieved_at="2026-11-18T00:00:00+00:00", kind="patent",
        claims="1. 带排气支路的消防泵入口结构。", verified=False,
    )


class PaginatedProvider:
    name = "offline-page-provider"

    def __init__(self):
        self.calls = []

    def search_page(self, query, *, cursor=None, limit=100):
        self.calls.append((query, cursor, limit))
        if cursor == "*":
            return {"records": [paper(10), paper(11)], "next_cursor": "PAGE-2"}
        if cursor == "PAGE-2":
            return {"records": [paper(12)], "next_cursor": None}
        raise AssertionError("unexpected cursor")


class LiteratureMemoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.store = LiteratureMemoryStore(self.root / "case-A")

    def test_thousand_documents_have_own_markdown_and_single_case_database(self):
        result = self.store.ingest_many(paper(i) for i in range(1000))
        self.assertEqual(result["new"], 1000)
        self.assertEqual(
            len(list((self.root / "case-A" / "knowledge" / "documents" / "papers").glob("*.md"))),
            1000,
        )
        self.assertTrue(self.store.db_path.is_file())
        self.assertTrue((self.root / "case-A" / "knowledge" / "INDEX.md").is_file())
        self.assertTrue((self.root / "case-A" / "knowledge" / "RESEARCH_RESUME.md").is_file())
        matches = self.store.search("消防泵", limit=5)
        self.assertEqual(len(matches), 5)
        self.assertEqual(self.store.stats()["by_kind"]["paper"]["documents"], 1000)
        again = self.store.ingest_many([paper(300), paper(301)])
        self.assertEqual(again["unchanged"], 2)

        isolated = LiteratureMemoryStore(self.root / "case-B")
        self.assertEqual(isolated.search("消防泵"), [])
        self.assertNotEqual(self.store.db_path, isolated.db_path)

    def test_summary_preserved_when_source_metadata_changes(self):
        original = paper(5)
        doc_id = evidence_id(original)
        self.store.ingest_many([original])
        with self.assertRaises(PatentWorkflowError):
            self.store.write_analysis(
                doc_id, analyst="AI", basis="full_text",
                analysis={"plain_summary": "已阅读全文"},
            )
        self.store.write_analysis(
            doc_id, analyst="研发人员", basis="abstract",
            analysis={
                "plain_summary": "从摘要可见该研究关注进水口空化。",
                "innovation_hooks": "考虑变面积排气结构（待实验验证）。",
            },
        )
        revised = replace(original, abstract="新增实验对象为低压吸水流道")
        self.assertEqual(self.store.ingest_many([revised])["updated"], 1)
        note = self.store.read(doc_id)
        self.assertIn("新增实验对象", note["markdown"])
        self.assertIn("从摘要可见该研究关注", note["markdown"])
        self.assertIn("innovation_hooks", note["markdown"])
        self.assertIn("full_text_verified: false", note["markdown"])
        self.assertEqual(note["analysis_count"], 1)
        self.assertEqual(len(self.store.search("变面积排气结构")), 1)

    def test_patent_and_untrusted_source_remain_unverified(self):
        item = patent(2)
        self.store.ingest_many([item])
        note = self.store.read(evidence_id(item))["markdown"]
        self.assertIn("metadata_from_provider: false", note)
        self.assertIn("尚未核实", note)
        self.assertIn("带排气支路", note)
        self.assertEqual(len(self.store.search("分离阀", kind="patent")), 1)
        self.assertEqual(self.store.search("分离阀", kind="paper"), [])

    def test_pagination_checkpoint_resume_and_cached_results(self):
        provider = PaginatedProvider()
        runner = LiteratureHarvester(self.store)
        partial = runner.harvest(
            provider, "cavitation fire pump",
            budget=HarvestBudget(max_documents=5, page_size=2, max_pages=1),
        )
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["records_seen"], 2)
        self.assertEqual(provider.calls[0][1], "*")
        completed = runner.harvest(
            provider, "cavitation fire pump",
            budget=HarvestBudget(max_documents=5, page_size=2, max_pages=2),
        )
        self.assertEqual(completed["status"], "complete")
        self.assertTrue(completed["resumed"])
        self.assertEqual(provider.calls[-1][1], "PAGE-2")
        cached = runner.harvest(provider, "cavitation fire pump")
        self.assertEqual(cached["status"], "cached_complete")
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(self.store.stats()["by_kind"]["paper"]["documents"], 3)

    def test_pages_are_retained_on_partial_error(self):
        class Broken(PaginatedProvider):
            def search_page(self, query, *, cursor=None, limit=100):
                if cursor == "PAGE-2":
                    raise PatentWorkflowError("HTTP 429 budget")
                return super().search_page(query, cursor=cursor, limit=limit)

        response = LiteratureHarvester(self.store).harvest(
            Broken(), "pump", budget=HarvestBudget(page_size=2, max_pages=3),
        )
        self.assertEqual(response["status"], "failed")
        self.assertIn("HTTP 429", response["error"])
        self.assertEqual(self.store.stats()["by_kind"]["paper"]["documents"], 2)

    def test_official_provider_paging_uses_cursors(self):
        def openalex_fetch(url, **kwargs):
            params = parse_qs(urlsplit(url).query)
            self.assertEqual(params["cursor"], ["*"])
            self.assertEqual(params["per_page"], ["2"])
            return {
                "results": [{
                    "id": "https://openalex.org/W100",
                    "display_name": "Hydraulics", "publication_date": "2026-01-01",
                }, {
                    "id": "https://openalex.org/W101",
                    "display_name": "Hydraulic piping",
                }],
                "meta": {"next_cursor": "CURSOR-NEXT", "count": 10000},
            }

        a = OpenAlexProvider(fetch_json=openalex_fetch).search_page(
            "pump", cursor="*", limit=2,
        )
        self.assertEqual(a["next_cursor"], "CURSOR-NEXT")
        self.assertEqual(len(a["records"]), 2)

        def crossref_fetch(url, **kwargs):
            params = parse_qs(urlsplit(url).query)
            self.assertEqual(params["cursor"], ["*"])
            return {"message": {
                "items": [{"DOI": "10.1000/abc", "title": ["X"]}],
                "next-cursor": "SHOULD-NOT-BE-USED",
            }}

        b = CrossrefProvider(fetch_json=crossref_fetch).search_page(
            "pump", cursor="*", limit=2,
        )
        self.assertIsNone(b["next_cursor"])  # 页数不足单页容量即结束

    def test_missing_note_can_be_repaired_from_evidence(self):
        item = paper(999)
        self.store.ingest_many([item])
        path = Path(self.store.read(evidence_id(item))["path"])
        path.unlink()
        self.assertEqual(self.store.ingest_many([item])["updated"], 1)
        self.assertTrue(path.exists())

    def test_per_project_mcp_service_tools(self):
        from mechanical_patent.mcp_server import PatentMCPService
        service = PatentMCPService(self.root / "service")
        service.create_case("PROJECT-1", "高海拔消防泵")
        doc = paper(7)
        service._memory("PROJECT-1").ingest_many([doc])
        self.assertEqual(len(service.literature_search("PROJECT-1", "消防泵")["matches"]), 1)
        read = service.literature_read("PROJECT-1", evidence_id(doc))
        self.assertIn("摘要", read["markdown"])
        service.literature_note(
            "PROJECT-1", evidence_id(doc), analyst="AI", basis="abstract",
            analysis={"technical_mechanism": "泵进口局部压力降低（尚未核实）。"},
        )
        self.assertEqual(service.literature_stats("PROJECT-1")["by_kind"]["paper"]["analyzed"], 1)
        service.create_case("PROJECT-2", "其他项目")
        with self.assertRaises(PatentWorkflowError):
            service.literature_read("PROJECT-2", evidence_id(doc))
        with self.assertRaises(PatentWorkflowError):
            service.literature_harvest("PROJECT-1", "openalex", "secret")


if __name__ == "__main__":
    unittest.main()
