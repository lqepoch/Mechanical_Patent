"""阶段 A 技术方案独立质检与企业真实评审验签。

检查技术表达/来源/工程反证，独立于阶段 B 的权利要求质量审核。
MCP 只读校验由外部审批系统颁发的双人评审结论，不签发批准。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
from typing import Any

from .core import Evidence, evidence_id, PatentWorkflowError
from .technical_brief import render_brief


_REVIEW_KEYS = (
    "case_id", "run_id", "candidate_id", "brief_sha256", "decision",
    "engineering_reviewer", "ip_reviewer", "engineering_finding",
    "patent_screening_finding", "signed_at",
)


def _load(path: Path) -> Any:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 300_000:
        raise PatentWorkflowError("缺少可信案卷数据或文件不符合安全限制。")
    return json.loads(path.read_text(encoding="utf-8"))


def _signed_review_valid(folder: Path, *, case_id: str, run_id: str,
                         candidate_id: str, brief_sha256: str) -> bool:
    path = folder / "08c_technical_review.json"
    secret = os.getenv("PATENT_TECHNICAL_REVIEW_KEY", "").encode("utf-8")
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 8192 or len(secret) < 32:
        return False
    try:
        obj = _load(path)
        if not isinstance(obj, dict) or set(obj) != set(_REVIEW_KEYS) | {"signature"}:
            return False
        if obj["decision"] != "approve_technical_brief":
            return False
        if any(not isinstance(obj[k], str) or not obj[k].strip() for k in _REVIEW_KEYS):
            return False
        if (obj["case_id"], obj["run_id"], obj["candidate_id"], obj["brief_sha256"]) != (
            case_id, run_id, candidate_id, brief_sha256
        ):
            return False
        if obj["engineering_reviewer"] == obj["ip_reviewer"]:
            return False
        timestamp = datetime.fromisoformat(obj["signed_at"])
        if timestamp.tzinfo is None:
            return False
        age = datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)
        if age < timedelta(minutes=-5) or age > timedelta(days=90):
            return False
        body = json.dumps(
            {k: obj[k] for k in _REVIEW_KEYS}, ensure_ascii=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        return hmac.compare_digest(obj["signature"], hmac.new(secret, body, sha256).hexdigest())
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return False


def inspect_brief(folder: Path, *, case_id: str, run_id: str,
                  candidate_id: str) -> dict[str, Any]:
    """工程阶段独立评估：证据不足可写研究稿，但不能标记技术结案。"""
    path = Path(folder)
    response = {
        "phase": "engineering", "case_id": case_id, "run_id": run_id,
        "candidate_id": candidate_id, "status": "revision_required",
        "engineering_review_approved": False,
        "filing_authorized": False, "conversion_authorized": False,
        "blockers": [], "warnings": [],
    }
    blockers = response["blockers"]
    try:
        brief = _load(path / "08a_technical_brief.json")
        documents = _load(path / "04_evidence.json")
        challenges = _load(path / "06_countersearch.json")
        engineering = _load(path / "07_engineering.json")
    except (PatentWorkflowError, ValueError, TypeError, OSError) as exc:
        blockers.append("案卷缺少技术方案或检索/反证/工程证据，无法结案。")
        response["error_type"] = type(exc).__name__
        return response
    records = documents.get("records", []) if isinstance(documents, dict) else []
    known: dict[str, Evidence] = {}
    for record in records:
        try:
            item = Evidence.from_dict(record)
            known[evidence_id(item)] = item
        except (ValueError, TypeError, KeyError):
            continue
    try:
        _, report = render_brief(brief, path, known_evidence=set(known))
    except (PatentWorkflowError, ValueError, TypeError):
        blockers.append("技术方案结构错误或证据编号不属于本案卷。")
        return response
    if brief["candidate_id"] != candidate_id:
        blockers.append("技术方案候选编号与目标不一致。")
    response["warnings"] = report["warnings"]
    if report["missing_figures"]:
        blockers.append("技术方案引用了未生成或失效的图片，请先补齐或明确删除。")
    items = brief.get("innovation_points", [])
    linked_patents = set()
    for idx, innovation in enumerate(items, 1):
        ids = innovation.get("evidence_ids", [])
        verified_patents = [
            known[k] for k in ids if k in known
            and known[k].kind == "patent" and known[k].verified and known[k].claims.strip()
        ]
        if not verified_patents:
            blockers.append(f"创新点{idx}没有来自核验过的专利权利要求正文的对照证据。")
        else:
            linked_patents.update(evidence_id(x) for x in verified_patents)
    valid_prior = any(
        item.get("evidence_id") in linked_patents
        for item in brief.get("prior_art", [])
        if isinstance(item, dict)
    )
    if not valid_prior:
        blockers.append("缺少本发明创新点关联的已核验原专利对照记录。")
    charts = challenges.get("claim_charts", []) if isinstance(challenges, dict) else []
    if not any(isinstance(c, dict) and c.get("candidate_id") == candidate_id
               and isinstance(c.get("evidence"), list) and c["evidence"]
               for c in charts):
        blockers.append("缺少当前候选发明的逐技术特征专利反证记录。")
    assessments = engineering.get("assessments", []) if isinstance(engineering, dict) else []
    if not any(isinstance(a, dict) and a.get("candidate_id") == candidate_id
               and a.get("physical_principle") and a.get("falsification_tests")
               for a in assessments):
        blockers.append("缺少当前候选发明的物理机理与可证伪试验记录。")
    if not blockers:
        signed = _signed_review_valid(
            path, case_id=case_id, run_id=run_id, candidate_id=candidate_id,
            brief_sha256=sha256((path / "08a_technical_brief.json").read_bytes()).hexdigest(),
        )
        if signed:
            response["status"] = "technical_complete"
            response["engineering_review_approved"] = True
        else:
            response["status"] = "awaiting_dual_human_review"
            response["warnings"].append("等待工程人员和知识产权审查人员签核；报告通过静态检查不代表法律上的新颖性确立。")
    return response
