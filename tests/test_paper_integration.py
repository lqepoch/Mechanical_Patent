"""Canonical literature memory: cross-source metadata, OA DOI enrichment and rights revocation."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from mechanical_patent.core import Evidence, PatentWorkflowError, evidence_id
from mechanical_patent.literature_memory import LiteratureMemoryStore
from mechanical_patent.literature_oa import enrich_unpaywall
from mechanical_patent.literature_fulltext import FulltextPipeline
from mechanical_patent.paper_sources import UnpaywallEnricher


def paper(source: str = "openalex", *, licensed: bool = True) -> Evidence:
    return Evidence(
        publication="10.4242/research.pump",
        title="High altitude cavitation mechanisms",
        url="https://doi.org/10.4242/research.pump",
        retrieved_at="2026-11-19T00:00:00+00:00",
        kind="paper", source=source, verified=True,
        abstract="A reference abstract about hydraulic pump cavitation.",
        pdf_url="https://repository.example.org/free.pdf" if licensed else "",
        paper_metadata={
            "doi": "10.4242/research.pump", "authors": ["Example Researcher"],
            "source_ids": {source: ("W123" if source == "openalex" else "CR-11")},
            "sources": [source],
            "is_open_access": True if licensed else None,
            "license": "cc-by-4.0" if licensed else "",
        },
    )


class IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.memory = LiteratureMemoryStore(self.root / "project-a")
        self.item = paper()
        self.doc_id = evidence_id(self.item)

    def test_repeated_provider_merges_same_doi_without_losing_analysis(self):
        self.memory.ingest_many([self.item])
        self.memory.write_analysis(
            self.doc_id, analyst="Engineer", basis="abstract",
            analysis={"innovation_hooks": "A variable suction geometry requires testing."},
        )
        crossref = paper("crossref", licensed=False)
        results = self.memory.ingest_many([crossref])
        self.assertEqual(results["updated"], 1)
        with self.memory.connect() as db:
            row = db.execute(
                "SELECT metadata_json,pdf_url FROM documents WHERE doc_id=?", (self.doc_id,)
            ).fetchone()
        import json
        meta = json.loads(row["metadata_json"])
        self.assertEqual(meta["sources"], ["openalex", "crossref"])
        self.assertEqual(meta["source_ids"]["openalex"], "W123")
        self.assertEqual(meta["source_ids"]["crossref"], "CR-11")
        self.assertEqual(row["pdf_url"], self.item.pdf_url)
        markdown = self.memory.read(self.doc_id)["markdown"]
        self.assertIn("A variable suction geometry", markdown)
        self.assertEqual(self.memory.read(self.doc_id)["analysis_count"], 1)

    def test_same_provider_license_revocation_blocks_fulltext_queue(self):
        self.memory.ingest_many([self.item])
        revoked = Evidence.from_dict({
            **self.item.to_dict(),
            "paper_metadata": {
                "doi": "10.4242/research.pump", "authors": ["Example Researcher"],
                "sources": ["openalex"], "is_open_access": False,
                "license": "all-rights-reserved",
            },
            "pdf_url": "",
        })
        self.memory.ingest_many([revoked])
        with self.memory.connect() as db:
            row = db.execute(
                "SELECT metadata_json,pdf_url FROM documents WHERE doc_id=?", (self.doc_id,)
            ).fetchone()
        import json
        meta = json.loads(row["metadata_json"])
        self.assertIs(meta["is_open_access"], False)
        self.assertEqual(row["pdf_url"], "")
        with self.assertRaises(PatentWorkflowError):
            FulltextPipeline(self.memory).queue(
                self.doc_id, rights_actor="IP reviewer",
                rights_reference="IPR-2026-REVOCATION", authorized=True,
            )

    def test_unpaywall_enrichment_requires_explicit_permission_and_keeps_notes(self):
        item = paper("crossref", licensed=False)
        self.memory.ingest_many([item])
        self.memory.write_analysis(
            self.doc_id, analyst="Research agent", basis="abstract",
            analysis={"plain_summary": "Study has no locally verified fulltext."},
        )
        def get(_url):
            return {
                "is_oa": True, "oa_status": "green",
                "best_oa_location": {
                    "url_for_pdf": "https://repository.example.org/accepted.pdf",
                    "license": "cc-by",
                },
            }
        source = UnpaywallEnricher(
            contact_email="reader@example.org", fetch_json=get,
        )
        with self.assertRaises(PatentWorkflowError):
            enrich_unpaywall(self.memory, self.doc_id, authorized=False, provider=source)
        outcome = enrich_unpaywall(self.memory, self.doc_id, authorized=True, provider=source)
        self.assertFalse(outcome["full_text_verified"])
        self.assertFalse(outcome["download_authorized"])
        self.assertEqual(outcome["oa_status"], "green")
        with self.memory.connect() as db:
            row = db.execute(
                "SELECT metadata_json,pdf_url FROM documents WHERE doc_id=?", (self.doc_id,)
            ).fetchone()
        import json
        self.assertEqual(row["pdf_url"], "https://repository.example.org/accepted.pdf")
        meta = json.loads(row["metadata_json"])
        self.assertEqual(meta["sources"], ["crossref", "unpaywall"])
        self.assertTrue(meta["is_open_access"])
        self.assertEqual(meta["license"], "cc-by")
        self.assertIn("Study has no locally verified fulltext", self.memory.read(self.doc_id)["markdown"])
        self.assertEqual(
            FulltextPipeline(self.memory).queue(
                self.doc_id, rights_actor="IP reviewer",
                rights_reference="IPR-2026-APPROVED", authorized=True,
            )["status"], "queued",
        )

    def test_project_isolation_after_enrichment(self):
        self.memory.ingest_many([self.item])
        another = LiteratureMemoryStore(self.root / "project-b")
        with self.assertRaises(PatentWorkflowError):
            enrich_unpaywall(another, self.doc_id, authorized=True)


if __name__ == "__main__":
    unittest.main()
