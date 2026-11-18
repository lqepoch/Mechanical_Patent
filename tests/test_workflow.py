import json
import tempfile
import unittest
from pathlib import Path

from mechanical_patent.core import Evidence
from mechanical_patent.workflow import PatentResearch


class FakeProvider:
    name = "mock-provider"

    def __init__(self, verified=True):
        self.verified = verified
        self.queries = []

    def search(self, term, *, limit=10):
        self.queries.append(term)
        return [Evidence(
            publication="CN123456789A", title="Prior art control system",
            source="mock-evidence", url="https://example.org/CN123456789A",
            retrieved_at="2026-11-18T00:00:00+00:00", jurisdiction="CN",
            claims="1. A flow regulating valve" if self.verified else "",
            abstract="Valve mechanism", verified=self.verified,
        )]


class FakeModel:
    model = "deterministic-model"

    def ask(self, role, instructions, payload):
        if role == "SEARCH_STRATEGIST":
            return {"queries": ["pump inlet", "pump valve", "吸水控制"]}
        if role == "LANDSCAPE_ANALYST":
            return {"routes": ["valves"], "known_problems": ["cavitation"], "gaps": ["response time"]}
        if role.startswith("INVENTOR_"):
            return {"ideas": [{"title": "Adaptive dual valve",
                               "mechanism": "Two valves are actuated in order",
                               "enabling_details": "A sensor commands valve B after valve A",
                               "technical_problem": "Reduce inlet transients",
                               "expected_effect": "Lower pressure spikes"}]}
        if role == "INDEPENDENT_PRIOR_ART_CHALLENGER":
            return {"adversarial_queries": ["dual valve"], "claim_chart": [], "obviousness_risks": []}
        if role == "INDEPENDENT_ENGINEERING_VERIFIER":
            return {"theoretical_feasibility": "plausible",
                    "physical_principle": "Valve sequencing", "validation_tests": ["Transient flow test"]}
        if role == "CN_INVENTION_PATENT_DRAFTER":
            return {
                "title": "A dual-valve pump inlet", "abstract": "A sequenced pair of inlet valves.",
                "claims": ["1. A pump inlet with valves A and B."],
                "claim_support": [{"claim": 1, "specification_passage": "Embodiment: two valves A and B."}],
                "description": {key: "Engineering description" for key in (
                    "technical_field", "background", "technical_problem", "technical_solution",
                    "beneficial_effects", "embodiments", "drawings")},
                "figure_plan": ["Valve arrangement"],
            }
        raise AssertionError("Unexpected role " + role)


class ResearchTests(unittest.TestCase):
    def test_evidence_driven_research_to_review(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case"
            p = FakeProvider()
            result = PatentResearch(p, FakeModel(), path, max_ideas=3).run("Improve pump inlet")
            self.assertEqual(result["status"], "needs_human_review")
            self.assertFalse(result["filing_authorized"])
            self.assertTrue((path / "DOSSIER.md").is_file())
            self.assertTrue((path / "09_quality_gate.json").is_file())
            self.assertTrue((path / "manifest.json").is_file())
            self.assertGreater(len(p.queries), 3)
            self.assertEqual(len(json.loads((path / "04_inventions.json").read_text())["candidates"]), 3)

    def test_unverified_corpus_remains_research_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case"
            result = PatentResearch(FakeProvider(verified=False), FakeModel(), path,
                                    max_ideas=1).run("Improve pump inlet")
            self.assertEqual(result["status"], "research_only")
            self.assertTrue(any("verified" in issue for issue in result["issues"]))
            self.assertFalse(result["filing_authorized"])

    def test_no_silent_reuse_of_dossier(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case"
            PatentResearch(FakeProvider(), FakeModel(), path, max_ideas=1).run("Pump")
            with self.assertRaises(FileExistsError):
                PatentResearch(FakeProvider(), FakeModel(), path)


if __name__ == "__main__":
    unittest.main()
