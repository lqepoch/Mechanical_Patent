"""Policy-controlled Crawl4AI gateway for public non-patent web material.

Patent databases are accessed using licensed or official APIs. Crawl4AI is the
single HTML extraction engine, never a WAF-bypass or unrestricted spider.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import ipaddress
import json
import os
from pathlib import Path
import socket
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from .core import Evidence, PatentWorkflowError, utc_now

# A web page may be publicly accessible while its provider disallows bots.
# Provider-specific contractual rules must be reviewed before adding domains.
PROHIBITED_AUTOMATED_HOSTS = frozenset({"patentscope.wipo.int"})


def validate_web_url(
    url: str, allowed_hosts: set[str] | frozenset[str],
    *, resolve: Callable[..., Any] = socket.getaddrinfo,
) -> str:
    """Fail closed on host allowlist, invalid URL, non-global IP, local services."""
    if not isinstance(url, str) or len(url) > 2048:
        raise PatentWorkflowError("Invalid web URL")
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    allow = {h.lower().rstrip(".") for h in allowed_hosts}
    if parts.scheme != "https" or not host or not parts.netloc or parts.username or parts.password:
        raise PatentWorkflowError("Crawler accepts HTTPS public pages without URL-embedded credentials only.")
    try:
        port = parts.port
    except ValueError as exc:
        raise PatentWorkflowError("Invalid URL port.") from exc
    if port not in (None, 443):
        raise PatentWorkflowError("Nonstandard ports are blocked.")
    if host in PROHIBITED_AUTOMATED_HOSTS:
        raise PatentWorkflowError("Automated crawling is prohibited on this public interface.")
    if host not in allow:
        raise PatentWorkflowError("Web hostname was not explicitly allowlisted.")
    try:
        addresses = resolve(host, 443, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as exc:
        raise PatentWorkflowError("Cannot safely resolve crawler destination.") from exc
    if not addresses:
        raise PatentWorkflowError("No public destination addresses.")
    for entry in addresses:
        try:
            ip = ipaddress.ip_address(entry[4][0])
        except (IndexError, ValueError, TypeError) as exc:
            raise PatentWorkflowError("Invalid DNS resolution for crawl destination.") from exc
        if not ip.is_global:
            raise PatentWorkflowError("Local or non-global IP is forbidden to the web crawler.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


@dataclass(frozen=True)
class WebDocument:
    url: str
    title: str
    markdown: str
    retrieved_at: str
    content_sha256: str
    extractor: str = "crawl4ai"
    notice: str = "Source was fetched; its content and claims are not independently validated."

    def to_evidence(self) -> Evidence:
        return Evidence(
            publication="WEB-" + self.content_sha256[:20].upper(),
            title=self.title or self.url,
            url=self.url,
            source=self.extractor,
            retrieved_at=self.retrieved_at,
            abstract=self.markdown[:20000],
            kind="web",
            verified=True,  # source-fetched, not legal or substantive truth
        )


class Crawl4AIGateway:
    """Single-process Crawl4AI extraction with explicit site allowlist and robots.txt."""

    def __init__(self, allowed_hosts: set[str], *, timeout_ms: int = 30000,
                 max_pages: int = 12, max_chars: int = 150000):
        if not allowed_hosts:
            raise PatentWorkflowError("Crawl4AI requires an explicit host allowlist.")
        self.allowed_hosts = {h.lower().rstrip(".") for h in allowed_hosts}
        self.timeout_ms = max(5000, min(int(timeout_ms), 120000))
        self.max_pages = max(1, min(int(max_pages), 30))
        self.max_chars = max(1000, min(int(max_chars), 300000))

    async def collect(self, urls: list[str]) -> tuple[list[WebDocument], list[str]]:
        if len(urls) > self.max_pages:
            raise PatentWorkflowError("Page budget exceeded.")
        normalized = [validate_web_url(u, self.allowed_hosts) for u in urls]
        if len(set(normalized)) != len(normalized):
            normalized = list(dict.fromkeys(normalized))
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
        except ImportError as exc:
            raise PatentWorkflowError(
                "Optional Crawl4AI library missing: pip install -e '.[web]' && crawl4ai-setup"
            ) from exc
        config = CrawlerRunConfig(
            check_robots_txt=True,
            cache_mode=CacheMode.BYPASS,
            page_timeout=self.timeout_ms,
            word_count_threshold=5,
            excluded_tags=["script", "style"],
        )
        records: list[WebDocument] = []
        errors: list[str] = []
        async with AsyncWebCrawler(config=BrowserConfig(browser_type="chromium", headless=True)) as crawler:
            for url in normalized:
                try:
                    result = await crawler.arun(url=url, config=config)
                    if not result.success:
                        raise PatentWorkflowError(
                            "Crawl4AI refused or failed: " + str(result.error_message)[:240]
                        )
                    final = str(getattr(result, "url", "") or url)
                    # This check is post-fetch; production also needs network-level egress policy
                    # to prevent unsafe redirects/DNS rebinding before navigation.
                    final = validate_web_url(final, self.allowed_hosts)
                    markdown_data = result.markdown
                    markdown = getattr(markdown_data, "raw_markdown", None)
                    if markdown is None:
                        markdown = str(markdown_data or "")
                    markdown = markdown[:self.max_chars]
                    if not markdown.strip():
                        raise PatentWorkflowError("No extractable content in fetched web page.")
                    meta = getattr(result, "metadata", {}) or {}
                    title = str(meta.get("title", "") or url)[:300] if isinstance(meta, dict) else url
                    records.append(WebDocument(
                        url=final, title=title, markdown=markdown,
                        retrieved_at=utc_now(),
                        content_sha256=sha256(markdown.encode("utf-8")).hexdigest(),
                    ))
                except (PatentWorkflowError, OSError, ValueError) as exc:
                    errors.append(url + " — " + str(exc))
        return records, errors

    @staticmethod
    def write_capture(folder: Path, docs: list[WebDocument], errors: list[str]) -> None:
        from .core import save_json
        folder.mkdir(parents=True, exist_ok=True)
        entries = []
        for doc in docs:
            filename = "WEB-" + doc.content_sha256[:16] + ".md"
            # Content is untrusted and cannot become executable skills or system instructions.
            (folder / filename).write_text(doc.markdown, encoding="utf-8")
            item = asdict(doc)
            item.pop("markdown")
            item["content_file"] = filename
            entries.append(item)
        save_json(folder / "web_capture_manifest.json", {
            "engine": "crawl4ai", "pages": entries, "errors": errors,
            "robots_compliance_enabled": True,
        })
