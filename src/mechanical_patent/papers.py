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
        from .paper_sources import _mk, merge_paper_records
        out: list[Evidence] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            oa_url = str(item.get("id") or "")
            location = item.get("best_oa_location") or {}
            access = item.get("open_access") or {}
            authorships = item.get("authorships") or []
            e = _mk(
                self.name, title=item.get("display_name") or item.get("title"),
                identifier=oa_url.rsplit("/", 1)[-1], url=oa_url, doi=item.get("doi"),
                abstract=_abstract_from_inverted_index(item.get("abstract_inverted_index")),
                date=item.get("publication_date"), pdf=location.get("pdf_url"),
                authors=[a["author"]["display_name"] for a in authorships
                         if isinstance(a, dict) and isinstance(a.get("author"), dict)
                         and a["author"].get("display_name")],
                cited=item.get("cited_by_count"), is_oa=access.get("is_oa"),
                oa_status=access.get("oa_status"), license=location.get("license"),
            )
            if e:
                out.append(e)
        return merge_paper_records(out)


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
        from .paper_sources import _mk, merge_paper_records
        out: list[Evidence] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            doi = _doi(item.get("DOI"))
            title_list = item.get("title")
            title = str(title_list[0] if isinstance(title_list, list) and title_list else "").strip()
            if not doi or not title:
                continue
            authors = item.get("author") or []
            e = _mk(
                self.name, title=title, identifier=doi, doi=doi,
                url=item.get("URL") or _canonical_url(doi, ""),
                abstract=_crossref_abstract(item.get("abstract")),
                date=_crossref_date(item),
                authors=[" ".join(str(a.get(x) or "") for x in ("given", "family")).strip()
                         for a in authors if isinstance(a, dict)],
            )
            if e:
                out.append(e)
        return merge_paper_records(out)
