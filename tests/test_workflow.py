import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.core import Evidence
from mechanical_patent.workflow import PatentResearch, validate_case


class FakeProvider:
    def __init__(self, name, kind, verified=True):
        self.name, self.kind, self.verified = name, kind, verified
        self.queries = []

    def search(self, query, *, limit=10):
        self.queries.append(query)
        if self.kind == "patent":
            return [Evidence(
                publication="CN123456789A", title="Inlet valve control",
                url="https://example.org/CN123456789A", source=self.name,
                retrieved_at="2026-11-18T00:00:00+00:00", kind="patent",
                verified=self.verified, jurisdiction="CN",
                abstract="Mechanical inlet valve and pressure control",
                claims="1. A pump valve." if self.verified else "",
            )]
        return [Evidence(
            publication="10.1234/experimental-flow", title="Engineering journal paper",
            url="https://doi.org/10.1234/experimental-flow", source=self.name,
            retrieved_at="2026-11-18T00:00:00+00:00", kind="paper",
            verified=self.verified, abstract="Measured inlet flow in published study",
        )]


class ResearchTests(unittest.TestCase):
    def test_dual_source_research_with_no_model(self):
        with tempfile.TemporaryDirectory() as root:
            pat = FakeProvider("epo-mock", "patent")
            paper = FakeProvider("openalex-mock", "paper")
            case = Path(root) / "case"
            result = PatentResearch(pat, [paper], case).run(
                "Improve water pump", ["water inlet control"], ["pump hydraulic cavitation"])
            self.assertFalse(result["filing_authorized"])
            self.assertEqual(result["patent_claims_available"], 1)
            self.assertEqual(result["papers_discovered"], 1)
            self.assertEqual(pat.queries, ["water inlet control"])
            self.assertEqual(paper.queries, ["pump hydraulic cavitation"])
            self.assertTrue((case / "AGENT_NEXT_STEPS.md").exists())
            self.assertFalse((case / "08_application.json").read_text().find('"draft": null') == -1)
            self.assertEqual(len(json.loads((case / "04_evidence.json").read_text())["records"]), 2)

    def test_static_validation_blocks_empty_agent_output(self):
        with tempfile.TemporaryDirectory() as root:
            case = Path(root) / "case"
            PatentResearch(FakeProvider("mock", "patent"), [
                FakeProvider("mock-paper", "paper")
            ], case).run("Pump", ["inlet"], ["turbulence"])
            gate = validate_case(case)
            self.assertEqual(gate["status"], "research_incomplete")
            self.assertTrue(gate["issues"])
            self.assertFalse(gate["filing_authorized"])

    def test_imported_sources_do_not_forge_verified_claims(self):
        with tempfile.TemporaryDirectory() as root:
            case = Path(root) / "case"
            report = PatentResearch(FakeProvider("fixture", "patent", verified=False), [
                FakeProvider("fixture-paper", "paper", verified=False)
            ], case).run("Pump", ["inlet"], ["turbulence"])
            self.assertEqual(report["patent_claims_available"], 0)
            self.assertFalse(report["filing_authorized"])

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "case"
            PatentResearch(None, [], path).run("Pump")
            with self.assertRaises(FileExistsError):
                PatentResearch(None, [], path)


if __name__ == "__main__":
    unittest.main()
