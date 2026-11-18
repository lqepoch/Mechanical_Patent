"""行业 MCP 工具结果的原文追溯和权限门禁测试：不访问外网。"""
import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.core import PatentWorkflowError
from mechanical_patent.mcp_bridge import import_mcp_json, normalize_mcp_patents


def sample():
    return {
        "tool_family": "patent-client-agents",
        "tool_name": "epo_ops_patent_search",
        "transport": "structured_api",
        "data_access_authorized": True,
        "records": [
            {
                "publication": "CN202612345678A",
                "title": "一种机械流体系统",
                "original_url": "https://example.org/publication/CN202612345678A",
                "claims": "1. 一种具备双通道流体回路的机械系统。",
                "publication_date": "2026-11-01",
                "jurisdiction": "CN",
            }
        ],
    }


class MCPBridgeTests(unittest.TestCase):
    def test_external_evidence_is_not_auto_verified(self):
        result = normalize_mcp_patents(sample())
        self.assertEqual(len(result["records"]), 1)
        self.assertFalse(result["records"][0]["verified"])
        self.assertEqual(result["records"][0]["kind"], "patent")
        self.assertTrue(result["records"][0]["source"].startswith("mcp:patent-client-agents/"))
        self.assertEqual(result["review_status"], "awaiting_independent_source_verification")
        self.assertEqual(len(result["origin"]["structured_payload_sha256"]), 64)

    def test_license_and_html_crawl_restrictions(self):
        for patch in (
            {"data_access_authorized": False},
            {"tool_family": "unlicensed-provider"},
            {"transport": "html_scrape"},
        ):
            with self.subTest(patch=patch):
                request = {**sample(), **patch}
                with self.assertRaises(PatentWorkflowError):
                    normalize_mcp_patents(request)
        bad = sample()
        bad["records"][0]["original_url"] = "http://private.local/data"
        with self.assertRaises(PatentWorkflowError):
            normalize_mcp_patents(bad)

    def test_mcp_snapshot_import_and_dedup(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            payload = sample()
            payload["records"].append({
                **payload["records"][0], "claims": "",
            })
            incoming = root / "mcp.json"
            output = root / "normalized.json"
            incoming.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = import_mcp_json(incoming, output)
            self.assertEqual(result["records"], 1)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(saved["records"][0]["claims"])
            self.assertFalse(saved["records"][0]["verified"])


if __name__ == "__main__":
    unittest.main()
