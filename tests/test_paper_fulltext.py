"""Copyright-aware paper PDF storage, local parsing and durable page-level provenance."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.core import Evidence, PatentWorkflowError, evidence_id
from mechanical_patent.literature_memory import LiteratureMemoryStore
from mechanical_patent.paper_fulltext import PaperFullTextService


PDF = b"%PDF-1.4\n1 0 obj\n<</Type/Catalog>>\nendobj\n%%EOF\n"
URL = "https://repository.example.org/article.pdf"


def paper(*, provider="openalex", title="A pump paper", abstract="Cavitation model",
          pdf_url=URL):
    return Evidence(
        kind="paper", publication="10.5555/pump.study", title=title,
        abstract=abstract, url="https://doi.org/10.5555/pump.study",
        source=provider, retrieved_at="2026-11-19T00:00:00+00:00",
        verified=True, pdf_url=pdf_url,
        paper_metadata={"doi": "10.5555/pump.study", "authors": ["A Researcher"],
                        "sources": [provider], "source_ids": {provider: "W100"},
                        "license": "cc-by", "full_text_verified": False}
    )


class FullTextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.memory = LiteratureMemoryStore(Path(self.temp.name) / "case-001")
        original = paper()
        self.doc_id = evidence_id(original)
        self.memory.ingest_many([original])
        self.calls = {"download": 0, "parse": 0}

        def fake_download(url, destination_dir, *, allowed_hosts, max_bytes):
            self.assertEqual(url, URL)
            self.assertEqual(allowed_hosts, {"repository.example.org"})
            self.assertGreater(max_bytes, len(PDF))
            self.calls["download"] += 1
            folder = Path(destination_dir)
            result = folder / (sha256(PDF).hexdigest() + ".pdf")
            result.write_bytes(PDF)
            return {"local_pdf_path": str(result), "sha256": sha256(PDF).hexdigest(),
                    "online_url": url, "bytes": len(PDF)}

        def fake_parse(original_path, output_path, *,
                       authorized, source_url, artifacts, converter, max_pages):
            self.assertTrue(authorized)
            self.assertEqual(source_url, URL)
            self.assertEqual(Path(original_path).read_bytes(), PDF)
            self.calls["parse"] += 1
            payload = {
                "source_pdf_sha256": sha256(PDF).hexdigest(),
                "blocks": [{"page": 1, "block": 1, "label": "paragraph",
                            "text": "7 m suction has insufficient NPSH", "bbox": None},
                           {"page": 2, "block": 2, "label": "formula",
                            "text": "NPSHa = atmospheric head - static lift", "bbox": None}],
                "review_status": "awaiting_original_pdf_review",
            }
            Path(output_path).write_text(json.dumps(payload), encoding="utf-8")
            return {"output": str(output_path), "blocks": 2,
                    "sha256": payload["source_pdf_sha256"], "status": "awaiting_original_pdf_review"}

        self.service = PaperFullTextService(self.memory, downloader=fake_download, parser=fake_parse)

    def _download(self):
        return self.service.download(
            self.doc_id, authorized=True, allowed_hosts={"repository.example.org"},
            rights_basis="open_license", rights_reference="CC BY license on repository metadata",
        )

    def test_permission_and_rights_fail_closed_before_network(self):
        with self.assertRaises(PatentWorkflowError):
            self.service.download(
                self.doc_id, authorized=False, allowed_hosts={"repository.example.org"},
                rights_basis="open_license", rights_reference="License verified",
            )
        with self.assertRaises(PatentWorkflowError):
            self.service.download(
                self.doc_id, authorized=True, allowed_hosts={"repository.example.org"},
                rights_basis="unknown", rights_reference="License verified",
            )
        with self.assertRaises(PatentWorkflowError):
            self.service.download(
                self.doc_id, authorized=True, allowed_hosts=set(),
                rights_basis="open_license", rights_reference="License verified",
            )
        self.assertEqual(self.calls["download"], 0)
        self.assertEqual(self.service.status(self.doc_id)["state"], "not_downloaded")

    def test_download_parse_page_evidence_and_durable_markdown(self):
        initial = self.memory.read(self.doc_id)["markdown"]
        self.memory.write_analysis(self.doc_id, analyst="Engineer", basis="abstract",
                                   analysis={"open_questions": "Has cavitation been tested at altitude?"})
        x = self._download()
        self.assertEqual(x["state"], "downloaded")
        self.assertEqual(x["pdf_sha256"], sha256(PDF).hexdigest())
        self.assertEqual(self.calls["download"], 1)
        self._download()
        self.assertEqual(self.calls["download"], 1)
        parsed = self.service.parse(self.doc_id, authorized=True, converter=object())
        self.assertEqual(parsed["state"], "parsed_unverified")
        self.assertFalse(parsed["full_text_verified"])
        self.assertEqual(self.service.pages(self.doc_id, page=2)["blocks"][0]["block"], 2)
        self.assertEqual(self.service.pages(self.doc_id, page=1)["review_status"],
                         "awaiting_original_pdf_review")
        with self.assertRaises(PatentWorkflowError):
            self.service.pages(self.doc_id, page=601)
        note = self.memory.read(self.doc_id)["markdown"]
        self.assertIn("Has cavitation been tested at altitude?", note)
        self.assertIn(sha256(PDF).hexdigest(), note)
        self.assertIn("机器提取", note)
        self.assertIn("full_text_verified: false", note)
        self.assertEqual(self.memory.read(self.doc_id)["analysis_count"], 1)
        self.memory.ingest_many([paper(provider="crossref", abstract="Longer new abstract")])
        note2 = self.memory.read(self.doc_id)["markdown"]
        self.assertIn("Has cavitation been tested at altitude?", note2)
        self.assertIn("机器提取", note2)
        self.assertEqual(self.memory.paper_source(self.doc_id)["paper_metadata"]["sources"],
                         ["openalex", "crossref"])
        self.assertTrue(len(note2) > len(initial))

    def test_bad_pdf_hash_and_outside_project_do_not_parse(self):
        x = self._download()
        Path(x["pdf_local_path"]).write_bytes(b"%PDF-1.4\ncorrupted")
        with self.assertRaises(PatentWorkflowError):
            self.service.parse(self.doc_id, authorized=True, converter=object())
        self.assertEqual(self.calls["parse"], 0)
        self.assertEqual(self.service.status(self.doc_id)["state"], "downloaded")

    def test_parser_failure_is_recoverable_and_keeps_pdf(self):
        downloaded = self._download()
        def fail(*_args, **_kwargs):
            raise PatentWorkflowError("offline Docling models absent")
        broken = PaperFullTextService(self.memory, downloader=self.service.download_impl, parser=fail)
        with self.assertRaises(PatentWorkflowError):
            broken.parse(self.doc_id, authorized=True, converter=object())
        self.assertEqual(broken.status(self.doc_id)["state"], "parse_failed")
        self.assertTrue(Path(downloaded["pdf_local_path"]).is_file())
        retried = self.service.parse(self.doc_id, authorized=True, converter=object())
        self.assertEqual(retried["state"], "parsed_unverified")

    def test_doi_oa_enrichment_preserves_abstract_and_requires_permission(self):
        from mechanical_patent.paper_sources import UnpaywallEnricher
        def fetched(url):
            self.assertIn("10.5555/pump.study", url)
            return {"is_oa": True, "oa_status": "green",
                    "best_oa_location": {"url_for_pdf": URL, "license": "cc-by"}}
        enricher = UnpaywallEnricher(
            contact_email="researcher@example.org", fetch_json=fetched,
        )
        original = Evidence(
            kind="paper", publication="10.5555/second",
            title="OA lookup source", url="https://doi.org/10.5555/second",
            source="crossref", retrieved_at="2026-11-19", verified=True,
            abstract="A complete preserved abstract",
            paper_metadata={"doi": "10.5555/second", "sources": ["crossref"]},
        )
        second = evidence_id(original)
        self.memory.ingest_many([original])
        with self.assertRaises(PatentWorkflowError):
            self.service.enrich_oa(second, authorized=False, enricher=enricher)
        def second_fetch(_url):
            return {"is_oa": True, "oa_status": "green",
                    "best_oa_location": {"url_for_pdf": URL, "license": "cc-by"}}
        result = self.service.enrich_oa(
            second, authorized=True,
            enricher=UnpaywallEnricher(contact_email="researcher@example.org",
                                      fetch_json=second_fetch),
        )
        self.assertEqual(result["pdf_url"], URL)
        note = self.memory.read(second)["markdown"]
        self.assertIn("A complete preserved abstract", note)
        self.assertEqual(
            self.memory.paper_source(second)["paper_metadata"]["sources"],
            ["crossref", "unpaywall"],
        )
        self.assertFalse(result["full_text_verified"])

    def test_no_pdf_source_cannot_download_or_process(self):
        second = Evidence(kind="paper", publication="arxiv:9999.12345",
                          title="No fulltext", url="https://arxiv.org/abs/9999.12345",
                          source="arxiv", retrieved_at="2026-11-19", verified=True)
        self.memory.ingest_many([second])
        with self.assertRaises(PatentWorkflowError):
            self.service.download(
                evidence_id(second), authorized=True,
                allowed_hosts={"arxiv.org"}, rights_basis="open_license",
                rights_reference="Rights page checked",
            )
        self.assertEqual(self.calls["download"], 0)

    def test_legacy_metadata_migration_preserves_analyst_notes(self):
        self.memory.ingest_many([paper()])
        after = LiteratureMemoryStore(Path(self.temp.name) / "case-001")
        self.assertEqual(after.paper_source(self.doc_id)["pdf_url"], URL)
        with after.connect() as db:
            cols = {r["name"] for r in db.execute("PRAGMA table_info(documents)")}
        self.assertTrue({"pdf_url", "paper_metadata_json"}.issubset(cols))


if __name__ == "__main__":
    unittest.main()
