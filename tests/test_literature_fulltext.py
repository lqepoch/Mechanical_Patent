"""离线验收 PDF 权利门禁、真实流转、可恢复解析与知识检索；无外网或模型权重。"""
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


class FulltextTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.case_root = Path(self.folder.name) / "cases" / "paper-case"
        self.memory = LiteratureMemoryStore(self.case_root)
        self.document = Evidence(
            publication="10.1234/oa-pump",
            title="Experimental Cavitation in High Altitude Fire Pumps",
            url="https://doi.org/10.1234/oa-pump",
            source="openalex", retrieved_at="2026-11-19T00:00:00+00:00",
            kind="paper", abstract="Bubble dynamics and cavitation threshold",
            verified=True, pdf_url="https://repository.example.edu/paper.pdf",
            paper_metadata={
                "doi": "10.1234/oa-pump", "license": "cc-by-4.0",
                "is_open_access": True, "sources": ["openalex"],
            },
        )
        self.memory.ingest_many([self.document])
        self.doc_id = evidence_id(self.document)
        self.pipeline = FulltextPipeline(self.memory)

    def _queue(self):
        return self.pipeline.queue(
            self.doc_id, rights_actor="authorized-law-reviewer",
            rights_reference="IPR-LIC-2026-0001", authorized=True,
        )

    def _downloader(self, calls):
        def download(url, dest, *, allowed_hosts, max_bytes):
            calls.append((url, allowed_hosts))
            dest.mkdir(parents=True, exist_ok=True)
            raw = b"%PDF-1.4\n%offline-test\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"
            digest = sha256(raw).hexdigest()
            path = dest / (digest + ".pdf")
            path.write_bytes(raw)
            return {
                "online_url": url, "local_pdf_path": str(path),
                "sha256": digest, "bytes": len(raw),
            }
        return download

    def _parser(self, calls):
        def parse(path, output, *, authorized, source_url, artifacts, converter):
            calls.append((path, source_url))
            payload = {
                "source_pdf_sha256": sha256(path.read_bytes()).hexdigest(),
                "parser": "docling", "parser_version": "offline-test",
                "review_status": "awaiting_original_pdf_review",
                "blocks": [
                    {"page": 3, "block": 1, "label": "paragraph",
                     "text": "Cavitation inception is affected by NPSH and atmospheric pressure."},
                    {"page": 4, "block": 2, "label": "formula",
                     "text": "High-altitude water inlet physics and vapor pressure limits."},
                ],
            }
            output.write_text(json.dumps(payload), encoding="utf-8")
            return {"sha256": payload["source_pdf_sha256"], "blocks": 2}
        return parse

    def test_queue_needs_license_and_explicit_review(self):
        with self.assertRaises(PatentWorkflowError):
            self.pipeline.queue(self.doc_id, rights_actor="AA",
                                rights_reference="IPR-2026", authorized=False)
        self.assertEqual(self.pipeline.status(self.doc_id)["status"], "not_planned")
        planned = self._queue()
        self.assertEqual(planned["status"], "queued")
        self.assertEqual(planned["source_license"], "cc-by-4.0")

    def test_unknown_or_noncommercial_license_blocked(self):
        for bad in ("", "cc-by-nc-4.0", "cc-by-nd", "all-rights-reserved"):
            entry = Evidence.from_dict({
                **self.document.to_dict(), "paper_metadata": {
                    "is_open_access": True, "license": bad
                }
            })
            self.memory.ingest_many([entry])
            with self.assertRaises(PatentWorkflowError, msg=bad):
                self.pipeline.queue(
                    self.doc_id, rights_actor="reviewer-1",
                    rights_reference="IPR-2026-001", authorized=True,
                )

    def test_oa_flag_missing_is_blocked(self):
        paper = Evidence.from_dict({
            **self.document.to_dict(), "paper_metadata": {
                "is_open_access": None, "license": "cc-by-4.0"
            }
        })
        self.memory.ingest_many([paper])
        with self.assertRaises(PatentWorkflowError):
            self._queue()

    def test_license_revocation_invalidates_existing_queue(self):
        self._queue()
        revoked = Evidence.from_dict({
            **self.document.to_dict(),
            "paper_metadata": {"is_open_access": False, "license": "all-rights-reserved"},
        })
        self.memory.ingest_many([revoked])
        download_calls = []
        with self.assertRaises(PatentWorkflowError):
            self.pipeline.process(
                self.doc_id, allowed_hosts={"repository.example.edu"},
                authorized=True, downloader=self._downloader(download_calls),
                parse=False,
            )
        self.assertEqual(download_calls, [])
        self.assertEqual(self.pipeline.status(self.doc_id)["status"], "queued")

    def test_process_blocks_unapproved_host_and_records_failure(self):
        self._queue()
        with self.assertRaises(PatentWorkflowError):
            self.pipeline.process(
                self.doc_id, allowed_hosts={"evil.example.com"}, authorized=True,
                downloader=self._downloader([]), parse=False,
            )
        status = self.pipeline.status(self.doc_id)
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["attempts"], 1)
        self.assertIn("白名单", status["error"])

    def test_full_pipeline_records_page_index_and_machine_note(self):
        self._queue()
        download_calls, parser_calls = [], []
        result = self.pipeline.process(
            self.doc_id, allowed_hosts={"repository.example.edu"},
            authorized=True, downloader=self._downloader(download_calls),
            parser=self._parser(parser_calls), converter=object(),
        )
        self.assertEqual(result["status"], "parsed")
        self.assertEqual(result["extracted_blocks"], 2)
        self.assertFalse(result["full_text_verified"])
        self.assertEqual(len(download_calls), 1)
        self.assertEqual(len(parser_calls), 1)
        hits = self.pipeline.search("Cavitation")
        self.assertEqual(hits[0]["page_no"], 3)
        self.assertEqual(hits[0]["source_pdf_sha256"], result["pdf_sha256"])
        self.assertEqual(hits[0]["review_status"], "awaiting_original_pdf_review")
        note = self.memory.read(self.doc_id)["markdown"]
        self.assertIn("## 机器 PDF 解析索引（未作人工核验）", note)
        self.assertIn(result["parse_sha256"], note)
        self.assertEqual(self.pipeline.pending(), [])
        # 重复执行不能重新下载或反复生成研究记忆。
        again = self.pipeline.process(
            self.doc_id, allowed_hosts={"repository.example.edu"},
            authorized=True, downloader=self._downloader(download_calls),
            parser=self._parser(parser_calls), converter=object(),
        )
        self.assertEqual(again["parse_sha256"], result["parse_sha256"])
        self.assertEqual(len(download_calls), 1)
        self.assertEqual(note, self.memory.read(self.doc_id)["markdown"])

    def test_parse_failure_retains_verified_pdf_for_resume(self):
        self._queue()
        download_calls, parser_calls = [], []
        def failing(*_args, **_kwargs):
            raise PatentWorkflowError("offline model resources invalid")
        with self.assertRaises(PatentWorkflowError):
            self.pipeline.process(
                self.doc_id, allowed_hosts={"repository.example.edu"},
                authorized=True, downloader=self._downloader(download_calls),
                parser=failing, converter=object(),
            )
        self.assertEqual(self.pipeline.status(self.doc_id)["status"], "downloaded")
        finished = self.pipeline.process(
            self.doc_id, allowed_hosts={"repository.example.edu"},
            authorized=True, downloader=self._downloader(download_calls),
            parser=self._parser(parser_calls), converter=object(),
        )
        self.assertEqual(finished["status"], "parsed")
        self.assertEqual(len(download_calls), 1)

    def test_download_only_state_is_resumeable(self):
        self._queue()
        downloaded = self.pipeline.process(
            self.doc_id, allowed_hosts={"repository.example.edu"},
            authorized=True, downloader=self._downloader([]), parse=False,
        )
        self.assertEqual(downloaded["status"], "downloaded")
        self.assertTrue(downloaded["pdf_sha256"])
        self.assertEqual(downloaded["parse_sha256"], "")

    def test_paper_metadata_survives_reingest_and_keeps_notes(self):
        self._queue()
        self.pipeline.process(self.doc_id, allowed_hosts={"repository.example.edu"},
                              authorized=True, downloader=self._downloader([]),
                              parser=self._parser([]), converter=object())
        before = self.memory.read(self.doc_id)["markdown"]
        changed = Evidence.from_dict({
            **self.document.to_dict(),
            "abstract": "Longer metadata abstract updated after new search",
            "retrieved_at": "2026-11-19T04:00:00+00:00",
        })
        self.memory.ingest_many([changed])
        note = self.memory.read(self.doc_id)["markdown"]
        self.assertIn("Longer metadata abstract", note)
        self.assertIn("机器 PDF 解析索引", note)
        self.assertIn("PDF-PARSE:", note)
        self.assertNotEqual(before, note)

    def test_resume_never_accepts_wrong_hash(self):
        self._queue()
        self.pipeline.process(self.doc_id, allowed_hosts={"repository.example.edu"},
                              authorized=True, downloader=self._downloader([]), parse=False)
        with self.memory.connect(write=True) as db:
            db.execute(
                "UPDATE fulltext_jobs SET pdf_sha256=? WHERE doc_id=?",
                ("0" * 64, self.doc_id),
            )
        with self.assertRaises(PatentWorkflowError):
            self.pipeline.process(self.doc_id, allowed_hosts={"repository.example.edu"},
                                  authorized=True, parse=False)

    def test_mcp_read_only_provenance_tools_are_project_scoped(self):
        service = PatentMCPService(Path(self.folder.name) / "mcp-storage", project_id="project-A")
        service.create_case("case-A", "Pump Research")
        self.assertEqual(service.literature_fulltext_status("case-A", self.doc_id)["status"],
                         "not_planned")
        with self.assertRaises(PatentWorkflowError):
            service.literature_fulltext_status("unknown", self.doc_id)
        self.assertEqual(service.literature_fulltext_pending("case-A")["jobs"], [])
        self.assertEqual(service.literature_fulltext_search("case-A", "NPSH")["matches"], [])

    def test_legacy_project_migration_is_idempotent(self):
        with self.memory.connect() as db:
            cols = {x["name"] for x in db.execute("PRAGMA table_info(documents)")}
            self.assertTrue({"pdf_url", "metadata_json"}.issubset(cols))
        restarted = LiteratureMemoryStore(self.case_root)
        with restarted.connect() as db:
            entry = db.execute(
                "SELECT pdf_url,metadata_json FROM documents WHERE doc_id=?",
                (self.doc_id,),
            ).fetchone()
            self.assertEqual(entry["pdf_url"], "https://repository.example.edu/paper.pdf")
            self.assertEqual(json.loads(entry["metadata_json"])["license"], "cc-by-4.0")

    def test_short_chinese_phrase_search_falls_back_without_fts(self):
        self._queue()
        self.pipeline.process(self.doc_id, allowed_hosts={"repository.example.edu"},
                              authorized=True, downloader=self._downloader([]),
                              parser=self._parser([]), converter=object())
        hits = self.pipeline.search("高原", limit=5)
        self.assertEqual(hits, [])
        self.assertEqual(len(self.pipeline.search("NPSH", limit=5)), 1)


if __name__ == "__main__":
    unittest.main()
