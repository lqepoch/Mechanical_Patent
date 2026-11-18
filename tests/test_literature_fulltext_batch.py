"""PDF 全文批次队列：预算、失败隔离、项目级续检和状态接口。"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mechanical_patent.core import Evidence, PatentWorkflowError, evidence_id
from mechanical_patent.literature_memory import LiteratureMemoryStore
from mechanical_patent.literature_fulltext import LiteratureFullText
from mechanical_patent.literature_fulltext_batch import FullTextBatchRunner
from mechanical_patent.cli import main


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "case-batch"
        self.memory = LiteratureMemoryStore(self.project)
        self.docs = []
        for n in range(2):
            paper = Evidence(
                publication=f"10.1234/batch-{n}", title=f"Hydraulic study {n}",
                url=f"https://doi.org/10.1234/batch-{n}", source="crossref",
                retrieved_at="2026-11-19T00:00:00Z", kind="paper",
                abstract="Cavitation flow physics", verified=True,
                paper_metadata={"doi": f"10.1234/batch-{n}"},
            )
            self.docs.append(evidence_id(paper))
            self.memory.ingest_many([paper])
        self.runner = FullTextBatchRunner(LiteratureFullText(self.memory))
        self.files = []
        for n in range(2):
            path = self.root / f"source-{n}.pdf"
            path.write_bytes(b"%PDF-1.4\n" + bytes([65+n]) * 1300 + b"\n%%EOF")
            self.files.append(path)

    def item(self, n, *, parse=False, source="local"):
        item = {
            "doc_id": self.docs[n], "source": source,
            "rights_basis": "cc-by", "rights_reference":
                "https://creativecommons.org/licenses/by/4.0/",
            "parse": parse,
        }
        if source == "local":
            item["input"] = str(self.files[n])
        else:
            item["allowed_hosts"] = ["repository.example.org"]
        return item

    def test_partial_then_resume_with_project_sqlite(self):
        manifest = {"items": [self.item(0), self.item(1)]}
        first = self.runner.run(manifest, authorized=True, max_documents=1)
        self.assertEqual(first["status"], "partial")
        self.assertEqual(first["completed_total"], 1)
        self.assertEqual(first["pending"], 1)
        second = self.runner.run(manifest, authorized=True, max_documents=1)
        self.assertEqual(second["status"], "complete")
        self.assertEqual(second["completed_total"], 2)
        third = self.runner.run(manifest, authorized=True)
        self.assertEqual(third["processed_this_run"], 0)
        self.assertEqual(third["skipped_this_run"], 2)
        state = self.runner.status(first["batch_id"])
        self.assertTrue(state["complete"])
        self.assertEqual(state["counts"], {"done": 2})
        self.assertEqual(len(state["items"]), 2)

    def test_invalid_license_or_missing_authorization(self):
        manifest = {"items": [self.item(0)]}
        with self.assertRaises(PatentWorkflowError):
            self.runner.run(manifest, authorized=False)
        invalid = self.item(0)
        invalid["rights_basis"] = "cc-by-nc"
        with self.assertRaises(PatentWorkflowError):
            self.runner.run({"items": [invalid]}, authorized=True)
        with self.assertRaises(PatentWorkflowError):
            self.runner.run({"items": [invalid, invalid]}, authorized=True)

    def test_remote_manifest_requires_outbound_before_any_access(self):
        manifest = {"items": [self.item(0, source="remote")]}
        with self.assertRaises(PatentWorkflowError):
            self.runner.run(manifest, authorized=True, outbound_approved=False)
        self.assertEqual(
            self.runner.pipeline.status(self.docs[0])["state"], "not_available",
        )

    def test_failed_item_keeps_queue_and_successful_siblings(self):
        missing = self.item(0)
        missing["input"] = str(self.root / "missing.pdf")
        manifest = {"items": [missing, self.item(1)]}
        result = self.runner.run(manifest, authorized=True, max_attempts=2)
        self.assertEqual(result["failed_this_run"], 1)
        self.assertEqual(result["completed_total"], 1)
        self.assertEqual(result["failed_pending_retry"], 1)
        detail = self.runner.status(result["batch_id"])
        self.assertEqual(detail["counts"], {"done": 1, "failed": 1})
        retry = self.runner.run(manifest, authorized=True, max_attempts=2)
        self.assertEqual(retry["failed_this_run"], 1)
        missing_path = self.root / "missing.pdf"
        missing_path.write_bytes(b"%PDF-1.4\n" + b"C" * 1200)
        blocked = self.runner.run(manifest, authorized=True, max_attempts=2)
        self.assertEqual(blocked["processed_this_run"], 0)
        repaired = self.runner.run(manifest, authorized=True, max_attempts=2, refresh=True)
        self.assertEqual(repaired["completed_total"], 2)

    def test_project_isolation_of_batch_identifiers(self):
        manifest = {"items": [self.item(0)]}
        batch = self.runner.run(manifest, authorized=True)
        independent = FullTextBatchRunner(LiteratureFullText(
            LiteratureMemoryStore(self.root / "other-project")
        ))
        with self.assertRaises(PatentWorkflowError):
            independent.status(batch["batch_id"])
        with self.assertRaises(PatentWorkflowError):
            self.runner.status("FTB-../../outside")

    def test_cli_local_batch_and_status(self):
        manifest = {"items": [self.item(0)]}
        file = self.root / "batch.json"
        file.write_text(json.dumps(manifest), encoding="utf-8")
        code = main([
            "literature", "--project-dir", str(self.project),
            "fulltext-batch", "--manifest", str(file), "--authorized",
            "--max-documents", "1",
        ])
        self.assertEqual(code, 0)
        batch = self.runner.run(manifest, authorized=True)
        code = main([
            "literature", "--project-dir", str(self.project),
            "fulltext-batch-status", "--batch-id", batch["batch_id"],
        ])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
