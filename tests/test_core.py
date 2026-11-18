import json
import tempfile
import unittest
from pathlib import Path

from mechanical_patent.core import Evidence, coverage, deduplicate, evidence_id, save_json, validate_draft, PatentWorkflowError
from mechanical_patent.providers import ImportedPatentProvider, parse_epo_xml
from mechanical_patent.llm import JSONGateway


def patent(verified=True, claims="1. A pump device"):
    return Evidence(publication="CN123456789A", title="Pump control", url="https://example.org/record/1",
                    source="test-provider", retrieved_at="2026-11-18T00:00:00+00:00",
                    claims=claims, abstract="Adaptive inlet control", jurisdiction="CN", verified=verified)


class EvidenceTests(unittest.TestCase):
    def test_https_and_ids(self):
        self.assertTrue(evidence_id(patent()).startswith("EV-"))
        with self.assertRaises(ValueError):
            Evidence(publication="CN123", title="A", source="test", url="http://example.com",
                     retrieved_at="today")

    def test_deduplication_and_coverage(self):
        items = deduplicate([patent(False, ""), patent()])
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].verified)
        self.assertEqual(coverage(items, [])["patents_with_claims"], 1)
        self.assertFalse(coverage(items, [])["global_exhaustiveness_confirmed"])

    def test_import_cannot_assert_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "patents.json"
            path.write_text(json.dumps({"records": [patent().to_dict()]}), encoding="utf-8")
            result = ImportedPatentProvider(path).search("pump")
            self.assertEqual(len(result), 1)
            self.assertFalse(result[0].verified)

    def test_atomic_case_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nested" / "case.json"
            digest = save_json(path, {"hello": "patent"})
            self.assertEqual(len(digest), 64)
            self.assertEqual(json.loads(path.read_text()), {"hello": "patent"})

    def test_epo_xml_namespace_parser(self):
        xml = b'''<?xml version="1.0"?>
        <ops:world-patent-data xmlns:ops="http://ops.epo.org" xmlns:ex="http://www.epo.org/exchange">
          <ops:search-result>
            <ex:exchange-document country="CN" doc-number="123456789" kind="A">
              <ex:invention-title>Adaptive pump</ex:invention-title>
              <ex:publication-reference><ex:document-id><ex:date>20261118</ex:date></ex:document-id></ex:publication-reference>
            </ex:exchange-document>
          </ops:search-result>
        </ops:world-patent-data>'''
        result = parse_epo_xml(xml)
        self.assertEqual(result[0].publication, "CN123456789A")
        self.assertTrue(result[0].verified)
        self.assertFalse(result[0].claims)

    def test_draft_support_gate(self):
        draft = {
            "title": "Adaptive pump", "abstract": "A structure",
            "claims": ["1. Device including a regulated inlet."],
            "description": {k: "text" for k in (
                "technical_field", "background", "technical_problem", "technical_solution",
                "beneficial_effects", "embodiments", "drawings")},
            "claim_support": [{"claim": 1, "specification_passage": "Regulated inlet disclosed in embodiment 1"}],
        }
        self.assertEqual(validate_draft(draft, [patent()], {"mechanism": "m", "enabling_details": "e"}), [])
        self.assertTrue(any("source-verified" in x for x in validate_draft(
            draft, [patent(False)], {"mechanism": "m", "enabling_details": "e"})))

    def test_remote_model_opt_in(self):
        with self.assertRaises(PatentWorkflowError):
            JSONGateway(base_url="https://remote.example.org/v1", allow_external=False)
        with self.assertRaises(PatentWorkflowError):
            JSONGateway(base_url="http://remote.example.org/v1", allow_external=True)
        self.assertEqual(JSONGateway(base_url="https://remote.example.org/v1",
                                     allow_external=True).model, "qwen3")


if __name__ == "__main__":
    unittest.main()
