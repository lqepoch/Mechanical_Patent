"""Crawl4AI policy tests, with the native-agent research handoff."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.core import PatentWorkflowError
from mechanical_patent.web_crawler import WebDocument, validate_web_url, Crawl4AIGateway
from mechanical_patent.workflow import PatentResearch
from test_workflow import FakeProvider


def resolve_public(host, port, **kwargs):
    return [(None, None, None, None, ("1.1.1.1", 443))]


def resolve_private(host, port, **kwargs):
    return [(None, None, None, None, ("127.0.0.1", 443))]


class CrawlSecurityTests(unittest.TestCase):
    def test_only_allowlisted_public_https(self):
        url = validate_web_url("https://www.example.com/article?q=1",
                               {"www.example.com"}, resolve=resolve_public)
        self.assertEqual(url, "https://www.example.com/article?q=1")
        for candidate in ("http://www.example.com/", "https://www.example.com:8080/",
                          "https://www.example.com@127.0.0.1/", "https://127.0.0.1/",
                          "file:///etc/passwd"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(PatentWorkflowError):
                    validate_web_url(candidate, {"www.example.com"}, resolve=resolve_public)

    def test_no_private_dns_or_wipo_patentscope(self):
        with self.assertRaises(PatentWorkflowError):
            validate_web_url("https://www.example.com/", {"www.example.com"}, resolve=resolve_private)
        with self.assertRaises(PatentWorkflowError):
            validate_web_url("https://patentscope.wipo.int/", {"patentscope.wipo.int"}, resolve=resolve_public)

    def test_web_is_independent_nonpatent_evidence(self):
        body = "# Technically interesting public page"
        page = WebDocument(
            url="https://www.example.com/a", title="Public pump article",
            markdown=body, retrieved_at="2026-11-18T00:00:00+00:00",
            content_sha256=hashlib.sha256(body.encode()).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as root:
            case = Path(root) / "case"
            report = PatentResearch(
                FakeProvider("patent-mock", "patent"),
                [FakeProvider("paper-mock", "paper")], case,
                supplemental_sources=[page.to_evidence()], web_documents=[page],
            ).run("Improve pump", ["valve"], ["fluid pressure"])
            records = json.loads((case / "04_evidence.json").read_text())["records"]
            self.assertEqual({x["kind"] for x in records}, {"patent", "paper", "web"})
            self.assertTrue((case / "04a_crawl4ai.json").exists())
            self.assertFalse(report["filing_authorized"])

    def test_page_budget(self):
        import asyncio
        with self.assertRaises(PatentWorkflowError):
            asyncio.run(Crawl4AIGateway({"www.example.com"}, max_pages=1).collect([
                "https://www.example.com/a", "https://www.example.com/b"
            ]))


if __name__ == "__main__":
    unittest.main()
