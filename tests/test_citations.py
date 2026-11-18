"""公开 DOI 引证网络：原始来源、边方向、限额、案卷血缘与安全回归。"""
import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.citations import (
    OpenCitationsClient, normalize_doi, dois_in_pid_field, create_citation_graph,
)
from mechanical_patent.case_citations import update_case_citations
from mechanical_patent.core import PatentWorkflowError
from mechanical_patent.workflow import PatentResearch
from mechanical_patent.audit import verify_audit_chain


SEED = "10.5555/pump"
REFERENCE = "10.5555/physics"
FOLLOWUP = "10.5555/new-pump"


def mock_api(url: str):
    if "/references/" in url:
        return [
            {
                "citing": "omid:br/1 doi:10.5555/pump",
                "cited": "omid:br/2 doi:10.5555/physics",
                "oci": "abc-123", "creation": "2026-01-20",
            },
            {
                "citing": "doi:10.5555/pump",
                "cited": "doi:10.5555/physics",
            },
            {"citing": "doi:10.5555/other", "cited": "doi:10.5555/nope"},
        ]
    if "/citations/" in url:
        return [
            {
                "citing": "omid:br/3 doi:10.5555/new-pump",
                "cited": "omid:br/1 doi:10.5555/pump",
                "oci": "def-456", "creation": "2026-07-02",
            },
            {"citing": "unknown", "cited": "doi:10.5555/pump"},
        ]
    raise AssertionError("Unexpected test URL " + url)


class OpenCitationsTests(unittest.TestCase):
    def setUp(self):
        self.client = OpenCitationsClient(fetch_json=mock_api)

    def test_doi_parsing_and_pid_aliases(self):
        self.assertEqual(normalize_doi("https://doi.org/10.5555/PUMP"), SEED)
        self.assertEqual(normalize_doi("doi:10.5555/PUMP"), SEED)
        self.assertEqual(
            dois_in_pid_field("omid:br/10 openalex:W123 doi:10.5555/PHYSICS"),
            [REFERENCE],
        )
        for bad in ["", "https://private.local/secret", "../evil", "10.abc/invalid", "10.5555/xx?y"]:
            with self.subTest(bad=bad):
                with self.assertRaises(PatentWorkflowError):
                    normalize_doi(bad)

    def test_forward_and_backward_edges_are_grounded(self):
        graph = create_citation_graph([SEED], client=self.client)
        self.assertEqual(graph["status"], "complete_within_query_limits")
        self.assertEqual(len(graph["edges"]), 2)
        self.assertEqual(
            {(x["citing_doi"], x["cited_doi"]) for x in graph["edges"]},
            {(SEED, REFERENCE), (FOLLOWUP, SEED)},
        )
        self.assertEqual(len(graph["queries"]), 2)
        self.assertEqual({x["doi"] for x in graph["nodes"]}, {SEED, REFERENCE, FOLLOWUP})
        self.assertTrue(all(x["url"].startswith("https://api.opencitations.net/index/v2/")
                            for x in graph["queries"]))

    def test_rate_and_partial_failure_reporting(self):
        def failing(url):
            if "/citations/" in url:
                raise PatentWorkflowError("429 检索服务暂时限速")
            return mock_api(url)
        result = create_citation_graph([SEED],
            client=OpenCitationsClient(fetch_json=failing))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["edges"]), 1)
        self.assertEqual(len(result["errors"]), 1)
        with self.assertRaises(PatentWorkflowError):
            create_citation_graph([SEED] * 9, client=self.client)
        with self.assertRaises(PatentWorkflowError):
            create_citation_graph([SEED], client=self.client, max_links=1000)

    def test_save_batch_and_enrich_technology_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "research"
            PatentResearch(None, [], folder).run("研究低气压吸水泵的原理")
            before = verify_audit_chain(folder)
            self.assertTrue(before["valid"])
            self.assertEqual(before["count"], 1)
            result = update_case_citations(
                folder, [SEED], client=self.client, direction="both"
            )
            self.assertEqual(result["total_edges"], 2)
            self.assertEqual(result["total_nodes"], 3)
            evidence_graph = json.loads(
                (folder / "04b_technology_graph.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                len([e for e in evidence_graph["edges"] if e["relation"] == "引用"]), 2
            )
            self.assertEqual(
                len([n for n in evidence_graph["nodes"] if n["kind"] == "论文文献"]), 3
            )
            self.assertTrue(all(
                n["attributes"].get("verified") is False
                for n in evidence_graph["nodes"] if n["kind"] == "论文文献"
            ))
            archive_files = list((folder / "citation_batches").glob("*.json"))
            self.assertEqual(len(archive_files), 1)
            self.assertTrue(verify_audit_chain(folder)["valid"])
            self.assertEqual(verify_audit_chain(folder)["count"], 2)
            repeated = update_case_citations(
                folder, [SEED], client=self.client, direction="both"
            )
            self.assertEqual(repeated["total_edges"], 2)
            self.assertTrue(verify_audit_chain(folder)["valid"])
            self.assertEqual(verify_audit_chain(folder)["count"], 3)
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("04c_paper_citations.json", manifest["sha256"])
            self.assertFalse(result["filing_authorized"])

    def test_unknown_case_is_not_silently_created(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(PatentWorkflowError):
                update_case_citations(Path(folder), [SEED], client=self.client)


if __name__ == "__main__":
    unittest.main()
