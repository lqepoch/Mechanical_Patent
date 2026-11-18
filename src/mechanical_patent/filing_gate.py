"""独立审批后的专利申请文本转换门禁；不承担法律递交权限。

审批文件只由可信企业审批服务签名写入私有案卷，AI/MCP 没有签发接口。
使用每套部署的高熵密钥；生产需升级为可审计的 OIDC/PKI 组织签名。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
from typing import Any

from .core import PatentWorkflowError


def _payload(approval: dict[str, Any]) -> bytes:
    required = {"case_id", "run_id", "candidate_id", "brief_sha256",
                "decision", "approved_by", "approved_at"}
    if set(approval) - required - {"signature"} or not required.issubset(approval):
        raise PatentWorkflowError("转换审批记录字段缺失或出现未经授权的字段。")
    return json.dumps(
        {key: approval[key] for key in sorted(required)},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")


def conversion_status(folder: Path, case_id: str, run_id: str,
                      candidate_id: str) -> dict[str, Any]:
    """无密钥、无签名、无当前技术稿时关闭转换；不泄露密钥信息。"""
    path = Path(folder) / "08b_conversion_approval.json"
    brief = Path(folder) / "08a_technical_brief.json"
    denied = {"conversion_authorized": False, "filing_authorized": False}
    if path.is_symlink() or brief.is_symlink() or not path.is_file() or not brief.is_file():
        return {**denied, "reason": "缺少可信审批记录或当前技术方案。"}
    secret = os.getenv("PATENT_CONVERSION_APPROVAL_KEY", "").encode("utf-8")
    if len(secret) < 32:
        return {**denied, "reason": "审批验签密钥不可用；拒绝进入申请文本转换。"}
    try:
        if path.stat().st_size > 8192:
            raise ValueError("oversized")
        approval = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(approval, dict):
            raise ValueError("invalid")
        body = _payload(approval)
        if approval["decision"] != "convert_to_application" or not all(
            isinstance(approval[k], str) and approval[k].strip()
            for k in ("approved_by", "approved_at", "signature")
        ):
            raise ValueError("wrong decision")
        if (approval["case_id"], approval["run_id"], approval["candidate_id"]) != (
            case_id, run_id, candidate_id
        ):
            raise ValueError("case mismatch")
        digest = sha256(brief.read_bytes()).hexdigest()
        if approval["brief_sha256"] != digest:
            raise ValueError("stale document")
        stamp = datetime.fromisoformat(approval["approved_at"])
        if stamp.tzinfo is None:
            raise ValueError("no timezone")
        delay = datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)
        if delay < timedelta(minutes=-5) or delay > timedelta(days=90):
            raise ValueError("approval expired")
        signature = hmac.new(secret, body, sha256).hexdigest()
        if not hmac.compare_digest(approval["signature"], signature):
            raise ValueError("bad signature")
    except (OSError, ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return {**denied, "reason": "审批签名、身份、日期或文档哈希校验失败。"}
    return {
        "conversion_authorized": True, "filing_authorized": False,
        "approved_by": approval["approved_by"], "approved_at": approval["approved_at"],
        "brief_sha256": approval["brief_sha256"],
    }


def require_conversion_approval(folder: Path, case_id: str, run_id: str,
                                candidate_id: str) -> None:
    status = conversion_status(folder, case_id, run_id, candidate_id)
    if not status["conversion_authorized"]:
        raise PatentWorkflowError("申请文件转换受阻：" + status["reason"])
