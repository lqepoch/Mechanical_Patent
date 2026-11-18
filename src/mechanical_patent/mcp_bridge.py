"""外部行业 MCP 专利数据的统一证据导入契约。

ChatGPT/Codex 直接调用已获用户授权的 Patent Client Agents/patentkit 工具。
本模块验证保存的结构化工具结果、记录来源哈希，不替代调用者完成登录，
也不把外部导入数据自动提升为官方核验。
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .core import Evidence, PatentWorkflowError, deduplicate, save_json, utc_now

MAX_INPUT_BYTES = 10_000_000
MAX_RECORDS = 500
SUPPORTED_TOOL_FAMILIES = frozenset({"patent-client-agents", "patentkit"})


def normalize_mcp_patents(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PatentWorkflowError("MCP 证据包必须为 JSON 对象。")
    tool_family = str(payload.get("tool_family") or "").strip()
    tool_name = str(payload.get("tool_name") or "").strip()
    if tool_family not in SUPPORTED_TOOL_FAMILIES or not tool_name or len(tool_name) > 120:
        raise PatentWorkflowError("外部专利 MCP 工具来源缺失或不在许可证清单。")
    if payload.get("data_access_authorized") is not True:
        raise PatentWorkflowError("需确认已获该专利数据服务的访问和保存授权。")
    if payload.get("transport") != "structured_api":
        raise PatentWorkflowError("仅接受结构化数据工具结果；网页 HTML 应由 Crawl4AI 处理。")
    records = payload.get("records")
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_RECORDS:
        raise PatentWorkflowError("专利 MCP 工具结果数量非法或超出归档限制。")
    normalized: list[Evidence] = []
    for idx, entry in enumerate(records, start=1):
        if not isinstance(entry, dict):
            raise PatentWorkflowError(f"第 {idx} 条 MCP 证据格式错误。")
        number = str(entry.get("publication") or "").strip()
        title = str(entry.get("title") or "").strip()
        original_url = str(entry.get("original_url") or "").strip()
        u = urlsplit(original_url)
        if (not number or not title or u.scheme != "https" or not u.hostname
                or u.username or u.password or len(original_url) > 2048):
            raise PatentWorkflowError(f"第 {idx} 条专利缺少真实公开号、标题或安全来源 URL。")
        abstract = str(entry.get("abstract") or "")[:20000]
        claims = str(entry.get("claims") or "")[:50000]
        normalized.append(Evidence(
            publication=number, title=title, url=original_url,
            source=f"mcp:{tool_family}/{tool_name}",
            retrieved_at=utc_now(),
            abstract=abstract, claims=claims,
            publication_date=str(entry.get("publication_date") or "")[:40],
            jurisdiction=str(entry.get("jurisdiction") or "")[:20],
            kind="patent",
            verified=False,
        ))
    return {
        "records": [r.to_dict() for r in deduplicate(normalized)],
        "origin": {
            "tool_family": tool_family, "tool_name": tool_name,
            "transport": payload["transport"],
            "data_rights_declared": True,
            "structured_payload_sha256": sha256(
                json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "imported_at": utc_now(),
        },
        "review_status": "awaiting_independent_source_verification",
        "note": (
            "结构化 MCP 导入只能建立候选检索证据；须打开专利官方/原始 PDF "
            "核对公开号、权利要求及公开日期后才能完成核验。"
        ),
    }


def import_mcp_json(input_file: Path, output_file: Path) -> dict[str, Any]:
    path = Path(input_file)
    if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise PatentWorkflowError("MCP 输入不存在或超过资料大小预算。")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise PatentWorkflowError("无法读取真实 MCP 工具返回的结构化 JSON。") from exc
    result = normalize_mcp_patents(payload)
    save_json(Path(output_file), result)
    return {
        "output": str(Path(output_file)),
        "records": len(result["records"]),
        "status": result["review_status"],
        "payload_sha256": result["origin"]["structured_payload_sha256"],
    }
