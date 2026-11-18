"""工程师可读技术方案：结构化事实校验与无模型 LaTeX 排版。

默认只生成技术说明书；不生成权利要求、说明书、摘要，也不进行 PDF shell 执行。
由 MCP Host/工程师填写内容，服务端只负责来源边界、可读性和安全排版。
"""
from __future__ import annotations

from importlib import resources
from pathlib import Path
import re
from typing import Any

from .core import PatentWorkflowError

FIGURE_KINDS = frozenset({
    "structure", "section", "exploded", "principle", "flowchart",
    "sequence", "state", "comparison", "curve", "photo",
})
PROFILES = frozenset({"auto", "mechanical", "control", "hybrid", "concise"})
_ASSET = re.compile(r"figures/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*\.(?:pdf|png|jpg|jpeg)\Z")
_TEX_SPECIAL = {
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$",
    "&": r"\&", "#": r"\#", "%": r"\%", "_": r"\_",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def _plain(value: Any, name: str, maximum: int = 6000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise PatentWorkflowError(f"技术方案的{name}必须为不超过{maximum}字的非空文本。")
    return value.strip()


def _entries(data: dict[str, Any], name: str, maximum: int = 30) -> list[dict[str, Any]]:
    value = data.get(name, [])
    if not isinstance(value, list) or len(value) > maximum or any(not isinstance(x, dict) for x in value):
        raise PatentWorkflowError(f"{name}必须是数量不超过{maximum}的对象数组。")
    return value


def validate_brief(data: dict[str, Any], *, known_evidence: set[str] | None = None) -> dict[str, Any]:
    """对研发技术方案做静态合同检查。技术审查通过仍需工程师签核。"""
    if not isinstance(data, dict):
        raise PatentWorkflowError("研发技术方案须为 JSON 对象。")
    if set(data) & {"claims", "claim_support", "application_text", "patent_abstract"}:
        raise PatentWorkflowError("研发阶段禁止注入正式专利申请字段。")
    for field in ("candidate_id", "title", "technical_problem", "solution",
                  "mechanism", "expected_effect", "verification_plan"):
        _plain(data.get(field), field)
    components = _entries(data, "components")
    steps = _entries(data, "process_steps")
    inventions = _entries(data, "innovation_points")
    prior_art = _entries(data, "prior_art")
    risks = _entries(data, "risks")
    figures = _entries(data, "figures", maximum=12)
    if not components and not steps:
        raise PatentWorkflowError("结构部件或工作步骤至少提供一种，以便工程师复现方案。")
    if not inventions:
        raise PatentWorkflowError("至少提供一项具体的区别技术特征与作用效果。")
    ids = set()
    for item in components:
        number = _plain(item.get("number"), "部件标号", 12)
        if not re.fullmatch(r"[A-Za-z0-9-]{1,12}", number) or number in ids:
            raise PatentWorkflowError("部件标号格式错误或重复。")
        ids.add(number)
        _plain(item.get("name"), "部件名称", 100)
        _plain(item.get("role"), "部件作用")
    for item in steps:
        for field in ("trigger", "action", "result"):
            _plain(item.get(field), "工作步骤." + field)
    source_count = 0
    for item in inventions:
        for field in ("feature", "prior_difference", "technical_effect"):
            _plain(item.get(field), "创新点." + field)
        references = item.get("evidence_ids", [])
        if not isinstance(references, list) or len(references) > 20 or any(
            not isinstance(x, str) or not x.strip() for x in references
        ):
            raise PatentWorkflowError("创新点 evidence_ids 必须是有效的来源编号数组。")
        if known_evidence is not None and any(x not in known_evidence for x in references):
            raise PatentWorkflowError("创新点引用的证据编号不在当前案卷中。")
        source_count += len(references)
    for item in prior_art:
        for field in ("evidence_id", "known_solution", "difference"):
            _plain(item.get(field), "现有技术." + field)
        if known_evidence is not None and item["evidence_id"] not in known_evidence:
            raise PatentWorkflowError("现有技术编号未在案卷证据库核验。")
    for item in risks:
        for field in ("failure", "mitigation"):
            _plain(item.get(field), "风险." + field)
    for item in figures:
        kind = _plain(item.get("kind"), "图片类型", 30)
        if kind not in FIGURE_KINDS:
            raise PatentWorkflowError("图的类型不在支持范围内。")
        _plain(item.get("caption"), "图名", 300)
        asset = item.get("asset", "")
        if asset and (not isinstance(asset, str) or not _ASSET.fullmatch(asset)):
            raise PatentWorkflowError("图片必须为 figures/ 下的安全文件名（pdf/png/jpg）。")
    profile = data.get("profile", "auto")
    if profile not in PROFILES:
        raise PatentWorkflowError("未知技术方案模板风格。")
    if profile == "auto":
        profile = "hybrid" if components and steps else "mechanical" if components else "control"
    warnings = []
    if source_count == 0:
        warnings.append("所有创新点均缺少证据编号；暂不能对新颖性作出肯定结论。")
    if not prior_art:
        warnings.append("缺少逐文件的现有技术差异对照，请在技术评审前补充。")
    if not figures:
        warnings.append("暂无插图；若机械装配关系难以用文字理解，请补充结构线稿。")
    return {
        "valid": True, "profile": profile, "warnings": warnings,
        "innovation_count": len(inventions),
        "figure_types": [x["kind"] for x in figures],
        "candidate_id": data["candidate_id"],
        "application_authorized": False,
        "review_status": "awaiting_engineering_review",
    }


def tex_escape(value: str) -> str:
    """逐字符转义全部 TeX 特殊字符，不能注入命令。"""
    return "".join(_TEX_SPECIAL.get(ch, ch) for ch in value)


def _para(value: str) -> str:
    return tex_escape(value).replace("\n\n", "\n\n" + r"\par" + "\n")


def _section(title: str, content: str) -> str:
    return "\\section{" + tex_escape(title) + "}\n" + content + "\n"


def _bullets(rows: list[str]) -> str:
    return "\\begin{itemize}\n" + "\n".join("\\item " + x for x in rows) + "\n\\end{itemize}\n"


def _table(headers: tuple[str, ...], rows: list[list[str]], widths: tuple[str, ...]) -> str:
    if not rows:
        return ""
    cols = "|" + "|".join("p{" + width + r"\textwidth}" for width in widths) + "|"
    output = [r"\small\begin{longtable}{" + cols + "}", r"\hline",
              " & ".join(tex_escape(x) for x in headers) + r"\\\hline",
              r"\endfirsthead", r"\hline",
              " & ".join(tex_escape(x) for x in headers) + r"\\\hline",
              r"\endhead"]
    for cells in rows:
        output.append(" & ".join(tex_escape(str(x)) for x in cells) + r"\\\hline")
    output.append(r"\end{longtable}\normalsize")
    return "\n".join(output)


def render_brief(data: dict[str, Any], case_dir: Path, *,
                 known_evidence: set[str] | None = None) -> tuple[str, dict[str, Any]]:
    """返回独立 XeLaTeX 文档和审阅元数据，绝不执行外部命令。"""
    report = validate_brief(data, known_evidence=known_evidence)
    root = Path(case_dir).resolve()
    parts = [
        _section("一页理解方案",
                 r"\textbf{技术问题：}" + _para(data["technical_problem"])
                 + "\n\n" + r"\textbf{一句话方案：}" + _para(data["solution"])
                 + "\n\n" + r"\textbf{预期效果：}" + _para(data["expected_effect"])),
        _section("工作原理与创新机理", _para(data["mechanism"])),
    ]
    components = data.get("components", [])
    steps = data.get("process_steps", [])
    comp_body = _table(("标号", "部件", "作用"), [
        [x["number"], x["name"], x["role"]] for x in components
    ], (".11", ".22", ".58"))
    steps_body = _table(("触发条件", "动作", "状态/结果"), [
        [x["trigger"], x["action"], x["result"]] for x in steps
    ], (".27", ".35", ".29"))
    if report["profile"] == "control":
        if steps_body:
            parts.append(_section("执行步骤与条件逻辑", steps_body))
        if comp_body:
            parts.append(_section("结构和接口说明", comp_body))
    else:
        if comp_body:
            parts.append(_section("结构和接口说明", comp_body))
        if steps_body:
            parts.append(_section("执行步骤与条件逻辑", steps_body))

    innovation_rows = [
        r"\textbf{具体区别：}" + _para(x["feature"])
        + "\n" + r"\textbf{对照差异：}" + _para(x["prior_difference"])
        + "\n" + r"\textbf{技术效果：}" + _para(x["technical_effect"])
        + "\n" + r"\textbf{证据编号：}" + tex_escape("、".join(x.get("evidence_ids", [])) or "待检索确认")
        for x in data["innovation_points"]
    ]
    parts.append(_section("值得保护的技术创新点（初筛）", _bullets(innovation_rows)))

    if data.get("prior_art"):
        parts.append(_section("相关公开技术与差异", _table(
            ("来源 ID", "已知方案", "本方案区别"),
            [[x["evidence_id"], x["known_solution"], x["difference"]] for x in data["prior_art"]],
            (".17", ".35", ".39"))))
    if data.get("risks"):
        parts.append(_section("工程风险与失效处理", _table(
            ("风险/失效", "应对和验证"),
            [[x["failure"], x["mitigation"]] for x in data["risks"]],
            (".38", ".53"))))
    parts.append(_section("试验和评审计划", _para(data["verification_plan"])))

    figures = []
    missing = []
    for number, fig in enumerate(data.get("figures", []), 1):
        asset = fig.get("asset")
        if not asset:
            missing.append({"number": number, "reason": "未提供已导出的图片", "kind": fig["kind"]})
            continue
        path = root / asset
        # 安全路径只能是固定 figures 子目录下的非符号链接实际文件。
        if path.is_symlink() or not path.resolve().is_relative_to(root / "figures") or not path.is_file():
            missing.append({"number": number, "reason": "图纸未在案卷文件夹中找到", "asset": asset})
            continue
        figures.append(
            r"\begin{figure}[htbp]" + "\n" + r"\centering" + "\n"
            + r"\includegraphics[width=.9\linewidth]{" + asset + "}\n"
            + r"\caption{" + tex_escape(fig["caption"]) + "}\n"
            + r"\end{figure}")
    if figures:
        parts.append(_section("按需选用的技术图示", "\n".join(figures)))
    if missing:
        parts.append(_section("待补图纸清单", _bullets([
            tex_escape(f"图{f['number']}：{f.get('asset','无导出文件')}，{f['reason']}")
            for f in missing
        ])))
    if report["warnings"]:
        parts.append(_section("当前证据及表达缺口", _bullets([tex_escape(x) for x in report["warnings"]])))
    parts.append(_section("评审结论状态",
                          "当前为工程技术方案审阅稿。工程结构和控制可行性需要专业人员签核；"
                          "专利检索和创造性意见仅为阶段性研究，"
                          "尚未批准申请，不包含法定格式的权利要求、说明书或摘要。"))
    template = resources.files("mechanical_patent").joinpath("templates/engineering_brief.tex").read_text(encoding="utf-8")
    latex = template.replace("%%TITLE%%", tex_escape(data["title"])).replace(
        "%%CANDIDATE%%", tex_escape(data["candidate_id"])
    ).replace("%%PROFILE%%", tex_escape(report["profile"])).replace(
        "%%CONTENT%%", "\n\n".join(parts))
    report["missing_figures"] = missing
    report["latex_length"] = len(latex)
    return latex, report
