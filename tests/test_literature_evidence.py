"""真实 PDF 哈希、Docling 页码证据、短引与跨案卷权限的离线集成测试。

CI 可用伪造转换器，真实 Docling 模型需要企业授权的离线模型资产。
所有测试样本均为模拟数据，不能视为正式专利或真实科研结果。
"""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from mechanical_patent.core import Evidence, PatentWorkflowError, evidence_id
from mechanical_patent.literature_evidence import FullTextEvidence
from mechanical_patent.literature_memory import LiteratureMemoryStore
from mechanical_patent.pdf_extraction import parse_local_pdf


def evidence(number: int = 1) -> Evidence:
    return Evidence(
        publication=f"CN2026110000{number:02d}A",
        title=f"高海拔消防泵入口控制机构 {number}",
        source="模拟公开专利数据源",
        url=f"https://example.org/patent/CN2026110000{number:02d}A",
        retrieved_at="2026-11-19T01:00:00+00:00",
        kind="patent", verified=False,
        claims="1. 一种排气支路结构，含有止回阀。",
    )


class FakeDoc:
    pages = {1: object(), 2: object()}
    def iterate_items(self):
        return iter([
            (SimpleNamespace(
                text="高海拔环境下消防泵入口压力降低，易产生汽蚀",
                label="paragraph", prov=[
                    SimpleNamespace(page_no=1, bbox=SimpleNamespace(
                        l=0.1, t=0.2, r=12.0, b=14.0,
                    )),
                ],
            ), 0),
            (SimpleNamespace(
                text="该结构通过独立排气支路及止回阀排出气体",
                label="paragraph",
                prov=[SimpleNamespace(page_no=2, bbox=None)],
            ), 0),
            (SimpleNamespace(
                text="没有可靠可定位页码的附录残片",
                label="text", prov=[],
            ), 0),
        ])


class FakeConverter:
    def convert(self, path, **kwargs):
        return SimpleNamespace(document=FakeDoc())


class FulltextEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.case_root = Path(self.temp.name) / "projects" / "P1" / "cases" / "C1"
        self.memory = LiteratureMemoryStore(self.case_root)
        self.original = evidence()
        self.doc_id = evidence_id(self.original)
        self.memory.ingest_many([self.original])
        self.fulltext = FullTextEvidence(self.memory)
        inbox = self.memory.root / "inbox"
        inbox.mkdir(mode=0o700)
        self.pdf = inbox / "public.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\nSynthetic offline legal fixture\n%%EOF")
        self.parsed = inbox / "public.json"
        parse_local_pdf(
            self.pdf, self.parsed, authorized=True, converter=FakeConverter(),
            source_url="https://example.org/patent/public.pdf",
        )

    def test_bind_page_blocks_and_search_with_original_pdf_hash(self):
        result = self.fulltext.attach(
            self.doc_id, self.parsed, self.pdf, authorized=True,
        )
        self.assertEqual(result["status"], "attached")
        self.assertEqual(result["blocks"], 3)
        self.assertEqual(result["page_anchors"], 2)
        self.assertEqual(result["pdf_sha256"], sha256(self.pdf.read_bytes()).hexdigest())
        self.assertTrue(self.fulltext.status(self.doc_id)["attached"])
        self.assertEqual(
            self.fulltext.status(self.doc_id)["review_status"],
            "awaiting_original_pdf_review",
        )
        found = self.fulltext.search("独立排气支路")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["anchor"], "p2:b2")
        self.assertEqual(found[0]["page"], 2)
        self.assertIn("止回阀", found[0]["excerpt"])
        self.assertEqual(found[0]["pdf_sha256"], result["pdf_sha256"])
        self.assertEqual(len(self.fulltext.search("止回", doc_id=self.doc_id)), 1)

        exact = self.fulltext.quote(self.doc_id, "p2:b2", "独立排气支路及止回阀")
        self.assertTrue(exact["exact_match"])
        self.assertEqual(exact["verification_level"], "parsed_text_match_only")
        self.assertFalse(self.fulltext.quote(self.doc_id, "p2:b2", "无人驾驶控制器")["exact_match"])
        self.assertIsNone(self.fulltext.search("附录残片")[0]["anchor"])

    def test_full_text_notes_require_existing_precise_anchor(self):
        with self.assertRaises(PatentWorkflowError):
            self.memory.write_analysis(
                self.doc_id, analyst="AI", basis="full_text",
                analysis={"plain_summary": "错误推断"}, source_positions=["p1:b1"],
            )
        self.fulltext.attach(self.doc_id, self.parsed, self.pdf, authorized=True)
        for invalid in ("p1", "p100:b1", "p1:b2", "p2:b999", "p0:b1", "p1:b3", "p2:b1"):
            with self.subTest(anchor=invalid), self.assertRaises(PatentWorkflowError):
                self.memory.write_analysis(
                    self.doc_id, analyst="AI", basis="full_text",
                    analysis={"plain_summary": "不正确"}, source_positions=[invalid],
                )
        valid = self.memory.write_analysis(
            self.doc_id, analyst="AI", basis="full_text",
            analysis={
                "plain_summary": "原文第2页描述排气支路及止回阀，需复核该结构可实现的工况。",
                "open_questions": "需要实测 NPSH 条件和高海拔泵入口压力。",
            }, source_positions=["p2:b2"],
        )
        self.assertEqual(valid["analysis_count"], 1)
        self.assertIn("p2:b2", self.memory.read(self.doc_id)["markdown"])

    def test_duplicate_update_and_immutable_revision(self):
        first = self.fulltext.attach(
            self.doc_id, self.parsed, self.pdf, authorized=True,
        )
        again = self.fulltext.attach(
            self.doc_id, self.parsed, self.pdf, authorized=True,
        )
        self.assertEqual(again["status"], "unchanged")
        self.assertEqual(first["parsed_sha256"], again["parsed_sha256"])
        data = json.loads(self.parsed.read_text(encoding="utf-8"))
        data["blocks"][1]["text"] = "改版：该结构含有自动压力阀"
        self.parsed.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        update = self.fulltext.attach(
            self.doc_id, self.parsed, self.pdf, authorized=True,
        )
        self.assertEqual(update["status"], "updated")
        self.assertFalse(update["stale_previous_notes"])
        self.assertFalse(self.fulltext.search("独立排气支路"))
        self.assertEqual(len(self.fulltext.search("自动压力阀")), 1)
        with self.memory.connect() as db:
            revisions = db.execute(
                "SELECT archive_json,archive_pdf FROM fulltext_revisions WHERE doc_id=?",
                (self.doc_id,),
            ).fetchall()
        self.assertEqual(len(revisions), 2)
        for entry in revisions:
            self.assertTrue((self.memory.root / entry["archive_json"]).is_file())
            self.assertTrue((self.memory.root / entry["archive_pdf"]).is_file())

    def test_mismatch_crosscase_and_permission_rejected(self):
        with self.assertRaises(PatentWorkflowError):
            self.fulltext.attach(self.doc_id, self.parsed, self.pdf, authorized=False)
        altered = self.memory.root / "inbox" / "other.pdf"
        altered.write_bytes(b"%PDF-1.5\nunrelated original content")
        with self.assertRaises(PatentWorkflowError):
            self.fulltext.attach(self.doc_id, self.parsed, altered, authorized=True)
        outside = Path(self.temp.name) / "not-in-case.pdf"
        outside.write_bytes(self.pdf.read_bytes())
        with self.assertRaises(PatentWorkflowError):
            self.fulltext.attach(self.doc_id, self.parsed, outside, authorized=True)
        second = LiteratureMemoryStore(Path(self.temp.name) / "projects" / "P2" / "cases" / "C1")
        second.ingest_many([evidence(2)])
        with self.assertRaises(PatentWorkflowError):
            FullTextEvidence(second).attach(
                self.doc_id, self.parsed, self.pdf, authorized=True,
            )
        self.assertEqual(FullTextEvidence(second).search("独立排气支路"), [])

    def test_bad_content_and_injected_anchors_fail_closed(self):
        bad = json.loads(self.parsed.read_text(encoding="utf-8"))
        bad["blocks"][0]["page"] = 0
        self.parsed.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(PatentWorkflowError):
            self.fulltext.attach(self.doc_id, self.parsed, self.pdf, authorized=True)
        bad["blocks"][0]["page"] = 1
        bad["blocks"][1]["block"] = 1
        self.parsed.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(PatentWorkflowError):
            self.fulltext.attach(self.doc_id, self.parsed, self.pdf, authorized=True)
        bad["blocks"][1]["block"] = 2
        bad["blocks"][1]["bbox"] = {"l": float("inf")}
        self.parsed.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(PatentWorkflowError):
            self.fulltext.attach(self.doc_id, self.parsed, self.pdf, authorized=True)

    def test_mcp_tool_restricts_all_file_paths_to_case_inbox(self):
        from mechanical_patent.mcp_server import PatentMCPService
        root = Path(self.temp.name) / "shared-workspace"
        service = PatentMCPService(root, project_id="PROJECT-A")
        service.create_case("CASE-1", "消防泵气液分离研究")
        doc = evidence(3)
        service._memory("CASE-1").ingest_many([doc])
        service_inbox = service._memory("CASE-1").root / "inbox"
        service_inbox.mkdir()
        (service_inbox / "paper.pdf").write_bytes(self.pdf.read_bytes())
        (service_inbox / "paper.json").write_bytes(self.parsed.read_bytes())
        # 当前测试的 parsed 恢复为合法格式。
        parse_local_pdf(
            service_inbox / "paper.pdf", service_inbox / "paper.json",
            authorized=True, converter=FakeConverter(),
            source_url="https://example.org/patent/public.pdf",
        )
        with self.assertRaises(PatentWorkflowError):
            service.literature_fulltext_ingest(
                "CASE-1", evidence_id(doc), "../paper.pdf", "paper.json", True,
            )
        inserted = service.literature_fulltext_ingest(
            "CASE-1", evidence_id(doc), "paper.pdf", "paper.json", True,
        )
        self.assertEqual(inserted["status"], "attached")
        query = service.literature_search("CASE-1", "独立排气支路")
        self.assertEqual(len(query["matched_passages"]), 1)
        self.assertEqual(len(service.literature_passages(
            "CASE-1", "独立排气支路", evidence_id(doc)
        )["passages"]), 1)
        checked = service.literature_quote(
            "CASE-1", evidence_id(doc), "p2:b2", "独立排气支路",
        )
        self.assertTrue(checked["exact_match"])
        other = PatentMCPService(root, project_id="PROJECT-B")
        other.create_case("CASE-1", "另一个研究方向")
        self.assertEqual(other.literature_passages("CASE-1", "独立排气支路")["passages"], [])
        with self.assertRaises(PatentWorkflowError):
            other.literature_quote(
                "CASE-1", evidence_id(doc), "p2:b2", "独立排气支路",
            )


if __name__ == "__main__":
    unittest.main()
