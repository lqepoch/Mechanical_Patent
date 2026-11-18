"""可选择的学术检索适配器和开放全文链接补全。

所有提供方只返回元数据/可能的 PDF HTTPS 链接；链接未被下载或核实。
支付型接口需显式 opt-in，严禁绕过付费墙。无额外第三方依赖。
"""
from __future__ import annotations

from dataclasses import replace
from html import unescape
import json
import os
import re
import threading
import time
from typing import Any, Callable
from urllib import error, parse, request
import xml.etree.ElementTree as ET

from .core import Evidence, PatentWorkflowError, utc_now
from .papers import (
    MAX_QUERY, MAX_RESPONSE, USER_AGENT, _canonical_url, _crossref_abstract,
    _doi, _fetch_json,
)

SEARCH_SOURCES = ("openalex", "crossref", "semantic-scholar", "arxiv",
                  "europe-pmc", "pubmed", "core", "lens")
PAID_OR_LICENSED = frozenset({"core", "lens"})
SOURCE_DESCRIPTIONS = {
    "openalex": "跨学科论文、摘要、OA 和引文（可匿名试用，按量计费）",
    "crossref": "DOI/出版社元数据、部分摘要",
    "semantic-scholar": "学术图谱、引用次数及开放 PDF（推荐配置 API Key）",
    "arxiv": "物理、工程、计算机预印本；PDF 可能有不同版权许可",
    "europe-pmc": "生命科学、医学及部分跨学科 OA 全文链接",
    "pubmed": "医学和生命科学索引，PDF 需通过 OA 来源另外查询",
    "core": "开放存储库聚合；机构/商业 API 许可需核查",
    "lens": "付费授权的论文-专利关联检索",
    "unpaywall": "DOI→合法开放获取位置补全；不支持关键词搜索",
}
_GATES_LOCK = threading.Lock()
_LAST_CALL: dict[str, float] = {}


def _pace(source: str, minimum_seconds: float) -> None:
    """进程内共享保守限流；多实例部署还须增加集中式限流。"""
    if minimum_seconds <= 0:
        return
    with _GATES_LOCK:
        now = time.monotonic()
        remaining = _LAST_CALL.get(source, 0.0) + minimum_seconds - now
        if remaining > 0:
            time.sleep(remaining)
        _LAST_CALL[source] = time.monotonic()


def _fetch_xml(url: str, *, headers: dict[str, str] | None = None) -> bytes:
    req = request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/atom+xml, application/xml",
        **(headers or {}),
    })
    try:
        with request.urlopen(req, timeout=25) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise PatentWorkflowError("学术 XML 响应超过安全长度。")
        return raw
    except error.HTTPError as exc:
        raise PatentWorkflowError(f"学术 XML 来源 HTTP {exc.code}（配额、限流或授权问题）。") from exc
    except (error.URLError, OSError) as exc:
        raise PatentWorkflowError("学术 XML 来源不可用。") from exc


def _post_json(url: str, *, body: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    """授权学术数据源的有界 JSON POST；不会将访问令牌写入 URL。"""
    req = request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                          method="POST", headers={
                              "User-Agent": USER_AGENT, "Content-Type": "application/json",
                              "Accept": "application/json", **(headers or {}),
                          })
    try:
        with request.urlopen(req, timeout=25) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise PatentWorkflowError("学术 JSON POST 响应超过安全长度。")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise PatentWorkflowError("学术 JSON POST 响应必须为对象。")
        return data
    except error.HTTPError as exc:
        raise PatentWorkflowError(f"学术 JSON POST 来源 HTTP {exc.code}（检查授权和限额）。") from exc
    except (error.URLError, OSError, ValueError) as exc:
        raise PatentWorkflowError("学术 JSON POST 来源不可用或数据无效。") from exc


def _https(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    try:
        parts = parse.urlsplit(value)
    except ValueError:
        return ""
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return ""
    return value[:3000]


def _plain(value: Any, maximum: int = 6000) -> str:
    return _crossref_abstract(value)[:maximum]


def _text(node: ET.Element | None) -> str:
    return " ".join("".join(node.itertext()).split()) if node is not None else ""


def _mk(source: str, *, title: Any, identifier: Any, url: Any, doi: Any = "",
        abstract: Any = "", date: Any = "", pdf: Any = "", authors: Any = (),
        cited: Any = None, is_oa: Any = None, license: Any = "", oa_status: Any = "") -> Evidence | None:
    title = str(title or "").strip()[:1500]
    doi = _doi(doi)
    identifier = str(identifier or "").strip()[:180]
    publication = doi or identifier
    landing = _canonical_url(doi, _https(url))
    if not title or not publication or not _https(landing):
        return None
    names: list[str] = []
    if isinstance(authors, (list, tuple)):
        for author in authors[:50]:
            name = author if isinstance(author, str) else ""
            if name and name.strip():
                names.append(name.strip()[:160])
    citation_count = cited if type(cited) is int and cited >= 0 else None
    metadata = {
        "schema_version": 1, "doi": doi, "authors": names,
        "citation_count": citation_count,
        "is_open_access": is_oa if isinstance(is_oa, bool) else None,
        "oa_status": str(oa_status or "")[:50],
        "license": str(license or "")[:150],
        "source_ids": {source: identifier},
        "sources": [source],
        "pdf_link_status": "unverified_discovery" if _https(pdf) else "not_found",
        "full_text_verified": False,
    }
    return Evidence(
        publication=publication, title=title, url=landing, source=source,
        retrieved_at=utc_now(), abstract=_plain(abstract),
        publication_date=str(date or "")[:32], kind="paper", verified=True,
        pdf_url=_https(pdf), paper_metadata=metadata,
    )


def merge_paper_records(records: list[Evidence]) -> list[Evidence]:
    """按 DOI 或原生编号去重并合并互补字段，保留每个数据来源。"""
    ordered: dict[str, Evidence] = {}
    for item in records:
        if item.kind != "paper":
            continue
        key = item.publication.strip().lower()
        if key not in ordered:
            ordered[key] = item
            continue
        original = ordered[key]
        a, b = dict(original.paper_metadata), dict(item.paper_metadata)
        sources = list(dict.fromkeys([*a.get("sources", [original.source]),
                                     *b.get("sources", [item.source])]))
        ids = {**a.get("source_ids", {}), **b.get("source_ids", {})}
        authors = a.get("authors") or b.get("authors") or []
        best_pdf = original.pdf_url or item.pdf_url
        merged = {
            **b, **a,
            "doi": a.get("doi") or b.get("doi") or "",
            "authors": authors,
            "citation_count": max((v for v in (a.get("citation_count"), b.get("citation_count"))
                                   if type(v) is int), default=None),
            "source_ids": ids, "sources": sources,
            "is_open_access": True if True in (a.get("is_open_access"), b.get("is_open_access"))
            else (False if a.get("is_open_access") is False and b.get("is_open_access") is False else None),
            "oa_status": a.get("oa_status") or b.get("oa_status") or "",
            "license": a.get("license") or b.get("license") or "",
            "pdf_link_status": "unverified_discovery" if best_pdf else "not_found",
            "full_text_verified": False,
        }
        ordered[key] = replace(
            original, abstract=max((original.abstract, item.abstract), key=len),
            publication_date=original.publication_date or item.publication_date,
            pdf_url=best_pdf, paper_metadata=merged,
            verified=original.verified or item.verified,
        )
    return list(ordered.values())


class SemanticScholarProvider:
    name = "semantic-scholar"

    def __init__(self, *, api_key: str | None = None,
                 fetch_json: Callable[..., dict] | None = None):
        self.key = api_key if api_key is not None else os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
        self.fetch_json = fetch_json or _fetch_json

    def search(self, query: str, *, limit: int = 10) -> list[Evidence]:
        return self.search_page(query, limit=min(limit, 25))["records"]

    def search_page(self, query: str, *, cursor: str | None = None,
                    limit: int = 100) -> dict[str, Any]:
        if not query.strip():
            return {"records": [], "next_cursor": None, "total_results": 0}
        if cursor not in (None, "*") and (not cursor.isdecimal() or len(cursor) > 5):
            raise PatentWorkflowError("Semantic Scholar 搜索页偏移量无效。")
        offset = int(cursor) if cursor not in (None, "*") else 0
        if offset >= 1000:
            return {"records": [], "next_cursor": None, "total_results": 1000}
        size = max(1, min(int(limit), 100, 1000-offset))
        params = {
            "query": query.strip()[:MAX_QUERY], "limit": size, "offset": offset,
            "fields": "title,abstract,year,publicationDate,authors,url,externalIds,citationCount,isOpenAccess,openAccessPdf",
        }
        _pace(self.name, 1.05)
        payload = self.fetch_json("https://api.semanticscholar.org/graph/v1/paper/search?"
                                  + parse.urlencode(params),
                                  headers={"x-api-key": self.key} if self.key else {})
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            raise PatentWorkflowError("Semantic Scholar 数据结构无效。")
        out: list[Evidence] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ids = row.get("externalIds") or {}
            if not isinstance(ids, dict):
                ids = {}
            oa_pdf = row.get("openAccessPdf") or {}
            paper_id = str(row.get("paperId") or "")
            item = _mk(self.name, title=row.get("title"), identifier=paper_id,
                       doi=ids.get("DOI"), url=row.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}",
                       abstract=row.get("abstract"),
                       date=row.get("publicationDate") or row.get("year"),
                       pdf=oa_pdf.get("url") if isinstance(oa_pdf, dict) else "",
                       authors=[a.get("name") for a in (row.get("authors") or []) if isinstance(a, dict)],
                       cited=row.get("citationCount"), is_oa=row.get("isOpenAccess"))
            if item:
                out.append(item)
        total = payload.get("total")
        end = offset + len(rows)
        next_cursor = str(end) if (
            len(rows) == size and end < 1000
            and (not isinstance(total, int) or end < total)
        ) else None
        return {"records": merge_paper_records(out),
                "next_cursor": next_cursor, "total_results": total}



class SemanticScholarBulkProvider(SemanticScholarProvider):
    """Official Academic Graph bulk API with opaque continuation token.

    Bulk API returns up to 1000 records; use max_documents in multiples of 1000
    to avoid dropping records and destroying exact checkpoint continuation.
    """
    name = "semantic-scholar-bulk"

    def search(self, query: str, *, limit: int = 10) -> list[Evidence]:
        raise PatentWorkflowError("Bulk 供应商仅允许 literature harvest 使用完整1000条分页。")

    def search_page(self, query: str, *, cursor: str | None = None,
                    limit: int = 1000) -> dict[str, Any]:
        if not query.strip():
            return {"records": [], "next_cursor": None, "total_results": 0}
        if limit != 1000:
            raise PatentWorkflowError("Semantic Scholar Bulk 每页必须保留全部1000条，防止游标丢失。")
        if cursor not in (None, "*") and (not isinstance(cursor, str) or len(cursor) > 4096):
            raise PatentWorkflowError("Semantic Scholar Bulk 游标无效。")
        params = {
            "query": query.strip()[:MAX_QUERY],
            "fields": "title,year,publicationDate,url,externalIds,citationCount,isOpenAccess,openAccessPdf",
        }
        if cursor not in (None, "*"):
            params["token"] = cursor
        _pace(self.name, 1.05)
        payload = self.fetch_json(
            "https://api.semanticscholar.org/graph/v1/paper/search/bulk?"
            + parse.urlencode(params),
            headers={"x-api-key": self.key} if self.key else {},
        )
        rows = payload.get("data", [])
        if not isinstance(rows, list) or len(rows) > 1000:
            raise PatentWorkflowError("Semantic Scholar Bulk 返回了不合法的文献分页。")
        out: list[Evidence] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ids = row.get("externalIds") or {}
            if not isinstance(ids, dict):
                ids = {}
            oa_pdf = row.get("openAccessPdf") or {}
            paper_id = str(row.get("paperId") or "")
            item = _mk(
                self.name, title=row.get("title"), identifier=paper_id,
                doi=ids.get("DOI"),
                url=row.get("url") or "https://www.semanticscholar.org/paper/" + paper_id,
                abstract=row.get("abstract"),
                date=row.get("publicationDate") or row.get("year"),
                pdf=oa_pdf.get("url") if isinstance(oa_pdf, dict) else "",
                cited=row.get("citationCount"), is_oa=row.get("isOpenAccess"),
            )
            if item:
                out.append(item)
        token = payload.get("token")
        if token is not None and (not isinstance(token, str) or len(token) > 4096):
            raise PatentWorkflowError("Semantic Scholar Bulk 返回不合法的后续游标。")
        if not rows:
            token = None
        return {"records": merge_paper_records(out),
                "next_cursor": token, "total_results": payload.get("total"),
                "consumed_records": len(rows)}


class ArxivProvider:
    name = "arxiv"

    def __init__(self, *, fetch_xml: Callable[..., bytes] | None = None):
        self.fetch_xml = fetch_xml or _fetch_xml

    def search(self, query: str, *, limit: int = 10) -> list[Evidence]:
        return self.search_page(query, limit=min(limit, 25))["records"]

    def search_page(self, query: str, *, cursor: str | None = None,
                    limit: int = 100) -> dict[str, Any]:
        if not query.strip():
            return {"records": [], "next_cursor": None, "total_results": 0}
        if cursor not in (None, "*") and (not cursor.isdecimal() or len(cursor) > 9):
            raise PatentWorkflowError("arXiv 分页起点无效。")
        start = int(cursor) if cursor not in (None, "*") else 0
        size = max(1, min(int(limit), 100))
        params = {"search_query": "all:" + query.strip()[:MAX_QUERY],
                  "start": start, "max_results": size}
        _pace(self.name, 3.1)
        raw = self.fetch_xml("https://export.arxiv.org/api/query?" + parse.urlencode(params))
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise PatentWorkflowError("arXiv Atom XML 无效。") from exc
        atom = "{http://www.w3.org/2005/Atom}"
        ax = "{http://arxiv.org/schemas/atom}"
        out: list[Evidence] = []
        for entry in root.findall(atom + "entry"):
            landing = _text(entry.find(atom + "id"))
            native = landing.rsplit("/", 1)[-1]
            native = re.sub(r"v\d+$", "", native)
            pdf = ""
            for link in entry.findall(atom + "link"):
                if link.get("type") == "application/pdf" or link.get("title") == "pdf":
                    pdf = _https(link.get("href"))
                    break
            authors = [_text(a.find(atom + "name")) for a in entry.findall(atom + "author")]
            item = _mk(self.name, title=_text(entry.find(atom + "title")),
                       identifier="arxiv:" + native, url=landing,
                       doi=_text(entry.find(ax + "doi")),
                       abstract=_text(entry.find(atom + "summary")),
                       date=_text(entry.find(atom + "published"))[:10],
                       pdf=pdf, authors=authors, is_oa=True)
            if item:
                out.append(item)
        namespace = "{http://a9.com/-/spec/opensearch/1.1/}"
        total_raw = _text(root.find(namespace + "totalResults"))
        total = int(total_raw) if total_raw.isdecimal() else None
        end = start + len(root.findall(atom + "entry"))
        next_cursor = str(end) if (
            len(out) == size and (total is None or end < total)
        ) else None
        return {"records": merge_paper_records(out),
                "next_cursor": next_cursor, "total_results": total}


class EuropePMCProvider:
    name = "europe-pmc"

    def __init__(self, *, fetch_json: Callable[..., dict] | None = None):
        self.fetch_json = fetch_json or _fetch_json

    def search(self, query: str, *, limit: int = 10) -> list[Evidence]:
        return self.search_page(query, limit=min(limit, 25))["records"]

    def search_page(self, query: str, *, cursor: str | None = None,
                    limit: int = 100) -> dict[str, Any]:
        if not query.strip():
            return {"records": [], "next_cursor": None, "total_results": 0}
        size = max(1, min(int(limit), 100))
        params = {"query": query.strip()[:MAX_QUERY], "format": "json",
                  "resultType": "core", "pageSize": size,
                  "cursorMark": cursor if cursor not in (None, "") else "*"}
        payload = self.fetch_json("https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
                                  + parse.urlencode(params))
        rows = (payload.get("resultList") or {}).get("result", [])
        if not isinstance(rows, list):
            raise PatentWorkflowError("Europe PMC 数据结构无效。")
        out: list[Evidence] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            fulltext = (row.get("fullTextUrlList") or {}).get("fullTextUrl", [])
            pdf = next((_https(x.get("url")) for x in fulltext
                        if isinstance(x, dict) and str(x.get("documentStyle", "")).lower() == "pdf"), "")
            authors = (row.get("authorList") or {}).get("author", [])
            native = str(row.get("source") or "MED") + ":" + str(row.get("id") or "")
            item = _mk(self.name, title=row.get("title"), identifier=native,
                       url="https://europepmc.org/article/" + parse.quote(str(row.get("source") or "MED")) +
                       "/" + parse.quote(str(row.get("id") or "")),
                       doi=row.get("doi"), abstract=row.get("abstractText"),
                       date=row.get("firstPublicationDate") or row.get("firstIndexDate") or row.get("pubYear"),
                       pdf=pdf,
                       authors=[x.get("fullName") for x in authors if isinstance(x, dict)],
                       is_oa=True if row.get("isOpenAccess") == "Y" else None,
                       license=row.get("license"))
            if item:
                out.append(item)
        next_cursor = payload.get("nextCursorMark")
        if not isinstance(next_cursor, str) or len(next_cursor) > 4096:
            next_cursor = None
        if len(rows) < size or next_cursor == params["cursorMark"]:
            next_cursor = None
        return {"records": merge_paper_records(out),
                "next_cursor": next_cursor, "total_results": payload.get("hitCount")}


class PubMedProvider:
    name = "pubmed"

    def __init__(self, *, api_key: str | None = None,
                 fetch_json: Callable[..., dict] | None = None,
                 fetch_xml: Callable[..., bytes] | None = None):
        self.key = api_key if api_key is not None else os.getenv("NCBI_API_KEY", "")
        self.contact_email = os.getenv("PATENT_CONTACT_EMAIL", "")
        self.fetch_json = fetch_json or _fetch_json
        self.fetch_xml = fetch_xml or _fetch_xml

    def search(self, query: str, *, limit: int = 10) -> list[Evidence]:
        return self.search_page(query, limit=min(limit, 25))["records"]

    def search_page(self, query: str, *, cursor: str | None = None,
                    limit: int = 100) -> dict[str, Any]:
        if not query.strip():
            return {"records": [], "next_cursor": None, "total_results": 0}
        if cursor not in (None, "*") and (not cursor.isdecimal() or len(cursor) > 9):
            raise PatentWorkflowError("PubMed 检索页偏移量无效。")
        start = int(cursor) if cursor not in (None, "*") else 0
        size = max(1, min(int(limit), 100))
        base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        params = {"db": "pubmed", "term": query.strip()[:MAX_QUERY],
                  "retmode": "json", "retstart": start, "retmax": size}
        if self.key:
            params["api_key"] = self.key
        if self.contact_email:
            params["email"] = self.contact_email
        # NCBI 官方单 IP 访问率限制；单进程内保守限速。
        _pace(self.name, 0.4 if not self.key else 0.12)
        discovery = (self.fetch_json(base + "esearch.fcgi?" + parse.urlencode(params))
                     .get("esearchresult") or {})
        ids = discovery.get("idlist", [])
        count_raw = discovery.get("count")
        total = int(count_raw) if str(count_raw).isdigit() else None
        if not isinstance(ids, list) or not ids:
            return {"records": [], "next_cursor": None, "total_results": total}
        identifiers = [str(x) for x in ids[:size] if str(x).isdigit()]
        if not identifiers:
            return {"records": [], "next_cursor": None, "total_results": total}
        detail = {"db": "pubmed", "id": ",".join(identifiers), "retmode": "xml"}
        if self.key:
            detail["api_key"] = self.key
        _pace(self.name, 0.4 if not self.key else 0.12)
        try:
            root = ET.fromstring(self.fetch_xml(base + "efetch.fcgi?" + parse.urlencode(detail)))
        except ET.ParseError as exc:
            raise PatentWorkflowError("PubMed XML 元数据无效。") from exc
        out: list[Evidence] = []
        for article in root.findall(".//PubmedArticle"):
            pmid = _text(article.find("./MedlineCitation/PMID"))
            if not pmid or not pmid.isdigit():
                continue
            title = _text(article.find("./MedlineCitation/Article/ArticleTitle"))
            abstr = " ".join(_text(x) for x in article.findall("./MedlineCitation/Article/Abstract/AbstractText"))
            doi = ""
            for identifier in article.findall("./PubmedData/ArticleIdList/ArticleId"):
                if identifier.attrib.get("IdType") == "doi":
                    doi = _text(identifier)
                    break
            authors = []
            for author in article.findall("./MedlineCitation/Article/AuthorList/Author"):
                full = " ".join(x for x in (_text(author.find("ForeName")),
                                             _text(author.find("LastName"))) if x)
                if full:
                    authors.append(full)
            date = _text(article.find("./MedlineCitation/Article/ArticleDate/Year"))
            if not date:
                date = _text(article.find("./MedlineCitation/Article/Journal/JournalIssue/PubDate/Year"))
            item = _mk(self.name, title=title, identifier="pmid:" + pmid,
                       url="https://pubmed.ncbi.nlm.nih.gov/" + pmid + "/",
                       doi=doi, abstract=abstr, date=date, authors=authors)
            if item:
                out.append(item)
        end = start + len(identifiers)
        next_cursor = str(end) if (
            len(identifiers) == size and (total is None or end < total)
        ) else None
        return {"records": merge_paper_records(out),
                "next_cursor": next_cursor, "total_results": total}


class COREProvider:
    name = "core"

    def __init__(self, *, api_key: str | None = None,
                 fetch_json: Callable[..., dict] | None = None):
        self.key = api_key if api_key is not None else os.getenv("CORE_API_KEY", "")
        if not self.key:
            raise PatentWorkflowError("CORE 使用前须配置 CORE_API_KEY 并确认数据许可。")
        self.fetch_json = fetch_json or _fetch_json

    def search(self, query: str, *, limit: int = 10) -> list[Evidence]:
        if not query.strip():
            return []
        url = "https://api.core.ac.uk/v3/search/works?" + parse.urlencode(
            {"q": query.strip()[:MAX_QUERY], "limit": max(1, min(limit, 25))})
        _pace(self.name, 2.1)
        payload = self.fetch_json(url, headers={"Authorization": "Bearer " + self.key})
        rows = payload.get("results", [])
        if not isinstance(rows, list):
            raise PatentWorkflowError("CORE 数据结构无效。")
        out: list[Evidence] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            native = str(row.get("id") or "")
            authors = row.get("authors") or []
            locations = row.get("sourceFulltextUrls") or []
            if isinstance(locations, str):
                locations = [locations]
            landing = next((_https(x) for x in locations if _https(x)), "") if isinstance(locations, list) else ""
            item = _mk(self.name, title=row.get("title"), identifier="core:" + native,
                       url=landing or "https://core.ac.uk/works/" + parse.quote(native),
                       doi=row.get("doi"), abstract=row.get("abstract"),
                       date=row.get("publishedDate") or row.get("yearPublished"),
                       pdf=row.get("downloadUrl"),
                       authors=[a.get("name") if isinstance(a, dict) else a for a in authors])
            if item:
                out.append(item)
        return merge_paper_records(out)


class LensProvider:
    name = "lens"

    def __init__(self, *, api_key: str | None = None,
                 fetch_json: Callable[..., dict] | None = None):
        self.key = api_key if api_key is not None else os.getenv("LENS_API_TOKEN", "")
        if not self.key:
            raise PatentWorkflowError("Lens 需要机构授权的 LENS_API_TOKEN。")
        self.fetch_json = fetch_json or _post_json

    def search(self, query: str, *, limit: int = 10) -> list[Evidence]:
        if not query.strip():
            return []
        # Lens Scholar API 采用 JSON DSL 的 POST 检索；许可证需事先明确。
        payload = self.fetch_json(
            "https://api.lens.org/scholarly/search",
            body={"query": query.strip()[:MAX_QUERY], "size": max(1, min(limit, 25))},
            headers={"Authorization": "Bearer " + self.key},
        )
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            raise PatentWorkflowError("Lens 数据结构无效。")
        out: list[Evidence] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ids = row.get("external_ids") or []
            doi = next((x.get("value", "") for x in ids
                        if isinstance(x, dict) and str(x.get("type", "")).lower() == "doi"), "")
            native = str(row.get("lens_id") or "")
            authors = row.get("authors") or []
            pdfs = (row.get("open_access") or {}).get("pdf_urls", []) if isinstance(row.get("open_access"), dict) else []
            item = _mk(self.name, title=row.get("title"), identifier="lens:" + native,
                       url="https://www.lens.org/lens/scholar/article/" + parse.quote(native),
                       doi=doi, abstract=row.get("abstract"), date=row.get("date_published") or row.get("year_published"),
                       pdf=pdfs[0] if pdfs else "",
                       authors=[a.get("display_name") or a.get("name") for a in authors if isinstance(a, dict)])
            if item:
                out.append(item)
        return merge_paper_records(out)


class UnpaywallEnricher:
    """仅使用 DOI 查询 OA PDF 位置；不是关键词检索引擎。"""
    name = "unpaywall"

    def __init__(self, *, contact_email: str | None = None,
                 fetch_json: Callable[..., dict] | None = None):
        self.email = contact_email if contact_email is not None else os.getenv("UNPAYWALL_EMAIL", "") or os.getenv("PATENT_CONTACT_EMAIL", "")
        if not self.email or "@" not in self.email:
            raise PatentWorkflowError("Unpaywall DOI 查询须配置合法的 UNPAYWALL_EMAIL。")
        self.fetch_json = fetch_json or _fetch_json

    def enrich(self, paper: Evidence) -> Evidence:
        doi = _doi(paper.paper_metadata.get("doi") or paper.publication)
        if paper.kind != "paper" or not doi or doi.startswith(("arxiv:", "pmid:", "core:", "lens:")):
            return paper
        url = "https://api.unpaywall.org/v2/" + parse.quote(doi, safe="/") + "?" + parse.urlencode({"email": self.email})
        payload = self.fetch_json(url)
        best = payload.get("best_oa_location") or {}
        if not isinstance(best, dict):
            best = {}
        pdf = _https(best.get("url_for_pdf"))
        meta = dict(paper.paper_metadata)
        # 已知 DOI 的补全操作不能暗中提升 PDF/全文的核验级别。
        meta["full_text_verified"] = False
        meta["sources"] = list(dict.fromkeys([*meta.get("sources", [paper.source]), self.name]))
        meta["is_open_access"] = payload.get("is_oa") if isinstance(payload.get("is_oa"), bool) else meta.get("is_open_access")
        meta["oa_status"] = str(payload.get("oa_status") or meta.get("oa_status") or "")
        meta["license"] = meta.get("license") or str(best.get("license") or "")
        meta["pdf_link_status"] = "unverified_discovery" if (pdf or paper.pdf_url) else "not_found"
        return replace(paper, pdf_url=paper.pdf_url or pdf, paper_metadata=meta)


def build_paper_providers(names: list[str] | None, *,
                          allow_paid: bool = False) -> tuple[list[Any], list[str]]:
    """统一配置入口；all 仅自动启用已授权的商业来源。"""
    from .papers import OpenAlexProvider, CrossrefProvider
    selected = list(names or ["openalex", "crossref", "semantic-scholar"])
    if "all" in selected:
        selected = list(SEARCH_SOURCES)
    providers: list[Any] = []
    warnings: list[str] = []
    types = {
        "openalex": OpenAlexProvider, "crossref": CrossrefProvider,
        "semantic-scholar": SemanticScholarProvider, "arxiv": ArxivProvider,
        "europe-pmc": EuropePMCProvider, "pubmed": PubMedProvider,
        "core": COREProvider, "lens": LensProvider,
    }
    for name in dict.fromkeys(selected):
        if name == "none":
            continue
        if name not in types:
            raise PatentWorkflowError(f"未知论文检索来源：{name}。")
        if name in PAID_OR_LICENSED:
            env = "CORE_API_KEY" if name == "core" else "LENS_API_TOKEN"
            if not allow_paid or not os.getenv(env):
                if "all" in (names or []):
                    warnings.append(f"{name} 尚未获得明确商业授权和凭证，已跳过。")
                    continue
                raise PatentWorkflowError(f"{name} 需要 --allow-paid-paper-apis 和 {env}。")
        providers.append(types[name]())
    return providers, warnings


def paper_source_catalog() -> list[dict[str, Any]]:
    """供 CLI/MCP/UI 展示平台能力，不暗示已验证实时联网成功。"""
    sources = []
    for name in SEARCH_SOURCES:
        required = {"core": "CORE_API_KEY", "lens": "LENS_API_TOKEN"}.get(name, "")
        sources.append({
            "id": name, "capability": "search", "description": SOURCE_DESCRIPTIONS[name],
            "commercial_license_gate": name in PAID_OR_LICENSED,
            "configured": (bool(os.getenv(required)) if required else True),
        })
    sources.append({
        "id": "unpaywall", "capability": "doi_enrich",
        "description": SOURCE_DESCRIPTIONS["unpaywall"],
        "commercial_license_gate": False,
        "configured": bool(os.getenv("UNPAYWALL_EMAIL") or os.getenv("PATENT_CONTACT_EMAIL")),
    })
    return sources
