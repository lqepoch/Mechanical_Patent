"""Scholarly literature discovery. No LLM API and no webpage scraping.

OpenAlex and Crossref provide metadata, not a guarantee of legally reusable full
text. HTML extraction is delegated to the repository's Crawl4AI gateway.
"""
from __future__ import annotations

from datetime import datetime
from html import unescape
import json
import os
import re
import time
from typing import Any, Callable
from urllib import error, parse, request

from .core import Evidence, PatentWorkflowError, deduplicate, utc_now

MAX_RESPONSE = 8_000_000
MAX_QUERY = 240
USER_AGENT = "MechanicalPatentResearch/0.2 (research tool; see https://github.com/lqepoch/Mechanical_Patent)"


def _fetch_json(url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    )
    for attempt in range(4):
        try:
            with request.urlopen(req, timeout=25) as response:
                raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise PatentWorkflowError("Scholarly response exceeded safe size limit")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise PatentWorkflowError("Scholarly service returned a non-object payload")
            return result
        except error.HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt < 3:
                retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
                try:
                    delay = min(30.0, max(0.25, float(retry_after)))
                except (TypeError, ValueError):
                    delay = min(12.0, 2.0 ** attempt)
                time.sleep(delay)
                continue
            raise PatentWorkflowError(
                f"Scholarly provider HTTP {exc.code}; inspect quota or query"
            ) from exc
        except (error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise PatentWorkflowError(
                "Scholarly provider unavailable or returned invalid JSON"
            ) from exc
    raise PatentWorkflowError("Scholarly retry budget exhausted")

def _doi(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    return text.lower().strip()


def _canonical_url(doi: str, fallback: str) -> str:
    if doi:
        return "https://doi.org/" + parse.quote(doi, safe="/:")
    return fallback


def _abstract_from_inverted_index(index: Any) -> str:
    """OpenAlex abstracts are often an inverted index, not a plain text field."""
    if not isinstance(index, dict):
        return ""
    words: dict[int, str] = {}
    for word, places in index.items():
        if not isinstance(word, str) or not isinstance(places, list):
            continue
        for pos in places:
            if isinstance(pos, int) and 0 <= pos < 8000:
                words[pos] = word
    if not words:
        return ""
    return " ".join(words[p] for p in sorted(words))[:6000]


def _crossref_abstract(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    return " ".join(unescape(re.sub(r"<[^>]*>", " ", text)).split())[:6000]


def _crossref_date(item: dict[str, Any]) -> str:
    for field in ("published", "published-online", "published-print", "issued"):
        parts = item.get(field, {}).get("date-parts", []) if isinstance(item.get(field), dict) else []
        if parts and isinstance(parts[0], list) and parts[0] and isinstance(parts[0][0], int):
            values = parts[0][:3]
            return "-".join([str(values[0]).zfill(4)] + [str(x).zfill(2) for x in values[1:]])
    return ""


class OpenAlexProvider:
    name = "openalex"

    def __init__(self, *, api_key: str | None = None, fetch_json: Callable[..., dict] | None = None):
        self.api_key = api_key if api_key is not None else os.getenv("OPENALEX_API_KEY", "")
        self.fetch_json = fetch_json or _fetch_json

    def search(self, query: str, *, limit: int = 10) -> list[Evidence]:
        return self.search_page(query, limit=min(limit, 25))["records"]

    def search_page(
        self, query: str, *, cursor: str | None = None, limit: int = 100,
    ) -> dict[str, Any]:
        """分页官方 OpenAlex works；下一页游标保留供断点续检。"""
        term = query.strip()[:MAX_QUERY]
        if not term:
            return {"records": [], "next_cursor": None, "total_results": 0}
        params = {"search": term, "per_page": max(1, min(limit, 100))}
        if cursor is not None:
            params["cursor"] = cursor or "*"
        headers = {"Authorization": "Bearer " + self.api_key} if self.api_key else {}
        payload = self.fetch_json(
            "https://api.openalex.org/works?" + parse.urlencode(params), headers=headers
        )
        items = payload.get("results", [])
        if not isinstance(items, list):
            raise PatentWorkflowError("OpenAlex results must be a list")
        out: list[Evidence] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            doi = _doi(item.get("doi"))
            oa_url = str(item.get("id") or "")
            publication = doi or oa_url.rsplit("/", 1)[-1]
            title = str(item.get("display_name") or item.get("title") or "").strip()
            canonical = _canonical_url(doi, oa_url)
            if not publication or not title or not canonical.startswith("https://"):
                continue
            out.append(Evidence(
                publication=publication, title=title, url=canonical, source=self.name,
                retrieved_at=utc_now(),
                abstract=_abstract_from_inverted_index(item.get("abstract_inverted_index")),
                publication_date=str(item.get("publication_date") or ""),
                jurisdiction="", kind="paper", verified=True,
            ))
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        next_cursor = meta.get("next_cursor") if len(items) >= int(params["per_page"]) else None
        next_cursor = next_cursor[:4096] if isinstance(next_cursor, str) else None
        return {
            "records": deduplicate(out), "next_cursor": next_cursor,
            "total_results": meta.get("count"),
        }


class CrossrefProvider:
    name = "crossref"

    def __init__(self, *, contact_email: str | None = None, fetch_json: Callable[..., dict] | None = None):
        self.contact_email = contact_email if contact_email is not None else os.getenv("PATENT_CONTACT_EMAIL", "")
        self.fetch_json = fetch_json or _fetch_json

    def search(self, query: str, *, limit: int = 10) -> list[Evidence]:
        return self.search_page(query, limit=min(limit, 25))["records"]

    def search_page(
        self, query: str, *, cursor: str | None = None, limit: int = 100,
    ) -> dict[str, Any]:
        """Crossref cursor 深分页；游标失效需由上层从第一页幂等重检。"""
        term = query.strip()[:MAX_QUERY]
        if not term:
            return {"records": [], "next_cursor": None, "total_results": 0}
        size = max(1, min(limit, 100))
        params = {"query.bibliographic": term, "rows": size}
        if cursor is not None:
            params["cursor"] = cursor or "*"
        if self.contact_email:
            params["mailto"] = self.contact_email
        payload = self.fetch_json("https://api.crossref.org/works?" + parse.urlencode(params))
        message = payload.get("message")
        if not isinstance(message, dict):
            raise PatentWorkflowError("Crossref message must be a JSON object")
        items = message.get("items", [])
        if not isinstance(items, list):
            raise PatentWorkflowError("Crossref items must be a list")
        out: list[Evidence] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            doi = _doi(item.get("DOI"))
            titles = item.get("title")
            title = str(titles[0] if isinstance(titles, list) and titles else "").strip()
            if not doi or not title:
                continue
            out.append(Evidence(
                publication=doi, title=title,
                url=_canonical_url(doi, str(item.get("URL") or "")),
                source=self.name, retrieved_at=utc_now(),
                abstract=_crossref_abstract(item.get("abstract")),
                publication_date=_crossref_date(item), jurisdiction="",
                kind="paper", verified=True,
            ))
        next_cursor = message.get("next-cursor") if len(items) >= size else None
        next_cursor = next_cursor[:4096] if isinstance(next_cursor, str) else None
        return {
            "records": deduplicate(out), "next_cursor": next_cursor,
            "total_results": message.get("total-results"),
        }

