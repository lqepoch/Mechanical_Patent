"""经用户授权的公开专利 PDF 本地归档：来源留存、内容寻址和 TLS 固定 IP。

仅接受已核对的公开 PDF 原始 HTTPS URL，拒绝域名白名单以外的来源、
重定向、私网 IP、非 PDF 内容和过大的响应。HTML 网页采集统一走 Crawl4AI。

注意：本模块保证请求直接连接经公网 IP 核验的目的地，不调用系统代理；
企业部署仍要叠加独立出站防火墙、许可证策略和内容安全扫描。
"""
from __future__ import annotations

from hashlib import sha256
from http.client import HTTPSConnection, HTTPResponse
import ipaddress
import os
from pathlib import Path
import socket
import ssl
import tempfile
from typing import Callable, Any
from urllib.parse import urlsplit

from .core import PatentWorkflowError
from .local_workspace import LocalPatentWorkspace
from .web_crawler import validate_web_url

MAX_PDF_BYTES = 40 * 1024 * 1024
BLOCK_SIZE = 64 * 1024


class _PinnedHTTPSConnection(HTTPSConnection):
    """连接已核验的公网 IP，同时用原主机名完成 SNI 和 TLS 证书验证。"""

    def __init__(self, hostname: str, verified_ip: str, *, timeout: int):
        super().__init__(
            hostname, port=443, timeout=timeout, context=ssl.create_default_context()
        )
        self._verified_ip = verified_ip

    def connect(self) -> None:
        raw = socket.create_connection((self._verified_ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


class _PinnedResponse:
    def __init__(self, conn: HTTPSConnection, result: HTTPResponse, original_url: str):
        self.conn = conn
        self.result = result
        self.original_url = original_url
        self.headers = result.headers

    def __enter__(self):
        return self

    def __exit__(self, *_):
        try:
            self.result.close()
        finally:
            self.conn.close()

    def geturl(self) -> str:
        return self.original_url

    def read(self, limit: int) -> bytes:
        return self.result.read(limit)


def _open_verified_pdf(
    source: str, *, timeout: int,
    resolve: Callable[..., Any] = socket.getaddrinfo,
) -> _PinnedResponse:
    """解析且严格检查公网地址，建立不跟随跳转的直接 HTTPS 连接。"""
    parts = urlsplit(source)
    hostname = parts.hostname
    if parts.scheme != "https" or not hostname or parts.port not in {None, 443}:
        raise PatentWorkflowError("仅支持标准 HTTPS PDF 来源。")
    try:
        infos = resolve(hostname, 443, type=socket.SOCK_STREAM)
        addresses = []
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if not ip.is_global:
                raise PatentWorkflowError("PDF 来源解析到了非公网 IP，已阻断。")
            addresses.append(str(ip))
    except (OSError, IndexError, TypeError, ValueError) as exc:
        raise PatentWorkflowError("无法安全解析公开 PDF 服务器地址。") from exc
    if not addresses:
        raise PatentWorkflowError("公开 PDF 来源无可验证的公网 IP。")
    conn = _PinnedHTTPSConnection(hostname, addresses[0], timeout=timeout)
    resource = parts.path or "/"
    if parts.query:
        resource += "?" + parts.query
    try:
        conn.request("GET", resource, headers={
            "Host": hostname,
            "User-Agent": "MechanicalPatentEvidence/0.2",
            "Accept": "application/pdf",
            "Connection": "close",
        })
        reply = conn.getresponse()
        if reply.status != 200:
            conn.close()
            raise PatentWorkflowError(
                f"公开 PDF 返回 HTTP {reply.status}；重定向与异常状态均不自动跟随。"
            )
        return _PinnedResponse(conn, reply, source)
    except BaseException:
        conn.close()
        raise


def download_pdf(
    url: str, destination_dir: Path, *, allowed_hosts: set[str],
    max_bytes: int = MAX_PDF_BYTES, timeout: int = 30,
    resolve: Callable[..., Any] = socket.getaddrinfo,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """本地合规归档。opener 与 resolve 只用于离线测试及明确授权的适配器。"""
    source = validate_web_url(url, set(allowed_hosts), resolve=resolve)
    if not 1_000 <= max_bytes <= MAX_PDF_BYTES:
        raise PatentWorkflowError("PDF 大小预算不合法。")
    storage = Path(destination_dir)
    storage.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    size = 0
    digest = sha256()
    try:
        response = (
            opener(source, timeout=timeout)
            if opener is not None else
            _open_verified_pdf(source, timeout=timeout, resolve=resolve)
        )
        with response:
            if response.geturl() != source:
                raise PatentWorkflowError("公开 PDF 地址发生变更或重定向，已中止下载。")
            declared_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].lower()
            if declared_type in {"text/html", "application/xhtml+xml", "text/plain"}:
                raise PatentWorkflowError("来源返回网页或非 PDF 文本。")
            with tempfile.NamedTemporaryFile(
                prefix=".pdf-", suffix=".tmp", dir=storage, delete=False
            ) as file:
                temp_name = file.name
                first = True
                while True:
                    chunk = response.read(BLOCK_SIZE)
                    if not chunk:
                        break
                    if first:
                        first = False
                        if not chunk.startswith(b"%PDF-"):
                            raise PatentWorkflowError("公开原文不存在合法 PDF 文件头。")
                    size += len(chunk)
                    if size > max_bytes:
                        raise PatentWorkflowError("公开 PDF 大小超出下载预算。")
                    digest.update(chunk)
                    file.write(chunk)
                if not size:
                    raise PatentWorkflowError("公开 PDF 为空。")
                file.flush()
                os.fsync(file.fileno())
        checksum = digest.hexdigest()
        target = (storage / (checksum + ".pdf")).resolve()
        if target.is_file():
            if sha256(target.read_bytes()).hexdigest() != checksum:
                raise PatentWorkflowError("同名文献本地内容损坏或被替换。")
        else:
            os.replace(temp_name, target)
            temp_name = ""
        return {
            "url": source, "local_pdf_path": str(target),
            "sha256": checksum, "bytes": size, "online_url": source,
        }
    except (OSError, ssl.SSLError, TimeoutError) as exc:
        raise PatentWorkflowError("原始公开 PDF 下载失败；可继续在线打开来源核验。") from exc
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def archive_patent(
    workspace: LocalPatentWorkspace, *, case_id: str, doc_id: str,
    storage_dir: Path, allowed_hosts: set[str], authorized: bool,
    **download_kwargs: Any,
) -> dict[str, Any]:
    if not authorized:
        raise PatentWorkflowError("归档公开 PDF 需要明确授权和网站许可。")
    source = workspace.pdf_source(case_id, doc_id)
    if source["kind"] != "patent":
        raise PatentWorkflowError("仅可归档专利原始 PDF。")
    url = source["public_pdf_url"]
    if not url:
        raise PatentWorkflowError("没有已核对的公开 PDF 原始地址；请先记录在线来源。")
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
