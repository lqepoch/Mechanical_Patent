"""使用 Docling 提取已获许可的本地专利/论文 PDF；保留页码级来源。

- 绝不通过此工具抓取网页或外部 URL：原始下载由已有合规归档模块负责。
- Docling 为可选本地处理依赖；缺少离线模型资源时明确失败，不静默联网下载。
- 页面文本与表格只代表解析结果，尚未由人工核对公开原始 PDF。
"""
from __future__ import annotations

from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .core import PatentWorkflowError, save_json, utc_now

MAX_PDF_BYTES = 40 * 1024 * 1024
MAX_PAGES = 600
MAX_ITEMS = 30000
MAX_ITEM_LENGTH = 10000
MAX_TOTAL_CHARS = 3_000_000


def _default_docling_converter(artifacts: Path | None) -> Any:
    """强制离线模型资源，不允许隐式向模型托管平台外发用户文档。"""
    if artifacts is None or not artifacts.is_dir():
        raise PatentWorkflowError(
            "Docling 真实运行需要事先批准并准备离线模型目录；使用 --docling-artifacts 指定。"
        )
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise PatentWorkflowError(
            "未安装 Docling；若具有许可，可执行 python -m pip install -e '.[pdf]'。"
        ) from exc

    options = PdfPipelineOptions(
        artifacts_path=artifacts,
        do_ocr=False,
        enable_remote_services=False,
        do_table_structure=True,
    )
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )


def parse_local_pdf(
    original_path: Path, output_path: Path, *,
    authorized: bool,
    source_url: str = "",
    artifacts: Path | None = None,
    converter: Any | None = None,
    max_pages: int = 200,
) -> dict[str, Any]:
    """只接受已存在的本地 PDF，生成页码级 JSON；绝不自动触发下载。"""
    if not authorized:
        raise PatentWorkflowError("处理原始 PDF 需要明确的资料使用与保密授权。")
    path = Path(original_path)
    if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".pdf":
        raise PatentWorkflowError("只允许处理真实、非符号链接的本地 PDF。")
    if path.stat().st_size > MAX_PDF_BYTES or path.stat().st_size < 5:
        raise PatentWorkflowError("PDF 文件大小不符合解析预算。")
    if max_pages < 1 or max_pages > MAX_PAGES:
        raise PatentWorkflowError("最大 PDF 页数必须在合法范围内。")
    if source_url:
        u = urlsplit(source_url)
        if u.scheme != "https" or not u.hostname or u.username or u.password:
            raise PatentWorkflowError("原文来源必须为公开 HTTPS 链接，不得夹带认证信息。")
    digest = sha256()
    with path.open("rb") as handle:
        if not handle.read(5).startswith(b"%PDF-"):
            raise PatentWorkflowError("文件不具备原始 PDF 格式头。")
        handle.seek(0)
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    implementation = converter if converter is not None else _default_docling_converter(artifacts)
    try:
        # Mock implementations may provide only positional input to simplify offline CI.
        result = implementation.convert(str(path), max_num_pages=max_pages, max_file_size=MAX_PDF_BYTES)
        document = result.document
        rows: list[dict[str, Any]] = []
        total = 0
        for item, _level in document.iterate_items():
            text = getattr(item, "text", None)
            if not isinstance(text, str) or not text.strip():
                continue
            page = None
            bounding_box = None
            provenance = getattr(item, "prov", None)
            if provenance:
                page_no = getattr(provenance[0], "page_no", None)
                if isinstance(page_no, int) and 1 <= page_no <= max_pages:
                    page = page_no
                box = getattr(provenance[0], "bbox", None)
                if box is not None:
                    bounding_box = {
                        key: getattr(box, key)
                        for key in ("l", "t", "r", "b")
                        if isinstance(getattr(box, key, None), (float, int))
                    }
            snippet = text.strip()[:MAX_ITEM_LENGTH]
            total += len(snippet)
            if total > MAX_TOTAL_CHARS or len(rows) >= MAX_ITEMS:
                raise PatentWorkflowError("PDF 内容超过页面/段落解析预算。")
            rows.append({
                "page": page,
                "block": len(rows) + 1,
                "label": str(getattr(item, "label", "text")),
                "text": snippet,
                "bbox": bounding_box,
            })
        if not rows:
            raise PatentWorkflowError("Docling 没有提取到可用的正文或页码段落。")
    except PatentWorkflowError:
        raise
    except (OSError, ValueError, RuntimeError, TypeError, AttributeError) as exc:
        raise PatentWorkflowError("Docling PDF 解析失败，原始文件仍应由人工打开核验。") from exc
    try:
        tool_version = version("docling")
    except PackageNotFoundError:
        tool_version = "test-adapter"
    payload = {
        "parser": "docling",
        "parser_version": tool_version,
        "source_pdf_sha256": digest.hexdigest(),
        "source_url": source_url,
        "processed_at": utc_now(),
        "page_count_reported": len(getattr(document, "pages", {}) or {}),
        "blocks": rows,
        "review_status": "awaiting_original_pdf_review",
        "legal_evidence_note": (
            "结构化提取结果仅用于定位和索引；具体公开内容、权利要求和附图"
            "必须以原始公开 PDF 为准。"
        ),
    }
    save_json(Path(output_path), payload)
    return {
        "output": str(Path(output_path).resolve()), "sha256": payload["source_pdf_sha256"],
        "blocks": len(rows), "status": payload["review_status"],
    }
