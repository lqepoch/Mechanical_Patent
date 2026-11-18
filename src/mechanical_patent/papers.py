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
from typing import Any, Callable
from urllib import error, parse, request

from .core import Evidence, PatentWorkflowError, deduplicate, utc_now

MAX_RESPONSE = 3_000_000
MAX_QUERY = 240
USER_AGENT = "MechanicalPatentResearch/0.2 (research tool; see https://github.com/lqepoch/Mechanical_Patent)"


def _fetch_json(url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})})
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
        raise PatentWorkflowError(f"Scholarly provider HTTP {exc.code}; inspect quota or query") from exc
    except (error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise PatentWorkflowError("Scholarly provider unavailable or returned invalid JSON") from exc


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
        term = query.strip()[:MAX_QUERY]
        if not term:
            return []
        params = {"search": term, "per_page": max(1, min(limit, 25))}
        headers = {}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        url = "https://api.openalex.org/works?" + parse.urlencode(params)
        payload = self.fetch_json(url, headers=headers)
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
                retrieved_at=utc_now(), abstract=_abstract_from_inverted_index(item.get("abstract_inverted_index")),
                publication_date=str(item.get("publication_date") or ""),
                jurisdiction="", kind="paper", verified=True,
            ))
        return deduplicate(out)


class CrossrefProvider:
    name = "crossref"

    def __init__(self, *, contact_email: str | None = None, fetch_json: Callable[..., dict] | None = None):
        self.contact_email = contact_email if contact_email is not None else os.getenv("PATENT_CONTACT_EMAIL", "")
        self.fetch_json = fetch_json or _fetch_json

    def search(self, query: str, *, limit: int = 10) -> list[Evidence]:
        term = query.strip()[:MAX_QUERY]
        if not term:
            return []
        params = {"query.bibliographic": term, "rows": max(1, min(limit, 25))}
        if self.contact_email:
            params["mailto"] = self.contact_email
        url = "https://api.crossref.org/works?" + parse.urlencode(params)
        payload = self.fetch_json(url)
        items = payload.get("message", {}).get("items", [])
        if not isinstance(items, list):
            raise PatentWorkflowError("Crossref items must be a list")
        out: list[Evidence] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            doi = _doi(item.get("DOI"))
            title_list = item.get("title")
            title = str(title_list[0] if isinstance(title_list, list) and title_list else "").strip()
            if not doi or not title:
                continue
            out.append(Evidence(
                publication=doi, title=title,
                url=_canonical_url(doi, str(item.get("URL") or "")),
                source=self.name, retrieved_at=utc_now(),
                abstract=_crossref_abstract(item.get("abstract")),
                publication_date=_crossref_date(item),
                jurisdiction="", kind="paper", verified=True,
            ))
        return deduplicate(out)
