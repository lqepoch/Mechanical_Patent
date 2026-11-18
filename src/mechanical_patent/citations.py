"""基于 OpenCitations Index v2 的开放论文引证网络。

面向当前 ChatGPT/Codex Agent 的数据工具。输入公开 DOI，查询直接参考
文献与被引文献，保存机器可核验的引证边、来源、查询时间与未覆盖范围。

OpenCitations 的 DOI 引证关系不代表论文科学结论正确或专利创造性成立。
"""
from __future__ import annotations

from datetime import datetime
import json
import re
from pathlib import Path
from typing import Any, Callable
from urllib import error, parse, request

from .core import PatentWorkflowError, save_json, utc_now

API_BASE = "https://api.opencitations.net/index/v2"
USER_AGENT = "MechanicalPatent/0.3 (scientific citation research)"
MAX_REPLY_BYTES = 2_000_000
MAX_SEEDS = 8
MAX_EDGES_PER_SEED = 50
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/[^\s?#<>]{1,230}$", re.I)
DOI_IN_PIDS = re.compile(r"(?:^|\s)doi:(10\.\d{4,9}/[^\s]+)", re.I)


def normalize_doi(value: str) -> str:
    """独立校验公开 DOI，严禁把任意 URL 或主机名当作 API 路径。"""
    if not isinstance(value, str):
        raise PatentWorkflowError("DOI 必须是字符串。")
    doi = value.strip()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.I)
    if doi.lower().startswith("doi:"):
        doi = doi[4:]
    doi = parse.unquote(doi).strip().lower()
    if not DOI_PATTERN.fullmatch(doi):
        raise PatentWorkflowError("无效 DOI：必须为 10.<注册号>/<后缀> 格式。")
    return doi


def dois_in_pid_field(value: str) -> list[str]:
    """OpenCitations v2 PID 字段可同时包含 OMID、DOI 和 OpenAlex 编号。"""
    if not isinstance(value, str):
        return []
    matches = []
    for hit in DOI_IN_PIDS.finditer(value):
        try:
            doi = normalize_doi(hit.group(1).rstrip(",;"))
        except PatentWorkflowError:
            continue
        if doi not in matches:
            matches.append(doi)
    if not matches:
        try:
            return [normalize_doi(value)]
        except PatentWorkflowError:
            return []
    return matches


def _http_fetch_json(url: str, *, timeout: int = 25) -> list[dict[str, Any]]:
    """固定 HTTPS API 域名，限制响应大小；不调用浏览器、模型或爬虫。"""
    req = request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json",
    })
    try:
        with request.urlopen(req, timeout=timeout) as response:
            if response.geturl() != url:
                raise PatentWorkflowError("引证接口发生重定向，已终止请求。")
            body = response.read(MAX_REPLY_BYTES + 1)
        if len(body) > MAX_REPLY_BYTES:
            raise PatentWorkflowError("引证服务响应超过单次预算。")
        data = json.loads(body)
        if not isinstance(data, list):
            raise PatentWorkflowError("OpenCitations 返回非列表格式。")
        return data
    except error.HTTPError as exc:
        raise PatentWorkflowError(
            f"OpenCitations 请求失败 HTTP {exc.code}，请核对服务额度、查询或权限。"
        ) from exc
    except (error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise PatentWorkflowError("OpenCitations 服务不可用或返回无效 JSON。") from exc


class OpenCitationsClient:
    name = "opencitations-index-v2"

    def __init__(self, *, fetch_json: Callable[..., list[dict[str, Any]]] | None = None):
        self.fetch_json = fetch_json or _http_fetch_json

    def links(self, doi: str, *, direction: str, limit: int = MAX_EDGES_PER_SEED) -> dict[str, Any]:
        key = normalize_doi(doi)
        if direction not in {"references", "citations"}:
            raise PatentWorkflowError("引证方向只接受 references 或 citations。")
        if not 1 <= limit <= MAX_EDGES_PER_SEED:
            raise PatentWorkflowError("单 DOI 引证返回上限超出允许范围。")
        identifier = parse.quote("doi:" + key, safe=":/")
        url = f"{API_BASE}/{direction}/{identifier}"
        raw = self.fetch_json(url)
        if not isinstance(raw, list):
            raise PatentWorkflowError("引证 API 数据结构异常。")
        edges: list[dict[str, Any]] = []
        duplicates: set[tuple[str, str]] = set()
        skipped = 0
        for entry in raw:
            if len(edges) >= limit:
                break
            if not isinstance(entry, dict):
                skipped += 1
                continue
            citing = dois_in_pid_field(str(entry.get("citing") or ""))
            cited = dois_in_pid_field(str(entry.get("cited") or ""))
            if not citing or not cited:
                skipped += 1
                continue
            # 主查询端必须准确匹配；不能把不相关的三方引证挂到种子论文。
            if direction == "references" and key not in citing:
                skipped += 1
                continue
            if direction == "citations" and key not in cited:
                skipped += 1
                continue
            for from_doi in citing[:2]:
                for to_doi in cited[:2]:
                    pair = (from_doi, to_doi)
                    if pair in duplicates or len(edges) >= limit:
                        continue
                    duplicates.add(pair)
                    edges.append({
                        "citing_doi": from_doi, "cited_doi": to_doi,
                        "oci": str(entry.get("oci") or "")[:120],
                        "citing_publication_date": str(entry.get("creation") or "")[:30],
                        "source": self.name,
                        "record_type": "provider_reported_citation",
                    })
        return {
            "doi": key, "direction": direction, "url": url, "edges": edges,
            "returned_rows": len(raw), "skipped_rows": skipped,
            "truncated": len(raw) > limit,
        }


def create_citation_graph(
    seed_dois: list[str], *, client: OpenCitationsClient | None = None,
    direction: str = "both", max_links: int = 25,
) -> dict[str, Any]:
    """边界明确的一跳引用图；用于寻找跨领域技术线索，而非自动权利判断。"""
    if direction not in {"references", "citations", "both"}:
        raise PatentWorkflowError("无效的引证图方向。")
    if not 1 <= max_links <= MAX_EDGES_PER_SEED:
        raise PatentWorkflowError("单次 DOI 引证预算超限。")
    if not isinstance(seed_dois, list) or not 1 <= len(seed_dois) <= MAX_SEEDS:
        raise PatentWorkflowError("一次只能查询 1 至 8 篇公开 DOI。")
    seeds = list(dict.fromkeys(normalize_doi(raw) for raw in seed_dois))
    provider = client or OpenCitationsClient()
    directions = ("references", "citations") if direction == "both" else (direction,)
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    executed: list[dict[str, Any]] = []
    errors: list[str] = []
    for doi in seeds:
        for way in directions:
            try:
                result = provider.links(doi, direction=way, limit=max_links)
                executed.append({
                    "seed_doi": doi, "direction": way, "url": result["url"],
                    "returned_rows": result["returned_rows"],
                    "skipped_rows": result["skipped_rows"],
                    "truncated": result["truncated"],
                })
                for edge in result["edges"]:
                    pair = (edge["citing_doi"], edge["cited_doi"])
                    if pair not in seen:
                        seen.add(pair)
                        edges.append(edge)
            except PatentWorkflowError as exc:
                errors.append(f"{doi} / {way}: {exc}")
    nodes = sorted(set(seeds) | {
        edge[side] for edge in edges for side in ("citing_doi", "cited_doi")
    })
    return {
        "schema_version": "1.0",
        "provider": provider.name,
        "retrieved_at": utc_now(),
        "seed_dois": seeds,
        "direction": direction,
        "nodes": [{"doi": doi, "is_seed": doi in seeds} for doi in nodes],
        "edges": edges,
        "queries": executed,
        "errors": errors,
        "status": "partial" if errors else ("complete_within_query_limits" if executed else "unavailable"),
        "limitations": [
            "引证接口并不证明引用关系已覆盖全世界或所有出版物。",
            "仅保存提供方报告的 DOI 引用方向；实际论文标题、正文和理论仍待核验。",
            "引证共现、引用次数及技术相似度不能证明专利新颖性、创造性或 FTO。",
            "默认只查询一跳引用关系，不自动扩大到无穷多轮。",
        ],
    }


def export_citation_graph(
    seed_dois: list[str], output: Path, *, client: OpenCitationsClient | None = None,
    direction: str = "both", max_links: int = 25,
) -> dict[str, Any]:
    graph = create_citation_graph(seed_dois, client=client, direction=direction, max_links=max_links)
    save_json(output, graph)
    return {
        "output": str(output), "edges": len(graph["edges"]), "nodes": len(graph["nodes"]),
        "errors": graph["errors"], "status": graph["status"],
    }
