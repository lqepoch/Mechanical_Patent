"""本地原文 PDF 解析边界测试：Docling 真实模型不是 CI 必需依赖。"""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from mechanical_patent.core import PatentWorkflowError
from mechanical_patent.pdf_extraction import parse_local_pdf


class FakeDoc:
    pages = {1: object(), 2: object()}

    def iterate_items(self):
        box = SimpleNamespace(l=1.0, t=10.0, r=100.0, b=20.0)
        return iter([
            (SimpleNamespace(text="一种消防泵技术实施例",
                             label="paragraph",
                             prov=[SimpleNamespace(page_no=1, bbox=box)]), 0),
            (SimpleNamespace(text="具体控制方法包括测量入口压力",
                             label="paragraph",
                             prov=[SimpleNamespace(page_no=2, bbox=None)]), 0),
        ])


class FakeConverter:
    def convert(self, path, **kwargs):
        assert str(path).endswith(".pdf")
        assert kwargs["max_num_pages"] == 200
        return SimpleNamespace(document=FakeDoc())


class PDFExtractionTests(unittest.TestCase):
    def test_offline_page_anchor_and_hash(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / "public.pdf"
            source.write_bytes(b"%PDF-1.4\nfake fixture for offline parser tests\n%%EOF\n")
            out = root / "parsed.json"
            result = parse_local_pdf(source, out, authorized=True, converter=FakeConverter(),
                                     source_url="https://example.org/CN-public.pdf")
            self.assertEqual(result["blocks"], 2)
            import json
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["blocks"][0]["page"], 1)
            self.assertEqual(data["blocks"][1]["page"], 2)
            self.assertEqual(data["blocks"][0]["bbox"]["l"], 1.0)
            self.assertEqual(data["review_status"], "awaiting_original_pdf_review")
            self.assertEqual(data["source_url"], "https://example.org/CN-public.pdf")

    def test_access_and_input_guards(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / "doc.pdf"
            source.write_bytes(b"%PDF-1.4\ncontent\n")
            for payload in (
                {"authorized": False, "converter": FakeConverter()},
                {"authorized": True, "converter": FakeConverter(),
                 "source_url": "http://example.org/public.pdf"},
            ):
                with self.subTest(payload=payload):
                    with self.assertRaises(PatentWorkflowError):
                        parse_local_pdf(source, root / "out.json", **payload)
            source.write_bytes(b"<html>blocked</html>")
            with self.assertRaises(PatentWorkflowError):
                parse_local_pdf(source, root / "out.json",
                                authorized=True, converter=FakeConverter())


if __name__ == "__main__":
    unittest.main()
