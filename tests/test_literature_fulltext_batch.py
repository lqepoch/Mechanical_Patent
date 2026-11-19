"""基于 canonical FulltextPipeline 的可恢复多文献批次（无外网和模型权重）。"""
from __future__ import annotations

from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mechanical_patent.core import Evidence, PatentWorkflowError, evidence_id
from mechanical_patent.literature_memory import LiteratureMemoryStore
from mechanical_patent.literature_fulltext import FulltextPipeline
from mechanical_patent.literature_fulltext_batch import FullTextBatchRunner


class FullTextBatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.memory = LiteratureMemoryStore(self.root / "cases" / "FULLTEXT-1")
        self.docs = []
        for i in range(2):
            paper = Evidence(
                publication=f"10.2026/engine-{i}", title=f"Engine paper {i}",
                url=f"https://doi.org/10.2026/engine-{i}", source="openalex",
                retrieved_at="2026-11-19T00:00:00+00:00",
                kind="paper", verified=True, abstract="Mechanical pressure studies",
                pdf_url=f"https://repository.example.edu/paper-{i}.pdf",
                paper_metadata={
                    "doi": f"10.2026/engine-{i}", "is_open_access": True,
                    "license": "cc-by-4.0", "sources": ["openalex"],
                },
            )
            self.docs.append(evidence_id(paper))
            self.memory.ingest_many([paper])
        self.pipeline = FulltextPipeline(self.memory)
        self.runner = FullTextBatchRunner(self.pipeline)
        self.download_calls = []
        self.parse_calls = []

    def item(self, index, *, parse=True):
        return {
            "doc_id": self.docs[index],
            "rights_actor": "approved-IP-reviewer",
            "rights_reference": "IPR-PAPER-2026-001",
            "allowed_hosts": ["repository.example.edu"],
            "parse": parse,
        }

    def downloader(self, url, dest, *, allowed_hosts, max_bytes):
        self.download_calls.append(url)
        self.assertEqual(allowed_hosts, {"repository.example.edu"})
        self.assertGreaterEqual(max_bytes, 1000)
        raw = b"%PDF-1.7\n" + b"A" * 1800 + b"\n%%EOF"
        dest.mkdir(parents=True, exist_ok=True)
        digest = sha256(raw).hexdigest()
        path = dest / (digest + ".pdf")
        path.write_bytes(raw)
        return {"online_url": url, "local_pdf_path": str(path),
                "sha256": digest, "bytes": len(raw)}

    def parser(self, path, output, *, authorized, source_url, artifacts, converter):
        self.parse_calls.append(str(path))
        self.assertTrue(authorized)
        payload = {
            "source_pdf_sha256": sha256(path.read_bytes()).hexdigest(),
            "parser": "docling", "parser_version": "test",
            "review_status": "awaiting_original_pdf_review",
            "blocks": [
                {"page": 1, "block": 1, "label": "paragraph",
                 "text": "Altitude cavitation experiment: NPSH is critical."},
            ],
        }
        output.write_text(json.dumps(payload), encoding="utf-8")
        return {"sha256": payload["source_pdf_sha256"], "blocks": 1}

    def run_batch(self, manifest, **kwargs):
        return self.runner.run(
            manifest, authorized=True, outbound_approved=True,
            downloader=kwargs.pop("downloader", self.downloader),
            parser=self.parser, converter=object(), **kwargs,
        )

    def test_checkpoint_resume_keeps_canonical_docling_results(self):
        manifest = {"items": [self.item(0), self.item(1)]}
        first = self.run_batch(manifest, max_documents=1)
        self.assertEqual(first["status"], "partial")
        self.assertEqual(first["completed_total"], 1)
        self.assertEqual(len(self.download_calls), 1)
        second = self.run_batch(manifest, max_documents=1)
        self.assertEqual(second["status"], "complete")
        self.assertEqual(second["completed_total"], 2)
        self.assertEqual(len(self.download_calls), 2)
        cached = self.run_batch(manifest)
        self.assertEqual(cached["processed_this_run"], 0)
        self.assertEqual(cached["skipped_this_run"], 2)
        self.assertEqual(len(self.parse_calls), 2)
        self.assertEqual(len(self.pipeline.search("NPSH")), 2)
        status = self.runner.status(first["batch_id"])
        self.assertTrue(status["complete"])
        self.assertEqual(status["counts"], {"done": 2})

    def test_reject_outbound_and_invalid_manifest(self):
        manifest = {"items": [self.item(0)]}
        with self.assertRaises(PatentWorkflowError):
            self.runner.run(manifest, authorized=False, outbound_approved=True)
        with self.assertRaises(PatentWorkflowError):
            self.runner.run(manifest, authorized=True, outbound_approved=False)
        invalid = self.item(0)
        invalid["doc_id"] = "../../outside"
        with self.assertRaises(PatentWorkflowError):
            self.run_batch({"items": [invalid]})
        with self.assertRaises(PatentWorkflowError):
            self.run_batch({"items": [self.item(0), self.item(0)]})
        self.assertEqual(self.download_calls, [])

    def test_failure_isolation_and_manual_refresh_after_retry_exhaustion(self):
        manifest = {"items": [self.item(0), self.item(1)]}
        def transient(url, dest, *, allowed_hosts, max_bytes):
            if url.endswith("paper-0.pdf"):
                raise PatentWorkflowError("Upstream temporarily unavailable")
            return self.downloader(url, dest, allowed_hosts=allowed_hosts, max_bytes=max_bytes)
        first = self.run_batch(manifest, downloader=transient, max_attempts=2)
        self.assertEqual(first["status"], "partial")
        self.assertEqual(first["failed_pending_retry"], 1)
        self.assertEqual(first["completed_total"], 1)
        again = self.run_batch(manifest, downloader=transient, max_attempts=2)
        self.assertEqual(again["failed_this_run"], 1)
        blocked = self.run_batch(manifest, max_attempts=2)
        self.assertEqual(blocked["processed_this_run"], 0)
        self.assertEqual(blocked["failed_total"], 1)
        self.assertEqual(blocked["failed_pending_retry"], 0)
        self.assertEqual(blocked["failed_retry_exhausted"], 1)
        recovered = self.run_batch(manifest, max_attempts=2, refresh=True)
        self.assertEqual(recovered["completed_total"], 2)
        self.assertEqual(recovered["skipped_this_run"], 1)
        self.assertTrue(self.runner.status(first["batch_id"])["complete"])

    def test_download_only_and_parse_later(self):
        download_manifest = {"items": [self.item(0, parse=False)]}
        first = self.run_batch(download_manifest)
        self.assertEqual(first["status"], "complete")
        self.assertEqual(self.pipeline.status(self.docs[0])["status"], "downloaded")
        parsed_manifest = {"items": [self.item(0, parse=True)]}
        second = self.run_batch(parsed_manifest)
        self.assertEqual(second["status"], "complete")
        self.assertEqual(self.pipeline.status(self.docs[0])["status"], "parsed")
        self.assertEqual(len(self.download_calls), 1)
        self.assertEqual(len(self.parse_calls), 1)

    def test_thousand_record_pagination_and_failed_filter_via_cli_and_mcp(self):
        from mechanical_patent.cli import main
        from mechanical_patent.mcp_server import PatentMCPService
        service = PatentMCPService(self.root / "mcp")
        service.create_case("BATCH-1", "合成测试")
        memory = service._memory("BATCH-1")
        runner = FullTextBatchRunner(FulltextPipeline(memory))
        batch_id = "FTB-" + "A" * 20

        def doc_id(ordinal):
            return f"EV-{ordinal:012X}"

        with memory.connect(write=True) as db:
            db.execute("INSERT INTO fulltext_batches VALUES(?,?,?,?,?)",
                       (batch_id, "test", 1000, "test", "test"))
            db.executemany(
                "INSERT INTO fulltext_batch_items "
                "(batch_id,doc_id,ordinal,state,attempts,last_error,updated_at) VALUES(?,?,?,?,?,?,?)",
                [(batch_id, doc_id(i), i, "failed" if i in (200, 999) else "done",
                  1, "测试解析失败" if i in (200, 999) else "", "test")
                 for i in range(1000)],
            )

        first = runner.status(batch_id, limit=1000)
        self.assertEqual(first["next_cursor"], 199)
        self.assertTrue(first["truncated"])
        seen = [row["doc_id"] for row in first["items"]]
        page = first
        while page["next_cursor"] is not None:
            page = runner.status(batch_id, limit=200, cursor=page["next_cursor"])
            seen.extend(row["doc_id"] for row in page["items"])
        self.assertEqual(seen, [doc_id(i) for i in range(1000)])
        self.assertFalse(page["truncated"])

        out = StringIO()
        with redirect_stdout(out):
            rc = main(["literature", "--project-dir", str(service.root / "cases" / "BATCH-1"),
                       "fulltext-batch-status", "--batch-id", batch_id, "--state", "failed",
                       "--cursor", str(first["next_cursor"]), "--limit", "1"])
        self.assertEqual(rc, 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["matched_total"], 2)
        self.assertEqual(result["counts"], {"done": 998, "failed": 2})
        self.assertEqual(result["items"][0]["doc_id"], doc_id(200))
        self.assertEqual(result["items"][0]["last_error"], "测试解析失败")
        rest = service.literature_fulltext_batch_status(
            "BATCH-1", batch_id, limit=1, cursor=result["next_cursor"], state="failed",
        )
        self.assertEqual(rest["items"][0]["doc_id"], doc_id(999))
        self.assertIsNone(rest["next_cursor"])
        for args in ({"cursor": -1}, {"cursor": True}, {"cursor": 1000}, {"state": "unknown"}):
            with self.assertRaises(PatentWorkflowError):
                runner.status(batch_id, **args)

    def test_failed_parse_charges_download_budget_and_retry_reuses_pdf(self):
        manifest = {"items": [self.item(0), self.item(1)]}
        with patch.object(self, "parser", side_effect=PatentWorkflowError("解析失败")):
            first = self.run_batch(manifest, max_total_bytes=2500)
        self.assertEqual(first["failed_this_run"], 1)
        self.assertEqual(first["pending"], 1)
        self.assertEqual(first["bytes_processed_this_run"], 1815)
        self.assertEqual(len(self.download_calls), 1)
        second = self.run_batch(manifest, max_total_bytes=2500)
        self.assertEqual(second["status"], "complete")
        self.assertEqual(second["bytes_processed_this_run"], 1815)
        self.assertEqual(len(self.download_calls), 2)

    def test_status_error_is_isolated_and_parse_completion_is_required(self):
        status = self.pipeline.status

        def sometimes_unavailable(doc_id):
            if doc_id == self.docs[0]:
                raise PatentWorkflowError("检查点不可用")
            return status(doc_id)

        manifest = {"items": [self.item(0), self.item(1)]}
        with patch.object(self.pipeline, "status", side_effect=sometimes_unavailable):
            first = self.run_batch(manifest)
        self.assertEqual(first["processed_this_run"], 2)
        self.assertEqual(first["failed_this_run"], 1)
        self.assertEqual(first["completed_total"], 1)
        with patch.object(self.pipeline, "process", return_value={"status": "downloaded"}):
            second = self.run_batch(manifest)
        self.assertEqual(second["status"], "partial")
        self.assertEqual(second["failed_this_run"], 1)

    def test_stale_done_does_not_consume_new_revision_attempt_budget(self):
        manifest = {"items": [self.item(0)]}
        self.assertEqual(self.run_batch(manifest, max_attempts=1)["status"], "complete")
        with self.memory.connect(write=True) as db:
            db.execute("UPDATE fulltext_jobs SET status='downloaded',attempts=0 WHERE doc_id=?",
                       (self.docs[0],))
        with patch.object(self, "parser", side_effect=PatentWorkflowError("新版本解析失败")):
            result = self.run_batch(manifest, max_attempts=1)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["failed_retry_exhausted"], 1)
        self.assertFalse(self.runner.status(result["batch_id"])["complete"])

    def test_project_isolation_and_malformed_batch_id(self):
        manifest = {"items": [self.item(0)]}
        stored = self.run_batch(manifest)
        independent = FullTextBatchRunner(
            FulltextPipeline(LiteratureMemoryStore(self.root / "another-project"))
        )
        with self.assertRaises(PatentWorkflowError):
            independent.status(stored["batch_id"])
        with self.assertRaises(PatentWorkflowError):
            self.runner.status("../../outside")
        self.assertFalse(self.runner.status(stored["batch_id"], limit=1)["truncated"])


if __name__ == "__main__":
    unittest.main()
