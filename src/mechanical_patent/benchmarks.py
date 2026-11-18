"""企业专利检索的可复现实验评测（模型无关、零外部依赖）。

借鉴 PatSnap Patent Bench 的公开评测理念，但不复制其非商业数据。
输入必须是由企业有权使用、带来源/授权声明的自有标注样本。
严格模式将所有未返回结果的样本计为零，不选择性剔除失败样本。
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from .core import PatentWorkflowError, save_json, utc_now

MAX_FILE_BYTES = 25_000_000
MAX_CASES = 20_000
MAX_RANKED = 500
K_VALUES = (1, 5, 10, 20)

# 这里检验的是使用许可的最小机器规则，不代替企业法务逐项审查。
INCOMPATIBLE_LICENSE_MARKERS = ("NC", "NONCOMMERCIAL", "NON-COMMERCIAL", "UNKNOWN", "NO-LICENSE")
ALLOWED_LICENSES = {
    "INTERNAL-OWNED", "MIT", "APACHE-2.0", "CC0-1.0", "CC-BY-4.0",
}


def normalize_publication(value: str) -> str:
    """对专利公开号只做字母数字标准化，保留 A/B1/B2 版本以便追溯。"""
    if not isinstance(value, str):
        raise PatentWorkflowError("专利公开号必须是字符串。")
    result = re.sub(r"[^A-Z0-9]", "", value.upper())
    if not 4 <= len(result) <= 64:
        raise PatentWorkflowError("无效的专利公开号。")
    return result


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not Path(path).is_file() or Path(path).stat().st_size > MAX_FILE_BYTES:
        raise PatentWorkflowError("评测文件不存在或超过允许的文件预算。")
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            if len(rows) >= MAX_CASES:
                raise PatentWorkflowError("超出最大评测案例数量。")
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PatentWorkflowError(f"评测文件第 {line_number} 行不是合法 JSON。") from exc
            if not isinstance(item, dict):
                raise PatentWorkflowError(f"评测文件第 {line_number} 行必须为对象。")
            rows.append(item)
    if not rows:
        raise PatentWorkflowError("评测文件不能没有案例。")
    return rows


def validate_dataset_rights(manifest: dict[str, Any]) -> dict[str, str]:
    """企业模式默认拒绝 CC BY-NC、未知许可和缺少来源的评测资料。"""
    if not isinstance(manifest, dict):
        raise PatentWorkflowError("必须提供授权声明对象。")
    source = str(manifest.get("source_url") or "").strip()
    license_text = str(manifest.get("license") or "").strip().upper()
    rights = str(manifest.get("rights_holder") or "").strip()
    approved = manifest.get("commercial_evaluation_approved")
    if not source.startswith("https://") or not rights or approved is not True:
        raise PatentWorkflowError("评测集必须记录可访问来源、权利人和企业用途批准结果。")
    if any(item in license_text for item in INCOMPATIBLE_LICENSE_MARKERS):
        raise PatentWorkflowError("评测集许可含非商业或不明确条件，禁止在企业评测中使用。")
    if license_text not in ALLOWED_LICENSES:
        raise PatentWorkflowError("评测数据许可未纳入企业许可白名单，需法务先行核实。")
    return {"license": license_text, "rights_holder": rights, "source_url": source}


def _groups(case: dict[str, Any]) -> list[set[str]]:
    """每组专利视为一个真值家族，可命中该组任意一个公开文本。"""
    raw = case.get("relevant_families")
    if raw is None:
        ids = case.get("relevant_publications", [])
        if not isinstance(ids, list):
            raise PatentWorkflowError("真值公开号必须为列表。")
        raw = [[item] for item in ids]
    if not isinstance(raw, list) or not raw:
        raise PatentWorkflowError("每个检索案例都必须包含真实的专利真值。")
    result: list[set[str]] = []
    all_aliases: set[str] = set()
    for group in raw:
        if not isinstance(group, list) or not group:
            raise PatentWorkflowError("专利同族真值必须为非空列表。")
        normalized = {normalize_publication(x) for x in group}
        if all_aliases.intersection(normalized):
            raise PatentWorkflowError("同一公开号不能同时出现在两个不同真值家族。")
        all_aliases.update(normalized)
        result.append(normalized)
    return result


def _predictions(rows: list[dict[str, Any]], known: set[str]) -> dict[str, list[str]]:
    results = {}
    for row in rows:
        case_id = str(row.get("case_id") or "").strip()
        if case_id not in known or case_id in results:
            raise PatentWorkflowError("预测结果存在未知、重复或缺失的案例编号。")
        ranked = row.get("ranked_publications")
        if not isinstance(ranked, list) or len(ranked) > MAX_RANKED:
            raise PatentWorkflowError("检索排序结果必须为限长列表。")
        unique: list[str] = []
        for item in ranked:
            number = normalize_publication(item)
            if number not in unique:
                unique.append(number)
        results[case_id] = unique
    return results


def evaluate_retrieval(
    ground_truth: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    license_manifest: dict[str, Any],
) -> dict[str, Any]:
    rights = validate_dataset_rights(license_manifest)
    cases = {}
    for row in ground_truth:
        cid = str(row.get("case_id") or "").strip()
        if not cid or len(cid) > 128 or cid in cases:
            raise PatentWorkflowError("真值案例编号缺失、重复或过长。")
        cases[cid] = _groups(row)
    if not cases:
        raise PatentWorkflowError("评测案例不可为空。")
    predicted = _predictions(predictions, set(cases))
    by_case = []
    totals = {f"hit@{k}": 0.0 for k in K_VALUES}
    totals.update({f"recall@{k}": 0.0 for k in K_VALUES})
    totals.update({f"mrr@{k}": 0.0 for k in K_VALUES})

    for cid, groups in cases.items():
        ranked = predicted.get(cid, [])
        result = {"case_id": cid, "has_prediction": cid in predicted, "relevant_families": len(groups)}
        for k in K_VALUES:
            subset = ranked[:k]
            covered = [i for i, family in enumerate(groups) if any(p in family for p in subset)]
            hits = float(bool(covered))
            recall = len(covered) / len(groups)
            rank = next((idx for idx, p in enumerate(subset, 1)
                         if any(p in family for family in groups)), None)
            reciprocal = 1.0 / rank if rank else 0.0
            result.update({f"hit@{k}": hits, f"recall@{k}": recall,
                           f"mrr@{k}": reciprocal})
            totals[f"hit@{k}"] += hits
            totals[f"recall@{k}"] += recall
            totals[f"mrr@{k}"] += reciprocal
        by_case.append(result)

    return {
        "schema_version": "1.0",
        "evaluated_at": utc_now(),
        "dataset": rights,
        "mode": "strict_all_cases",
        "case_count": len(cases),
        "prediction_count": len(predicted),
        "missing_predictions_count": len(cases) - len(predicted),
        "metrics": {key: round(val / len(cases), 6) for key, val in totals.items()},
        "cases": by_case,
        "limitations": [
            "指标仅衡量给定标注集的检索召回与排序，不能证明全球专利查全。",
            "指标不能证明法律创造性、FTO、权利要求支持或实际授权可能性。",
            "数据许可仅进行了最低限度的自动检查，企业使用需要人工审核。",
        ],
    }


def run_benchmark(gold: Path, result_file: Path, rights_file: Path, output: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(Path(rights_file).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise PatentWorkflowError("无法读取评测数据授权声明文件。") from exc
    result = evaluate_retrieval(_load_jsonl(gold), _load_jsonl(result_file), manifest)
    save_json(Path(output), result)
    return result
