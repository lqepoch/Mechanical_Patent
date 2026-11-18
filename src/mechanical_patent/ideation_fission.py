"""可审计的机械专利构思裂变与质量—多样性筛选。

由当前 ChatGPT/Codex 等 Agent 生成技术内容；此模块只管理谱系、证据、
评价与候选移交，不声称自动证明新颖性、创造性或实验结果。
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Iterator
from uuid import uuid4

from .core import Evidence, PatentWorkflowError, evidence_id, save_json, utc_now

AXES = ("机械结构", "流体与热", "控制系统", "材料", "制造工艺", "系统集成", "跨领域原理")
METHODS = ("TRIZ", "SCAMPER", "设计思维", "FMEA", "形态分析", "逆向约束", "跨领域类比", "第一性原理", "组合创新")
TRANSFORMATIONS = (
    ("矛盾反转", "反转导致原方案失效的约束，构造另一种作用机理"),
    ("拆分重构", "把关键部件/动作拆成可独立控制的功能单元"),
    ("参数与拓扑跃迁", "改变流道、机构拓扑或耦合关系，禁止仅修改常规阈值"),
    ("异域迁移", "从不同产业的已公开物理机理寻找可实施的迁移"),
    ("失效倒推", "依据 FMEA 的失效链设计主动预防或容错结构"),
    ("跨代组合", "选择另一技术路线组合，必须解释功能协同和非简单叠加效果"),
)
SCORE_FIELDS = ("技术可行性", "公开充分度", "差异假说", "技术效果", "应用价值", "复杂性风险", "现有技术冲突")
MAX_GENERATION = 4
MAX_NODES = 120


def _required(value: Any, label: str, *, maximum: int = 6000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise PatentWorkflowError(f"{label}须为非空且长度不超过{maximum}的文本。")
    return value.strip()


def _list_of_text(value: Any, label: str, *, maximum: int = 24) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise PatentWorkflowError(f"{label}须包含1至{maximum}条。")
    return [_required(x, label, maximum=1200) for x in value]


def _fingerprint(mechanism: str, features: list[str]) -> str:
    canonical = " ".join((" ".join([mechanism] + features)).casefold().split())
    return sha256(canonical.encode("utf-8")).hexdigest()


@contextmanager
def _exclusive(path: Path) -> Iterator[None]:
    lock = path.with_suffix(".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise PatentWorkflowError("构思谱系有另一位写入者；请检查并发或遗留锁。") from exc
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


class FissionBoard:
    """一个研究运行实例中的发明谱系。多进程写入使用短期排他锁。"""

    def __init__(self, case_dir: Path):
        self.case_dir = Path(case_dir).resolve()
        if not self.case_dir.is_dir() or not (self.case_dir / "00_intake.json").is_file():
            raise PatentWorkflowError("须先建立真实研究案卷，才能开启想法裂变。")
        self.path = self.case_dir / "05a_idea_fission.json"

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("candidates"), list):
                raise PatentWorkflowError("构思谱系文件版本或结构无效。")
            return data
        intake = json.loads((self.case_dir / "00_intake.json").read_text(encoding="utf-8"))
        return {
            "schema_version": 1, "case_id": intake["case_id"],
            "created_at": utc_now(), "candidates": [], "events": [],
            "notice": "研究设想与内部评分均非新颖性、创造性或自由实施法律结论。",
        }

    def _evidence_ids(self) -> set[str]:
        path = self.case_dir / "04_evidence.json"
        if not path.exists():
            return set()
        records = json.loads(path.read_text(encoding="utf-8")).get("records", [])
        ids = set()
        for raw in records:
            try:
                ids.add(evidence_id(Evidence.from_dict(raw)))
            except (ValueError, TypeError, KeyError):
                continue
        return ids

    def _event(self, data: dict[str, Any], action: str, identifier: str) -> None:
        data["events"].append({"at": utc_now(), "action": action, "candidate_id": identifier})

    def list_candidates(self) -> dict[str, Any]:
        data = self._load()
        return {"case_id": data["case_id"], "candidates": data["candidates"],
                "total": len(data["candidates"]), "max_nodes": MAX_NODES}

    def plan(self, parent_id: str = "", limit: int = 6) -> dict[str, Any]:
        """仅生成供 AI 执行的研究任务，不制造技术方案或伪造专利结果。"""
        data = self._load()
        limit = max(1, min(int(limit), len(TRANSFORMATIONS)))
        parent = next((x for x in data["candidates"] if x["id"] == parent_id), None) if parent_id else None
        if parent_id and parent is None:
            raise PatentWorkflowError("父构思未登记。")
        generation = parent["generation"] + 1 if parent else 0
        if generation > MAX_GENERATION:
            raise PatentWorkflowError("已达到最大裂变深度，需先收敛和复核。")
        tasks = []
        for name, purpose in TRANSFORMATIONS[:limit]:
            tasks.append({
                "transformation": name, "research_question": purpose,
                "generation": generation, "parent_id": parent_id,
                "must_provide": [
                    "新作用机理", "区别技术特征", "机械或控制实现细节",
                    "理论依据及量纲", "失效模式", "可证伪实验", "反证检索词",
                ],
                "evidence_warning": "须继续搜索真实在先技术；评分不代表获得专利。",
            })
        return {"status": "awaiting_agent_ideas", "tasks": tasks,
                "budget": {"remaining_nodes": MAX_NODES - len(data["candidates"]),
                           "maximum_generation": MAX_GENERATION}}

    def register(self, candidate: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(candidate, dict):
            raise PatentWorkflowError("构思输入须为结构化对象。")
        title = _required(candidate.get("title"), "标题", maximum=200)
        problem = _required(candidate.get("technical_problem"), "技术问题")
        mechanism = _required(candidate.get("mechanism"), "具体物理机理")
        enabling = _required(candidate.get("enabling_details"), "可实施细节")
        features = _list_of_text(candidate.get("distinguishing_features"), "区别特征")
        assumptions = _list_of_text(candidate.get("assumptions"), "边界假设")
        falsification = _list_of_text(candidate.get("falsification_tests"), "证伪试验")
        effect = _required(candidate.get("expected_effect"), "预期效果")
        axis = candidate.get("technical_axis")
        method = candidate.get("inventive_method")
        if axis not in AXES or method not in METHODS:
            raise PatentWorkflowError("技术轴或创新方法不在允许集合内。")
        parent_id = str(candidate.get("parent_id") or "")
        references = candidate.get("evidence_ids", [])
        if not isinstance(references, list) or len(references) > 30 or any(not isinstance(x, str) for x in references):
            raise PatentWorkflowError("来源编号必须是列表，最多30条。")
        known = self._evidence_ids()
        if set(references) - known:
            raise PatentWorkflowError("构思引用了尚未入库的专利/论文编号。")
        fp = _fingerprint(mechanism, features)
        with _exclusive(self.path):
            data = self._load()
            if len(data["candidates"]) >= MAX_NODES:
                raise PatentWorkflowError("候选数量达到预算上限，先进行质量—多样性筛选。")
            if any(x["fingerprint"] == fp for x in data["candidates"]):
                raise PatentWorkflowError("发现技术特征完全重复的构思，停止无意义裂变。")
            parent = next((x for x in data["candidates"] if x["id"] == parent_id), None) if parent_id else None
            if parent_id and parent is None:
                raise PatentWorkflowError("父构思不存在。")
            generation = parent["generation"] + 1 if parent else 0
            if generation > MAX_GENERATION:
                raise PatentWorkflowError("超过允许的裂变代数。")
            item = {
                "id": "IF-" + uuid4().hex[:12].upper(), "parent_id": parent_id,
                "generation": generation, "title": title, "technical_problem": problem,
                "mechanism": mechanism, "enabling_details": enabling,
                "distinguishing_features": features, "assumptions": assumptions,
                "falsification_tests": falsification, "expected_effect": effect,
                "technical_axis": axis, "inventive_method": method,
                "evidence_ids": list(dict.fromkeys(references)),
                "fingerprint": fp, "created_at": utc_now(), "status": "hypothesis_only",
                "evaluation": None, "origin": "agent_hypothesis",
                "legal_patentability_verified": False, "experiment_verified": False,
            }
            data["candidates"].append(item)
            self._event(data, "register_hypothesis", item["id"])
            save_json(self.path, data)
        return item

    def evaluate(self, candidate_id: str, scores: dict[str, float], review: str,
                 countersearch_refs: list[str], physical_principle: str,
                 engineering_risks: list[str]) -> dict[str, Any]:
        _required(review, "评审理由")
        _required(physical_principle, "理论依据")
        risks = _list_of_text(engineering_risks, "工程风险")
        if not isinstance(scores, dict) or set(scores) != set(SCORE_FIELDS):
            raise PatentWorkflowError("必须分别填写全部七项工程/研究评分。")
        if any(type(v) not in (float, int) or not 0 <= v <= 5 for v in scores.values()):
            raise PatentWorkflowError("内部评分取值范围为0至5。")
        if not isinstance(countersearch_refs, list) or any(not isinstance(x, str) for x in countersearch_refs):
            raise PatentWorkflowError("反证来源须为证据编号列表。")
        if set(countersearch_refs) - self._evidence_ids():
            raise PatentWorkflowError("反证引用了未归档的来源编号。")
        # 研究启发式：较高值代表优先审查，完全不推定法定创造性。
        score = round(
            0.24 * scores["技术可行性"] + 0.20 * scores["公开充分度"]
            + 0.15 * scores["差异假说"] + 0.15 * scores["技术效果"]
            + 0.14 * scores["应用价值"] - 0.06 * scores["复杂性风险"]
            - 0.06 * scores["现有技术冲突"], 3
        )
        with _exclusive(self.path):
            data = self._load()
            item = next((x for x in data["candidates"] if x["id"] == candidate_id), None)
            if item is None:
                raise PatentWorkflowError("目标构思不存在。")
            item["evaluation"] = {
                "scores": scores, "heuristic_score": score, "review": review,
                "countersearch_refs": list(dict.fromkeys(countersearch_refs)),
                "physical_principle": physical_principle,
                "engineering_risks": risks, "reviewed_at": utc_now(),
                "notice": "代理人打分仅用于安排下一轮研究，不能证明新颖性或创造性。",
            }
            item["status"] = "needs_countersearch" if not countersearch_refs else "engineering_review_pending"
            self._event(data, "evaluate_hypothesis", item["id"])
            save_json(self.path, data)
        return {"candidate_id": candidate_id, "score": score, "status": item["status"]}

    def frontier(self, top_k: int = 8) -> dict[str, Any]:
        """按技术轴×创新方法保留多样性，避免同方向候选淹没其他路线。"""
        candidates = [x for x in self._load()["candidates"] if x.get("evaluation")]
        cells: dict[tuple[str, str], dict[str, Any]] = {}
        for item in candidates:
            key = (item["technical_axis"], item["inventive_method"])
            current = cells.get(key)
            if current is None or (item["evaluation"]["heuristic_score"], item["id"]) > (
                current["evaluation"]["heuristic_score"], current["id"]
            ):
                cells[key] = item
        selected = sorted(cells.values(), key=lambda x: (-x["evaluation"]["heuristic_score"], x["id"]))
        selected = selected[:max(1, min(int(top_k), 24))]
        return {
            "status": "internal_research_priority_only",
            "ranked": [{"id": x["id"], "title": x["title"], "axis": x["technical_axis"],
                        "method": x["inventive_method"], "generation": x["generation"],
                        "score": x["evaluation"]["heuristic_score"],
                        "countersearch_pending": not bool(x["evaluation"]["countersearch_refs"])}
                       for x in selected],
            "diversity_cells": len(cells), "evaluated_candidates": len(candidates),
            "legal_conclusion": "none",
        }

    def promote(self, candidate_id: str) -> dict[str, Any]:
        """只向旧案卷导出待独立反证/工程审核的候选，禁止提前给予法律通过标记。"""
        with _exclusive(self.path):
            data = self._load()
            item = next((x for x in data["candidates"] if x["id"] == candidate_id), None)
            if item is None:
                raise PatentWorkflowError("构思不存在。")
            review = item.get("evaluation") or {}
            if not item["evidence_ids"] or not review.get("countersearch_refs") or not review.get("physical_principle"):
                raise PatentWorkflowError("缺少来源、反证记录或理论依据，无法移交专利申请流程。")
            file = self.case_dir / "05_inventions.json"
            existing = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {"candidates": []}
            items = existing.get("candidates", [])
            if not isinstance(items, list):
                raise PatentWorkflowError("原候选案卷结构损坏。")
            if any(x.get("id") == candidate_id for x in items):
                raise PatentWorkflowError("该候选已移交。")
            items.append({
                "id": item["id"], "title": item["title"],
                "technical_problem": item["technical_problem"],
                "mechanism": item["mechanism"], "enabling_details": item["enabling_details"],
                "distinguishing_features": item["distinguishing_features"],
                "expected_effect": item["expected_effect"], "assumptions": item["assumptions"],
                "falsification_tests": item["falsification_tests"],
                "inventive_method": item["inventive_method"],
                "evidence_ids": item["evidence_ids"], "fission_parent_id": item["parent_id"],
                "verification_status": "hypothesis_only",
                "legal_patentability_verified": False,
            })
            existing["candidates"] = items
            existing["status"] = "awaiting_independent_countersearch_and_engineering_review"
            save_json(file, existing)
            item["status"] = "exported_for_review"
            self._event(data, "export_for_independent_review", item["id"])
            save_json(self.path, data)
        return {"candidate_id": candidate_id, "exported": True,
                "filing_authorized": False,
                "required_next": ["06_countersearch.json", "07_engineering.json",
                                  "08_application.json", "09_quality_gate.json", "人工签核"]}