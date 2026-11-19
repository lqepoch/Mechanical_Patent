"""已有合规全文流水线的页码锚点、短引及 Markdown 精读记忆的离线测试。"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.core import Evidence, PatentWorkflowError, evidence_id
from mechanical_patent.literature_fulltext import FulltextPipeline
from mechanical_patent.literature_memory import LiteratureMemoryStore
from mechanical_patent.mcp_server import PatentMCPService


def paper() -> Evidence:
    return Evidence(
        publication="10.4321/controlled-fire-pump",
        title="High-altitude pump cavitation",
        url="https://doi.org/10.4321/controlled-fire-pump",
        source="offline-test", retrieved_at="2026-11-19T00:00:00+00:00",
        kind="paper", verified=False, abstract="Cavitation at reduced inlet pressure.",
        pdf_url="https://repository.example.edu/cavitation.pdf",
        paper_metadata={
            "license": "cc-by-4.0", "is_open_access": True,
            "doi": "10.4321/controlled-fire-pump",
        },
    )


def fake_download(url, dest, *, allowed_hosts, max_bytes):
    assert url == "https://repository.example.edu/cavitation.pdf"
    assert allowed_hosts == {"repository.example.edu"}
    data = b"%PDF-1.4\n%synthetic public-domain CI fixture\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    digest = sha256(data).hexdigest()
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / (digest + ".pdf")
    path.write_bytes(data)
    return {"online_url": url, "local_pdf_path": str(path),
            "sha256": digest, "bytes": len(data)}


def fake_parser(path, output, *, authorized, source_url, artifacts, converter):
    assert authorized
    content = {
        "source_pdf_sha256": sha256(path.read_bytes()).hexdigest(),
        "source_url": source_url, "parser": "docling",
        "parser_version": "CI adapter",
        "review_status": "awaiting_original_pdf_review",
        "blocks": [
            {"page": 2, "block": 1, "label": "paragraph",
             "text": "Inlet cavitation decreases flow stability and increases acoustic noise."},
            {"page": 3, "block": 2, "label": "paragraph",
             "text": "One-way air discharge valves may reduce entrained air."},
            {"page": None, "block": 3, "label": "paragraph",
             "text": "Unnumbered appendix extract without a trustworthy page."},
        ],
    }
    output.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    return {"sha256": content["source_pdf_sha256"], "blocks": len(content["blocks"])}


class FullTextQuoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.memory = LiteratureMemoryStore(self.home / "project-one" / "cases" / "CASE-1")
        self.record = paper()
        self.doc_id = evidence_id(self.record)
        self.memory.ingest_many([self.record])
        self.pipeline = FulltextPipeline(self.memory)

    def parsed(self):
        self.pipeline.queue(
            self.doc_id, rights_actor="IP-review",
            rights_reference="LIC-2026-CI", authorized=True,
        )
        return self.pipeline.process(
            self.doc_id, allowed_hosts={"repository.example.edu"},
            authorized=True, downloader=fake_download,
            parser=fake_parser, converter=object(),
        )

    def test_fulltext_must_be_parsed_before_ai_claims_full_text(self):
        with self.assertRaises(PatentWorkflowError):
            self.memory.write_analysis(
                self.doc_id, analyst="AI", basis="full_text",
                analysis={"plain_summary": "Study"}, source_positions=["p2:b1"],
            )
        # Abstract-level notes remain possible without a PDF.
        saved = self.memory.write_analysis(
            self.doc_id, analyst="AI", basis="abstract",
            analysis={"plain_summary": "The abstract mentions low inlet pressure."},
        )
        self.assertEqual(saved["analysis_count"], 1)

    def test_current_page_anchor_and_exact_quote_and_note_hashes(self):
        state = self.parsed()
        self.assertEqual(state["status"], "parsed")
        anchor = self.pipeline.validate_positions(
            self.doc_id, ["p2:b1", "p3:b2"],
        )
        self.assertEqual(anchor["pdf_sha256"], state["pdf_sha256"])
        self.assertEqual(anchor["parse_sha256"], state["parse_sha256"])
        self.assertEqual(anchor["verification_level"], "parsed_text_anchor_only")
        good = self.pipeline.quote(
            self.doc_id, "p3:b2", "One-way air discharge valves",
        )
        self.assertTrue(good["exact_match"])
        self.assertEqual(good["verification_level"], "parsed_text_match_only")
        self.assertFalse(good["full_text_verified"])
        self.assertTrue(good["quote_sha256"])
        bad = self.pipeline.quote(self.doc_id, "p3:b2", "perpetual energy output")
        self.assertFalse(bad["exact_match"])
        self.assertIsNone(bad["quote_sha256"])
        note = self.memory.write_analysis(
            self.doc_id, analyst="Researcher", basis="full_text",
            analysis={
                "plain_summary": "The parser reports a one-way discharge valve on page 3.",
                "open_questions": "Physical tests still required for NPSH.",
            }, source_positions=["p3:b2"],
        )
        self.assertEqual(note["analysis_count"], 1)
        markdown = self.memory.read(self.doc_id)["markdown"]
        self.assertIn("p3:b2", markdown)
        self.assertIn(state["pdf_sha256"], markdown)
        self.assertIn(state["parse_sha256"], markdown)
        self.assertIn("需人工核查原始 PDF", markdown)

    def test_malformed_cross_page_or_unanchored_reference_rejected(self):
        self.parsed()
        bad = ["p9:b1", "p2:b2", "p3:b1", "p2:b4",
               "p1:b0", "p0:b1", "../p2:b1", "p2:b3", "p2:b2",
               "p10000:b1", "", "page2-block1"]
        for anchor in bad:
            with self.subTest(anchor=anchor), self.assertRaises(PatentWorkflowError):
                self.pipeline.validate_positions(self.doc_id, [anchor])
        # The unnumbered extracted third block cannot substantiate a full_text quote.
        with self.assertRaises(PatentWorkflowError):
            self.pipeline.validate_positions(self.doc_id, ["p3:b3"])
        for invalid in ("", "no", "x" * 1001):
            with self.assertRaises(PatentWorkflowError):
                self.pipeline.quote(self.doc_id, "p2:b1", invalid)
        self.assertEqual(self.memory.stats()["by_kind"]["paper"]["analyzed"], 0)

    def test_stale_pdf_source_blocks_old_quotes_and_notes(self):
        self.parsed()
        with self.memory.connect(write=True) as db:
            db.execute(
                "UPDATE fulltext_jobs SET pdf_sha256=? WHERE doc_id=?",
                ("e" * 64, self.doc_id),
            )
        with self.assertRaises(PatentWorkflowError):
            self.pipeline.validate_positions(self.doc_id, ["p2:b1"])
        with self.assertRaises(PatentWorkflowError):
            self.memory.write_analysis(
                self.doc_id, analyst="AI", basis="full_text",
                analysis={"plain_summary": "stale"},
                source_positions=["p2:b1"],
            )

    def test_mcp_uses_current_project_only(self):
        workspace = self.home / "workspace"
        service = PatentMCPService(workspace, project_id="ALPHA")
        service.create_case("CASE-ONE", "Fire pump cavitation research")
        case_memory = service._memory("CASE-ONE")
        case_memory.ingest_many([paper()])
        pipeline = FulltextPipeline(case_memory)
        pipeline.queue(
            self.doc_id, rights_actor="IP-review",
            rights_reference="LIC-2026-CI", authorized=True,
        )
        pipeline.process(
            self.doc_id, allowed_hosts={"repository.example.edu"},
            authorized=True, downloader=fake_download,
            parser=fake_parser, converter=object(),
        )
        found = service.literature_fulltext_quote(
            "CASE-ONE", self.doc_id, "p2:b1", "Inlet cavitation",
        )
        self.assertTrue(found["exact_match"])
        service.create_case("CASE-TWO", "Other topic")
        with self.assertRaises(PatentWorkflowError):
            service.literature_fulltext_quote(
                "CASE-TWO", self.doc_id, "p2:b1", "Inlet cavitation",
            )
        another = PatentMCPService(workspace, project_id="BETA")
        another.create_case("CASE-ONE", "Other project")
        with self.assertRaises(PatentWorkflowError):
            another.literature_fulltext_quote(
                "CASE-ONE", self.doc_id, "p2:b1", "Inlet cavitation",
            )


if __name__ == "__main__":
    unittest.main()
