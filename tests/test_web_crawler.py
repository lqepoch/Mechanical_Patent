"""Offline validation of Crawl4AI's security boundary and evidence integration."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from mechanical_patent.core import PatentWorkflowError
from mechanical_patent.web_crawler import WebDocument, validate_web_url, Crawl4AIGateway
from mechanical_patent.workflow import PatentResearch
from test_workflow import FakeProvider, FakeModel


def resolve_public(host, port, **kwargs):
    return [(None, None, None, None, ("1.1.1.1", 443))]


def resolve_private(host, port, **kwargs):
    return [(None, None, None, None, ("127.0.0.1", 443))]


class CrawlSecurityTests(unittest.TestCase):
    def test_only_approved_public_https(self):
        url = validate_web_url("https://www.example.com/article?q=1",
                               {"www.example.com"}, resolve=resolve_public)
        self.assertEqual(url, "https://www.example.com/article?q=1")
        for candidate in ("http://www.example.com/",
                          "https://www.example.com:8080/",
                          "https://www.example.com@127.0.0.1/",
                          "https://127.0.0.1/",
                          "file:///etc/passwd"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(PatentWorkflowError):
                    validate_web_url(candidate, {"www.example.com"}, resolve=resolve_public)

    def test_no_private_dns_or_wipo_patentscope(self):
        with self.assertRaises(PatentWorkflowError):
            validate_web_url("https://www.example.com/", {"www.example.com"}, resolve=resolve_private)
        with self.assertRaises(PatentWorkflowError):
            validate_web_url("https://patentscope.wipo.int/", {"patentscope.wipo.int"}, resolve=resolve_public)

    def test_web_not_misclassified_as_patent_prior_art(self):
        page = "# Real source extract; not a patent"
        doc = WebDocument(
            url="https://www.example.com/a", title="Public pump discussion",
            markdown=page, retrieved_at="2026-11-18T06:00:00+00:00",
            content_sha256=hashlib.sha256(page.encode()).hexdigest(),
        )
        record = doc.to_evidence()
        self.assertEqual(record.kind, "web")
        self.assertTrue(record.verified)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "case"
            result = PatentResearch(FakeProvider(), FakeModel(), output,
                                    max_ideas=1, supplemental_sources=[record],
                                    web_documents=[doc]).run("Improve inlet")
            self.assertEqual(result["status"], "needs_human_review")
            records = json.loads((output / "02_prior_art.json").read_text())["records"]
            self.assertTrue(any(x["kind"] == "web" for x in records))
            self.assertTrue((output / "02a_crawl4ai_web_captures.json").exists())

    def test_page_budget(self):
        crawler = Crawl4AIGateway({"www.example.com"}, max_pages=1)
        with self.assertRaises(PatentWorkflowError):
            import asyncio
            asyncio.run(crawler.collect(["https://www.example.com/a", "https://www.example.com/b"]))


if __name__ == "__main__":
    unittest.main()
