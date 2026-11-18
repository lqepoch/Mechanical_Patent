"""原始专利 PDF 的来源链、授权下载和内容完整性测试：不触网。"""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.core import Evidence, PatentWorkflowError
from mechanical_patent.local_workspace import LocalPatentWorkspace
from mechanical_patent.pdf_archive import archive_patent, download_pdf


PDF_DATA = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
PDF_URL = "https://pdf.example.org/patents/CN001A.pdf"


class FakePDFResponse:
    def __init__(self, body: bytes, *, final_url: str = PDF_URL,
                 content_type: str = "application/pdf"):
        self.content = BytesIO(body)
        self.final_url = final_url
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.content.close()

    def geturl(self):
        return self.final_url

    def read(self, limit: int = 65536):
        return self.content.read(limit)


def fake_dns(host, port, **kwargs):
    return [(None, None, None, None, ("1.1.1.1", 443))]


def fake_open(req, timeout=30):
    return FakePDFResponse(PDF_DATA)


def document() -> Evidence:
    return Evidence(
        publication="CN202610000001A", title="某消防泵专利公开文本",
        url="https://example.org/patent/publication", source="官方来源",
        retrieved_at="2026-11-18T00:00:00+00:00",
        abstract="消防泵入口阀体结构", jurisdiction="CN", kind="patent",
        verified=True,
    )


class PDFArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_deduplicated_pdf_and_sha256(self):
        folder = self.root / "library"
        first = download_pdf(
            PDF_URL, folder, allowed_hosts={"pdf.example.org"},
            resolve=fake_dns, opener=fake_open
        )
        second = download_pdf(
            PDF_URL, folder, allowed_hosts={"pdf.example.org"},
            resolve=fake_dns, opener=fake_open
        )
        self.assertEqual(first["sha256"], sha256(PDF_DATA).hexdigest())
        self.assertEqual(first["local_pdf_path"], second["local_pdf_path"])
        self.assertEqual(Path(first["local_pdf_path"]).read_bytes(), PDF_DATA)
        self.assertEqual(list(folder.glob("*.pdf")), [Path(first["local_pdf_path"])])
        self.assertEqual(first["online_url"], PDF_URL)

    def test_deny_unapproved_hosts_non_pdf_redirect_and_large_file(self):
        with self.assertRaises(PatentWorkflowError):
            download_pdf(
                PDF_URL, self.root / "d1", allowed_hosts={"other.example.org"},
                resolve=fake_dns, opener=fake_open
            )
        with self.assertRaises(PatentWorkflowError):
            download_pdf(
                PDF_URL, self.root / "d2", allowed_hosts={"pdf.example.org"},
                resolve=fake_dns, opener=lambda req, timeout: FakePDFResponse(b"<html>Error</html>")
            )
        with self.assertRaises(PatentWorkflowError):
            download_pdf(
                PDF_URL, self.root / "d3", allowed_hosts={"pdf.example.org"},
                resolve=fake_dns,
                opener=lambda req, timeout: FakePDFResponse(PDF_DATA, final_url="https://other.example.org/p.pdf")
            )
        with self.assertRaises(PatentWorkflowError):
            download_pdf(
                PDF_URL, self.root / "d4", allowed_hosts={"pdf.example.org"},
                resolve=fake_dns,
                opener=lambda req, timeout: FakePDFResponse(PDF_DATA + b"X" * 2000),
                max_bytes=1000
            )

    def test_archive_requires_permission_and_preserves_online_source(self):
        workspace = LocalPatentWorkspace(self.root / "index.sqlite3")
        workspace.create_case("A", "消防泵高海拔吸水创新研究")
        doc_id = workspace.upsert_document("A", document(), public_pdf_url=PDF_URL)
        with self.assertRaises(PatentWorkflowError):
            archive_patent(
                workspace, case_id="A", doc_id=doc_id,
                storage_dir=self.root / "pdfs", allowed_hosts={"pdf.example.org"},
                authorized=False, resolve=fake_dns, opener=fake_open
            )
        archived = archive_patent(
            workspace, case_id="A", doc_id=doc_id,
            storage_dir=self.root / "pdfs", allowed_hosts={"pdf.example.org"},
            authorized=True, resolve=fake_dns, opener=fake_open
        )
        row = workspace.pdf_source("A", doc_id)
        self.assertEqual(archived["sha256"], sha256(PDF_DATA).hexdigest())
        self.assertEqual(row["public_pdf_url"], PDF_URL)
        self.assertEqual(row["pdf_sha256"], archived["sha256"])
        self.assertEqual(row["local_pdf_path"], archived["local_pdf_path"])


if __name__ == "__main__":
    unittest.main()
