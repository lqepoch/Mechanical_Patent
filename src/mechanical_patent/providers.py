"""Authorized patent providers. The service never scrapes WIPO or CNIPA pages."""
from __future__ import annotations

from base64 import b64encode
import json
import os
from pathlib import Path
from typing import Protocol
from urllib import error, parse, request
import xml.etree.ElementTree as ET

from .core import Evidence, PatentWorkflowError, deduplicate, utc_now


class PatentProvider(Protocol):
    name: str
    def search(self, term: str, *, limit: int = 10) -> list[Evidence]: ...


class ImportedPatentProvider:
    """Untrusted user-provided corpus; imported records cannot masquerade as live verification."""
    name = "imported"

    def __init__(self, path: str | Path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        source = payload.get("records", payload) if isinstance(payload, dict) else payload
        if not isinstance(source, list):
            raise PatentWorkflowError("Imported corpus must be a JSON list or {records: [...]} ")
        self.records = [Evidence.from_dict(x, imported=True) for x in source]

    def search(self, term: str, *, limit: int = 10) -> list[Evidence]:
        words = [t.lower() for t in term.split() if t]
        if not words:
            return self.records[:limit]
        found = [r for r in self.records if any(w in (r.title + " " + r.abstract + " " + r.claims).lower() for w in words)]
        return found[:limit]


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1].split(":", 1)[-1]


def _nodes(root: ET.Element, name: str) -> list[ET.Element]:
    return [e for e in root.iter() if _local(e.tag) == name]


def _first_text(root: ET.Element, name: str) -> str:
    for node in _nodes(root, name):
        value = "".join(node.itertext()).strip()
        if value:
            return value
    return ""


def parse_epo_xml(xml_text: bytes, *, limit: int = 10) -> list[Evidence]:
    """Parse EPO OPS biblio XML; missing abstracts or claims stay explicitly missing."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise PatentWorkflowError("EPO returned invalid XML") from exc
    records: list[Evidence] = []
    for item in _nodes(root, "exchange-document"):
        country = item.attrib.get("country", "")
        number = item.attrib.get("doc-number", "")
        kind = item.attrib.get("kind", "")
        publication = "".join((country, number, kind))
        if not publication:
            continue
        title = _first_text(item, "invention-title") or "Untitled patent"
        date = _first_text(item, "date")
        abstract = _first_text(item, "abstract")
        url = "https://worldwide.espacenet.com/patent/search?q=" + parse.quote("pn=" + publication)
        records.append(Evidence(
            publication=publication, title=title, url=url, source="epo-ops",
            retrieved_at=utc_now(), abstract=abstract, publication_date=date,
            jurisdiction=country, verified=True,
        ))
        if len(records) >= limit:
            break
    return deduplicate(records)


class EPOOPSProvider:
    """EPO OPS 3.2 OAuth, bounded search and optional document claims retrieval."""
    name = "epo-ops"
    base_url = "https://ops.epo.org/3.2"

    def __init__(self, client_id: str | None = None, client_secret: str | None = None, timeout: int = 30):
        self.client_id = client_id or os.getenv("EPO_OPS_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("EPO_OPS_CLIENT_SECRET", "")
        self.timeout = timeout
        if not self.client_id or not self.client_secret:
            raise PatentWorkflowError("Configure EPO_OPS_CLIENT_ID and EPO_OPS_CLIENT_SECRET.")
        self._token: str | None = None

    def _get_token(self) -> str:
        if self._token:
            return self._token
        auth = b64encode((self.client_id + ":" + self.client_secret).encode()).decode()
        req = request.Request(
            self.base_url + "/auth/accesstoken",
            data=b"grant_type=client_credentials",
            headers={"Authorization": "Basic " + auth, "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                data = json.load(response)
            self._token = data["access_token"]
            return self._token
        except (error.URLError, KeyError, ValueError) as exc:
            raise PatentWorkflowError("EPO authentication failed; verify authorized credentials and quota.") from exc

    def _get(self, path: str, extra_headers: dict[str, str] | None = None) -> bytes:
        headers = {"Authorization": "Bearer " + self._get_token(), "Accept": "application/xml"}
        headers.update(extra_headers or {})
        req = request.Request(self.base_url + path, headers=headers)
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                return response.read(4_000_000)
        except error.HTTPError as exc:
            raise PatentWorkflowError(f"EPO HTTP {exc.code}; check query, limits and OPS access.") from exc
        except error.URLError as exc:
            raise PatentWorkflowError("EPO unavailable; provider error was recorded.") from exc

    def search(self, term: str, *, limit: int = 10) -> list[Evidence]:
        return self.search_page(term, limit=limit)["records"]

    def search_page(
        self, term: str, *, cursor: str | None = None, limit: int = 20,
    ) -> dict[str, object]:
        """按 OPS Range 有界翻页。游标是本地偏移量，绝不调用未授权网页抓取。"""
        limit = max(1, min(int(limit), 20))
        term = term.strip()[:180]
        if not term:
            return {"records": [], "next_cursor": None, "total_results": None}
        start = 1 if cursor in (None, "*", "") else int(cursor)
        if not 1 <= start <= 2000:
            raise PatentWorkflowError("EPO OPS 当前检索结果超过允许的窗口，请细化检索式。")
        limit = min(limit, 2001 - start)
        cql = "ti=" + '"' + term.replace('"', "") + '"'
        path = "/rest-services/published-data/search/biblio?" + parse.urlencode({"q": cql})
        found = parse_epo_xml(
            self._get(path, {"X-OPS-Range": f"{start}-{start + limit - 1}"}),
            limit=limit,
        )
        next_cursor = (
            str(start + len(found))
            if len(found) == limit and start + len(found) <= 2000 else None
        )
        return {"records": found, "next_cursor": next_cursor, "total_results": None}

    def claims(self, publication: str) -> str:
        """Claims are fetched separately: search/biblio responses do not prove claim coverage."""
        if not publication or len(publication) > 32 or not publication.isalnum():
            raise PatentWorkflowError("Invalid publication identifier")
        raw = self._get("/rest-services/published-data/publication/epodoc/" + publication + "/claims")
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise PatentWorkflowError("EPO claims XML invalid") from exc
        return "\n".join(" ".join("".join(n.itertext()).split()) for n in _nodes(root, "claim-text"))
