"""专利原始 PDF 的可选合规本地归档。

默认以公开 PDF 的原始 HTTPS 链接提供在线核对；用户明确授权且网站
条款允许时，另存一份内容寻址的 PDF 到本地，记录 SHA-256 与来源。

浏览器/网页内容采集一律走 Crawl4AI；本模块仅针对已知且合法授权的
原始 PDF 二进制文件进行直接下载，不能用来搜索、绕开网站访问控制。
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import socket
import tempfile
from typing import Callable, Any
from urllib import error, request

from .core import PatentWorkflowError
from .local_workspace import LocalPatentWorkspace
from .web_crawler import validate_web_url

MAX_PDF_BYTES = 40 * 1024 * 1024
BLOCK_SIZE = 64 * 1024


class _BlockRedirect(request.HTTPRedirectHandler):
    """在发生任何重定向时中止，避免跳转到未获许可的站点。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PatentWorkflowError("PDF 下载发生重定向；请先核验最终地址并将其加入来源索引。")


def download_pdf(
    url: str, destination_dir: Path, *, allowed_hosts: set[str],
    max_bytes: int = MAX_PDF_BYTES, timeout: int = 30,
    resolve: Callable[..., Any] = socket.getaddrinfo,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """仅从允许的 HTTPS 域名读取 PDF，按内容哈希保存；不替用户判断版权。

    opener 和 resolve 可替换为模拟实现，保证 CI 不访问真实互联网。
    生产环境还需由出站代理绑定域名解析 IP、强制禁止内部网段访问。
    """
    source = validate_web_url(url, set(allowed_hosts), resolve=resolve)
    if not 1_000 <= max_bytes <= MAX_PDF_BYTES:
        raise PatentWorkflowError("PDF 大小限制不合法。")
    storage = Path(destination_dir)
    storage.mkdir(parents=True, exist_ok=True)
    writer = opener or request.build_opener(_BlockRedirect()).open
    temp_name = ""
    size = 0
    digest = sha256()
    try:
        req = request.Request(
            source,
            headers={"User-Agent": "MechanicalPatentEvidence/0.1", "Accept": "application/pdf"},
        )
        with writer(req, timeout=timeout) as response:
            final = response.geturl()
            if final != source:
                raise PatentWorkflowError("PDF 原始来源地址被重定向或变更。")
            declared_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].lower()
            if declared_type in {"text/html", "application/xhtml+xml", "text/plain"}:
                raise PatentWorkflowError("原始链接返回了网页或文本，缺少 PDF。")
            with tempfile.NamedTemporaryFile(
                prefix=".pdf-", suffix=".tmp", dir=storage, delete=False,
            ) as tmp:
                temp_name = tmp.name
                first = True
                while True:
                    chunk = response.read(BLOCK_SIZE)
                    if not chunk:
                        break
                    if first:
                        first = False
                        if not chunk.startswith(b"%PDF-"):
                            raise PatentWorkflowError("原始文件没有合法的 PDF 文件头。")
                    size += len(chunk)
                    if size > max_bytes:
                        raise PatentWorkflowError("PDF 超过许可的单文档下载大小。")
                    digest.update(chunk)
                    tmp.write(chunk)
                if not size:
                    raise PatentWorkflowError("PDF 文件为空。")
                tmp.flush()
                os.fsync(tmp.fileno())
        checksum = digest.hexdigest()
        final_path = (storage / (checksum + ".pdf")).resolve()
        if final_path.exists():
            if sha256(final_path.read_bytes()).hexdigest() != checksum:
                raise PatentWorkflowError("同名 PDF 本地文件的内容哈希不匹配。")
        else:
            os.replace(temp_name, final_path)
            temp_name = ""
        return {
            "url": source, "local_pdf_path": str(final_path),
            "sha256": checksum, "bytes": size, "content_type": "application/pdf",
            "online_url": source,
        }
    except error.HTTPError as exc:
        raise PatentWorkflowError(f"公开 PDF 下载失败：HTTP {exc.code}") from exc
    except error.URLError as exc:
        raise PatentWorkflowError("公开 PDF 网络不可达，请使用索引中的原始链接在线核验。") from exc
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def archive_patent(
    workspace: LocalPatentWorkspace, *, case_id: str, doc_id: str,
    storage_dir: Path, allowed_hosts: set[str],
    authorized: bool, **download_kwargs: Any,
) -> dict[str, Any]:
    """用户授权后归档真实专利 PDF；原始在线链接永久保留。"""
    if not authorized:
        raise PatentWorkflowError("本地 PDF 归档需要明确的下载授权和网站使用许可。")
    record = workspace.pdf_source(case_id, doc_id)
    if record["kind"] != "patent":
        raise PatentWorkflowError("此归档入口仅接受专利文献。")
    url = record["public_pdf_url"]
    if not url:
        raise PatentWorkflowError("未建立已核对的原始 PDF 链接，请先用 doc-review 录入。")
    result = download_pdf(
        url, Path(storage_dir), allowed_hosts=allowed_hosts, **download_kwargs
    )
    workspace.link_local_pdf(
        case_id, doc_id, local_path=Path(result["local_pdf_path"]),
        digest=result["sha256"], public_url=result["online_url"],
    )
    return {
        "case_id": case_id, "doc_id": doc_id,
        "online_pdf_url": result["online_url"],
        "local_pdf_path": result["local_pdf_path"],
        "sha256": result["sha256"], "bytes": result["bytes"],
    }
