"""双源文献—候选发明—反证—工程—权利要求的确定性质量门禁。

静态检查无法判断法律创造性、技术实现真实性或发明人实际贡献。
需要真人机械工程师和专利专业人员独立签核。
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .audit import append_audit_event, verify_audit_chain
from .core import Evidence, PatentWorkflowError, evidence_id, save_json, utc_now, validate_draft


def _load(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("需要 JSON 对象")
        return obj
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"案卷文件不可用：{path.name}（{exc}）")
        return {}


def _records(data: dict[str, Any], kind: str, errors: list[str]) -> list[Evidence]:
    raw = data.get("records", [])
    if not isinstance(raw, list):
        errors.append(f"{kind} 记录格式错误。")
        return []
    output: list[Evidence] = []
    for i, item in enumerate(raw):
        try:
            if not isinstance(item, dict):
                raise ValueError("需要对象")
            record = Evidence.from_dict(item)
            if record.kind != kind:
                raise ValueError(f"文献类别为 {record.kind}，预期 {kind}")
            output.append(record)
        except (TypeError, ValueError, KeyError) as exc:
            errors.append(f"{kind} 第 {i + 1} 项证据无效：{exc}")
    return output


def _check_quote(reference: Evidence, quote: str) -> bool:
    source_text = " ".join((reference.abstract + " " + reference.claims).split())
    return bool(quote and " ".join(quote.split()) in source_text)


def inspect_research_case(case_dir: Path) -> dict[str, Any]:
    """只读分析案卷，输出全程证据可核验性与结构性风险。"""
    path = Path(case_dir)
    errors: list[str] = []
    notes: list[str] = []
    intake = _load(path / "00_intake.json", errors)
    plan = _load(path / "01_search_plan.json", errors)
    patent_data = _load(path / "02_patents.json", errors)
    paper_data = _load(path / "03_papers.json", errors)
    candidates_data = _load(path / "05_inventions.json", errors)
    challenges_data = _load(path / "06_countersearch.json", errors)
    engineering_data = _load(path / "07_engineering.json", errors)
    application_data = _load(path / "08_application.json", errors)
    patents = _records(patent_data, "patent", errors)
    papers = _records(paper_data, "paper", errors)
    patent_index = {evidence_id(item): item for item in patents}
    paper_index = {evidence_id(item): item for item in papers}
    source_index = {**patent_index, **paper_index}

    if intake.get("workflow") != "agent_native":
        errors.append("案卷缺少原生 AI 客户端工作流标记。")
    for field, kind in (("patent_queries", "专利"), ("paper_queries", "论文")):
        values = plan.get(field, [])
        if not isinstance(values, list) or not values:
            errors.append(f"缺少已执行的{kind}检索词，双源检索未形成完整证据链。")
    if not any(p.verified for p in patents):
        errors.append("没有从真实专利数据接口核实的专利文献。")
    if not any(p.verified and p.claims.strip() for p in patents):
        errors.append("缺少真实核实的权利要求正文；当前只能开展摘要初筛。")
    if not any(p.verified for p in papers):
        errors.append("没有从学术数据接口核实的论文元数据。")
    if papers and not any(p.abstract.strip() for p in papers):
        notes.append("检索到了论文元数据，但缺少可分析的摘要；获取合法全文后复核。")
    if paper_data.get("full_text_verified", 0) == 0:
        notes.append("论文全文尚未核实，学术现有技术判断限于已取得的摘要或元数据。")
    if patent_data.get("coverage", {}).get("provider_errors") or patent_data.get("provider_errors"):
        notes.append("专利数据供应方存在访问失败或缺失记录，请核对覆盖日志。")

    candidates = candidates_data.get("candidates", [])
    if not isinstance(candidates, list) or not candidates:
        errors.append("尚无已结构化的创新候选方案。")
        candidates = []
    candidate_ids: set[str] = set()
    for idx, item in enumerate(candidates, 1):
        if not isinstance(item, dict):
            errors.append(f"候选 {idx} 数据格式错误。")
            continue
        code = str(item.get("id", "")).strip()
        if not code or code in candidate_ids:
            errors.append(f"候选 {idx} 缺少唯一的发明编号。")
        candidate_ids.add(code)
        for field, label in (
            ("title", "标题"), ("mechanism", "具体作用机理"),
            ("enabling_details", "使本领域技术人员可实施的细节"),
        ):
            if not str(item.get(field, "")).strip():
                errors.append(f"候选 {idx} 缺少{label}。")
        features = item.get("distinguishing_features", [])
        if not isinstance(features, list) or not features:
            errors.append(f"候选 {idx} 没有明确区别技术特征。")
        ids = item.get("evidence_ids", [])
        if not isinstance(ids, list) or not ids:
            errors.append(f"候选 {idx} 未关联专利或论文证据。")
        else:
            for source in ids:
                if source not in source_index:
                    errors.append(f"候选 {idx} 引用了未入库证据：{source}")

    charts = challenges_data.get("claim_charts", [])
    if not isinstance(charts, list) or not charts:
        errors.append("未形成逐技术特征的独立反证对照表。")
        charts = []
    checked_quotes = 0
    for idx, chart in enumerate(charts, 1):
        if not isinstance(chart, dict):
            errors.append(f"反证表第 {idx} 项格式错误。")
            continue
        code = str(chart.get("candidate_id", ""))
        if code not in candidate_ids:
            errors.append(f"反证表第 {idx} 项未关联有效候选发明。")
        if not str(chart.get("feature", "")).strip():
            errors.append(f"反证表第 {idx} 项缺少被比较技术特征。")
        anchors = chart.get("evidence", [])
        if not isinstance(anchors, list) or not anchors:
            errors.append(f"反证表第 {idx} 项没有原始文献证据锚点。")
            continue
        for anchor in anchors:
            if not isinstance(anchor, dict):
                errors.append(f"反证表第 {idx} 项证据格式错误。")
                continue
            source_id = str(anchor.get("evidence_id", ""))
            record = source_index.get(source_id)
            quote = str(anchor.get("quote", ""))
            if record is None:
                errors.append(f"反证表第 {idx} 项引用不存在的文献：{source_id}")
            elif not _check_quote(record, quote):
                errors.append(f"反证表第 {idx} 项原文未在存档摘要/权利要求中找到：{source_id}")
            else:
                checked_quotes += 1

    assessments = engineering_data.get("assessments")
    if not isinstance(assessments, list):
        assessments = []
        errors.append("缺少独立工程论证的候选逐项评审记录。")
    examined_ids: set[str] = set()
    for idx, item in enumerate(assessments, 1):
        if not isinstance(item, dict):
            errors.append(f"工程论证第 {idx} 项格式错误。")
            continue
        code = str(item.get("candidate_id", ""))
        if code not in candidate_ids:
            errors.append(f"工程论证第 {idx} 项未关联有效候选发明。")
        examined_ids.add(code)
        for key, label in (
            ("physical_principle", "物理原理"),
            ("equations_and_units", "公式及单位"),
            ("assumptions", "假设与边界"),
            ("failure_modes", "失效模式"),
            ("falsification_tests", "可证伪验证计划"),
        ):
            value = item.get(key)
            if not value:
                errors.append(f"工程论证第 {idx} 项缺少{label}。")
        state = item.get("verification_status")
        if state not in {"hypothesis_only", "analytical_estimate", "simulated", "bench_tested"}:
            errors.append(f"工程论证第 {idx} 项验证状态无效。")
        if state in {"simulated", "bench_tested"}:
            proof = item.get("artifact_sha256")
            if not isinstance(proof, str) or len(proof) != 64:
                errors.append(f"工程论证第 {idx} 项宣称已仿真/实测，却没有可核验的文件哈希。")
            notes.append("仿真或实测记录仍需由真实工程师复核原始文件、仪器和方法。")
    for code in candidate_ids - examined_ids:
        if code:
            errors.append(f"候选 {code} 缺少独立工程论证。")

    chosen = application_data.get("selected_candidate_id")
    if chosen not in candidate_ids:
        errors.append("申请文件尚未选定有效的候选发明编号。")
    draft = application_data.get("draft")
    if not isinstance(draft, dict):
        errors.append("尚无完整的中国发明专利申请草稿。")
    else:
        selected = next((c for c in candidates if isinstance(c, dict) and c.get("id") == chosen), {})
        errors.extend(validate_draft(draft, patents, selected))

    audit = verify_audit_chain(path)
    if not audit["valid"]:
        errors.extend("审计链：" + item for item in audit["errors"])
    counts = {
        "patent_records": len(patents),
        "verified_patent_records": sum(p.verified for p in patents),
        "patent_claims_available": sum(bool(p.claims.strip()) and p.verified for p in patents),
        "paper_records": len(papers),
        "verified_paper_records": sum(p.verified for p in papers),
        "invention_candidates": len(candidates),
        "claim_chart_items": len(charts),
        "source_anchored_quotes": checked_quotes,
        "engineering_assessments": len(assessments),
    }
    return {
        "status": "research_incomplete" if errors else "needs_human_review",
        "filing_authorized": False,
        "human_signoff": False,
        "issues": list(dict.fromkeys(errors)),
        "notices": list(dict.fromkeys(notes)),
        "metrics": counts,
        "audit_chain": audit,
        "legal_boundary": "本检查仅验证案卷结构和部分原文匹配，不能证明新颖性、创造性、FTO或可实施性。",
    }


def audit_research_case(case_dir: Path) -> dict[str, Any]:
    """保存质量报告及文件完整性摘要，不替代人工审批。"""
    path = Path(case_dir)
    report = inspect_research_case(path)
    save_json(path / "09_quality_gate.json", report)
    save_json(path / "10_enterprise_quality.json", report)
    append_audit_event(
        path, stage="质量审核", action="执行确定性质量检查", actor="系统质检工具",
        role="系统", payload={"status": report["status"], "issue_count": len(report["issues"])}
    )
    # 哈希清单涵盖机器产物与已存在的人工材料，排除自身以免形成循环引用。
    hashes = {}
    for file in sorted(path.glob("*.json")):
        if file.name != "manifest.json":
            hashes[file.name] = sha256(file.read_bytes()).hexdigest()
    save_json(path / "manifest.json", {
        "created_at": utc_now(),
        "sha256": hashes,
        "audit_chain_head": verify_audit_chain(path)["head_sha256"],
        "note": "完整性哈希需要外部不可改写存储或电子签名才具有更强的抗篡改能力。",
    })
    return report
