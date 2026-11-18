"""合法论文全文处理：授权门禁、归档幂等、项目隔离与页码搜索。"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mechanical_patent.core import Evidence, PatentWorkflowError, evidence_id
from mechanical_patent.literature_fulltext import LiteratureFullText, RIGHTS_BASES
from mechanical_patent.literature_memory import LiteratureMemoryStore
from mechanical_patent.mcp_server import PatentMCPService


PDF_ONE = b"%PDF-1.7\n" + b"A" * 1500 + b"\n%%EOF"
PDF_TWO = b"%PDF-1.7\n" + b"B" * 1510 + b"\n%%EOF"


class Converter:
    def __init__(self):
        self.calls = 0

    def convert(self, filename, **kwargs):
        self.calls += 1
        assert Path(filename).is_file()
        assert kwargs["max_num_pages"] == 200
        box = SimpleNamespace(l=1.0, t=2.0, r=300.0, b=40.0)
        blocks = [
            SimpleNamespace(
                text="The NPSH inlet threshold is reduced at high altitude.",
                label="paragraph", prov=[SimpleNamespace(page_no=1, bbox=box)],
            ),
            SimpleNamespace(
                text="A second page compares cavitation and air separation.",
                label="paragraph", prov=[SimpleNamespace(page_no=2, bbox=box)],
            ),
        ]
        doc = SimpleNamespace(
            iterate_items=lambda: ((block, 0) for block in blocks),
            pages={1: {}, 2: {}},
        )
        return SimpleNamespace(document=doc)


class FullTextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "case-test"
        self.memory = LiteratureMemoryStore(self.project)
        self.publication = "10.1234/cavitation.test"
        self.paper = Evidence(
            publication=self.publication, title="High altitude cavitation",
            url="https://doi.org/" + self.publication,
            source="openalex", retrieved_at="2026-11-19T00:00:00Z",
            kind="paper", abstract="Cavitation mechanics", verified=True,
            pdf_url="https://repository.example.org/accepted.pdf",
            paper_metadata={
                "doi": self.publication, "license": "cc-by",
                "sources": ["openalex"], "authors": ["Scientist"],
                "full_text_verified": False,
            },
        )
        self.memory.ingest_many([self.paper])
        self.doc_id = evidence_id(self.paper)
        self.pipeline = LiteratureFullText(self.memory)
        self.pdf = Path(self.temp.name) / "source.pdf"
        self.pdf.write_bytes(PDF_ONE)

    def import_pdf(self, source=None):
        return self.pipeline.import_local(
            self.doc_id, source or self.pdf, authorized=True,
            rights_basis="cc-by", rights_reference="https://creativecommons.org/licenses/by/4.0/",
        )

    def test_staged_pdf_and_explicit_rights(self):
        result = self.import_pdf()
        self.assertEqual(result["state"], "staged")
        self.assertFalse(result["full_text_verified"])
        self.assertEqual(result["pdf_sha256"], sha256(PDF_ONE).hexdigest())
        archived = self.pipeline.root / result["pdf_relpath"]
        self.assertTrue(archived.is_file())
        self.assertEqual(archived.read_bytes(), PDF_ONE)
        self.assertEqual(result["rights_basis"], "cc-by")
        self.assertEqual(result["source_url"], self.paper.url)
        self.assertNotIn(str(self.temp.name), result["pdf_relpath"])

    def test_unapproved_or_unknown_license_blocks_ingestion(self):
        with self.assertRaises(PatentWorkflowError):
            self.pipeline.import_local(
                self.doc_id, self.pdf, authorized=False, rights_basis="cc-by",
                rights_reference="https://creativecommons.org/licenses/by/4.0/",
            )
        with self.assertRaises(PatentWorkflowError):
            self.pipeline.import_local(
                self.doc_id, self.pdf, authorized=True, rights_basis="cc-by-nc",
                rights_reference="https://creativecommons.org/licenses/by-nc/4.0/",
            )
        with self.assertRaises(PatentWorkflowError):
            self.pipeline.import_local(
                self.doc_id, self.pdf, authorized=True, rights_basis="cc-by",
                rights_reference="x",
            )
        self.assertEqual(self.pipeline.status(self.doc_id)["state"], "not_available")
        self.assertNotIn("cc-by-nc", RIGHTS_BASES)

    def test_wrong_file_or_symlink_rejected(self):
        invalid = Path(self.temp.name) / "fake.pdf"
        invalid.write_bytes(b"PDF incorrect content")
        with self.assertRaises(PatentWorkflowError):
            self.import_pdf(invalid)
        link = Path(self.temp.name) / "link.pdf"
        try:
            link.symlink_to(self.pdf)
        except OSError:
            self.skipTest("symlinks not available")
        with self.assertRaises(PatentWorkflowError):
            self.import_pdf(link)

    def test_parse_search_page_and_pdf_hash_links(self):
        self.import_pdf()
        converter = Converter()
        result = self.pipeline.parse(
            self.doc_id, authorized=True, converter=converter,
        )
        self.assertEqual(converter.calls, 1)
        self.assertEqual(result["state"], "parsed_unreviewed")
        self.assertEqual(result["block_count"], 2)
        self.assertFalse(result["full_text_verified"])
        self.assertEqual(result["page_count"], 2)
        hits = self.pipeline.search("NPSH", doc_id=self.doc_id)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["page"], 1)
        self.assertEqual(hits[0]["bbox"]["l"], 1.0)
        self.assertEqual(hits[0]["pdf_sha256"], result["pdf_sha256"])
        page = self.pipeline.page(self.doc_id, 2)
        self.assertEqual(len(page["blocks"]), 1)
        self.assertIn("cavitation", page["blocks"][0]["text"])
        self.assertEqual(self.pipeline.search("unrelated"), [])

    def test_reparse_idempotent_and_reingest_preserves_notes(self):
        self.import_pdf()
        self.pipeline.parse(self.doc_id, authorized=True, converter=Converter())
        self.import_pdf()
        self.assertEqual(self.pipeline.status(self.doc_id)["state"], "parsed_unreviewed")
        self.memory.write_analysis(
            self.doc_id, analyst="researcher", basis="abstract",
            analysis={"engineering_problem": "Need new inlet NPSH design"},
        )
        before = self.memory.read(self.doc_id)["markdown"]
        self.memory.ingest_many([self.paper])
        after = self.memory.read(self.doc_id)["markdown"]
        self.assertIn("Need new inlet NPSH design", before)
        self.assertIn("Need new inlet NPSH design", after)
        self.assertEqual(self.pipeline.status(self.doc_id)["block_count"], 2)

    def test_new_pdf_revision_invalidates_old_index(self):
        self.import_pdf()
        self.pipeline.parse(self.doc_id, authorized=True, converter=Converter())
        other = Path(self.temp.name) / "updated.pdf"
        other.write_bytes(PDF_TWO)
        self.import_pdf(other)
        self.assertEqual(self.pipeline.status(self.doc_id)["state"], "staged")
        self.assertEqual(self.pipeline.search("NPSH"), [])
        self.pipeline.parse(self.doc_id, authorized=True, converter=Converter())
        self.assertEqual(len(self.pipeline.search("NPSH")), 1)

    def test_pdf_mutation_fails_closed(self):
        archived = self.import_pdf()
        file = self.pipeline.root / archived["pdf_relpath"]
        file.write_bytes(PDF_TWO)
        with self.assertRaises(PatentWorkflowError):
            self.pipeline.parse(self.doc_id, authorized=True, converter=Converter())
        self.assertEqual(self.pipeline.status(self.doc_id)["state"], "staged")

    def test_fetch_only_uses_stored_pdf_candidate_and_approved_host(self):
        requests = []
        def fake_downloader(url, destination_dir, *, allowed_hosts, max_bytes):
            requests.append((url, allowed_hosts, max_bytes))
            self.assertEqual(url, "https://repository.example.org/accepted.pdf")
            self.assertEqual(allowed_hosts, {"repository.example.org"})
            output = Path(destination_dir) / (sha256(PDF_ONE).hexdigest() + ".pdf")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(PDF_ONE)
            return {
                "local_pdf_path": str(output), "sha256": sha256(PDF_ONE).hexdigest(),
                "bytes": len(PDF_ONE),
            }
        args = dict(
            allowed_hosts={"repository.example.org"}, authorized=True,
            rights_basis="cc-by", rights_reference="https://creativecommons.org/licenses/by/4.0/",
            download=fake_downloader,
        )
        with self.assertRaises(PatentWorkflowError):
            self.pipeline.fetch(self.doc_id, outbound_approved=False, **args)
        self.assertEqual(requests, [])
        result = self.pipeline.fetch(self.doc_id, outbound_approved=True, **args)
        self.assertEqual(len(requests), 1)
        self.assertEqual(result["state"], "staged")
        self.assertEqual(result["source_url"], self.paper.pdf_url)

    def test_no_pdf_url_forbids_remote_fetch(self):
        other = Evidence(
            publication="10.1234/no.pdf", title="No PDF",
            url="https://doi.org/10.1234/no.pdf", source="crossref",
            retrieved_at="2026-01-01", kind="paper",
        )
        self.memory.ingest_many([other])
        with self.assertRaises(PatentWorkflowError):
            self.pipeline.fetch(
                evidence_id(other), allowed_hosts={"example.org"},
                authorized=True, rights_basis="written-permission",
                rights_reference="INTERNAL-AUTH-CASE123",
                outbound_approved=True,
            )

    def test_invalid_doc_id_and_cross_project_isolation(self):
        with self.assertRaises(PatentWorkflowError):
            self.pipeline.status("../../private")
        independent = LiteratureFullText(LiteratureMemoryStore(Path(self.temp.name) / "other"))
        with self.assertRaises(PatentWorkflowError):
            independent.status(self.doc_id)
        self.assertEqual(independent.search("NPSH"), [])

    def test_existing_metadata_migration(self):
        with self.memory.connect() as db:
            columns = {r["name"] for r in db.execute("PRAGMA table_info(documents)")}
        self.assertIn("pdf_url", columns)
        self.assertIn("paper_metadata_json", columns)
        again = LiteratureMemoryStore(self.project)
        self.assertEqual(
            again.read(self.doc_id)["doc_id"], self.doc_id,
        )
        self.assertEqual(
            LiteratureFullText(again).status(self.doc_id)["state"], "not_available",
        )

    def test_mcp_read_tools_use_bound_case(self):
        service = PatentMCPService(Path(self.temp.name) / "mcp", project_id="tenant-a")
        service.create_case("MCP-1", "hydraulics")
        store = service._memory("MCP-1")
        store.ingest_many([self.paper])
        with self.assertRaises(PatentWorkflowError):
            service.literature_fulltext_status("unknown", self.doc_id)
        status = service.literature_fulltext_status("MCP-1", self.doc_id)
        self.assertEqual(status["state"], "not_available")
        self.assertEqual(
            service.literature_fulltext_search("MCP-1", "cavitation")["count"], 0,
        )


if __name__ == "__main__":
    unittest.main()
