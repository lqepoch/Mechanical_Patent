"""Offline unit tests: no credentials and no AI inference APIs."""
import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.core import (
    Evidence, PatentWorkflowError, coverage, deduplicate, evidence_id,
    save_json, validate_draft,
)
from mechanical_patent.providers import ImportedPatentProvider, parse_epo_xml


def patent(verified=True, claims="1. A pump device"):
    return Evidence(
        publication="CN123456789A", title="Pump control",
        url="https://example.org/record/1",
        source="test-provider", retrieved_at="2026-11-18T00:00:00+00:00",
        claims=claims, abstract="Adaptive inlet control", jurisdiction="CN",
        verified=verified,
    )


class EvidenceTests(unittest.TestCase):
    def test_https_and_ids(self):
        self.assertTrue(evidence_id(patent()).startswith("EV-"))
        with self.assertRaises(ValueError):
            Evidence(publication="CN123", title="A", source="test",
                     url="http://example.com", retrieved_at="now")

    def test_deduplicate_and_coverage(self):
        result = deduplicate([patent(False, ""), patent()])
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].verified)
        self.assertEqual(coverage(result, [])["patents_with_claims"], 1)
        self.assertFalse(coverage(result, [])["global_exhaustiveness_confirmed"])

    def test_imported_source_is_unverified(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "input.json"
            file.write_text(json.dumps({"records": [patent().to_dict()]}), encoding="utf-8")
            values = ImportedPatentProvider(file).search("pump")
            self.assertEqual(len(values), 1)
            self.assertFalse(values[0].verified)

    def test_atomic_json(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "case" / "record.json"
            self.assertEqual(len(save_json(file, {"hello": "world"})), 64)
            self.assertEqual(json.loads(file.read_text()), {"hello": "world"})

    def test_epo_claims_not_in_biblio(self):
        xml = b'''<ops:world-patent-data xmlns:ops="http://ops.epo.org"
                    xmlns:ex="http://www.epo.org/exchange">
          <ex:exchange-document country="CN" doc-number="123456789" kind="A">
             <ex:invention-title>Adaptive Pump</ex:invention-title>
          </ex:exchange-document></ops:world-patent-data>'''
        item = parse_epo_xml(xml)[0]
        self.assertEqual(item.publication, "CN123456789A")
        self.assertFalse(item.claims)

    def test_claim_to_specification_passage(self):
        draft = {
            "title": "Adaptive pump", "abstract": "A structure",
            "claims": ["1. Device including a regulated inlet."],
            "description": {k: "Engineering description" for k in (
                "technical_field", "background", "technical_problem", "technical_solution",
                "beneficial_effects", "embodiments", "drawings")},
            "claim_support": [{"claim": 1, "specification_passage": "Engineering description"}],
        }
        idea = {"mechanism": "valve", "enabling_details": "valve moves"}
        self.assertEqual(validate_draft(draft, [patent()], idea), [])
        draft["claim_support"] = [{"claim": 1, "specification_passage": "Unrelated statement"}]
        self.assertIn("Claim 1 support passage is absent from description.",
                      validate_draft(draft, [patent()], idea))


if __name__ == "__main__":
    unittest.main()
