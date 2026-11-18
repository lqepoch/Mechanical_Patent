"""Editable engineering diagrams derived from explicit structured relationships.

This module never runs browsers, CAD tools or LaTeX. No geometric claims.
"""
from __future__ import annotations
from hashlib import sha256
import html
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from typing import Any
from .core import PatentWorkflowError, save_json

MAX_SOURCE_BYTES = 90_000
MAX_FIGURES = 3
SOURCE_RE = re.compile(r"figures/auto-(?:principle|flowchart|sequence)-[0-9a-f]{16}\.(?:drawio|mmd)\Z")
ASSET_RE = re.compile(r"figures/auto-(?:principle|flowchart|sequence)-[0-9a-f]{16}\.pdf\Z")
ALLOWED = {"principle", "flowchart", "sequence"}


def _field(value: Any, name: str, maximum: int = 120) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise PatentWorkflowError(f"图示字段{name}缺失或长度超限。")
    cleaned = value.strip()
    if any((ord(ch) < 32 and ch not in "\n\t") or ord(ch) == 127 for ch in cleaned):
        raise PatentWorkflowError(f"图示字段{name}包含非法控制字符。")
    return cleaned


def _list(value: Any, name: str, maximum: int) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > maximum or any(not isinstance(x, dict) for x in value):
        raise PatentWorkflowError(f"{name}需要有限个结构化对象。")
    return value


def _mermaid_label(value: str) -> str:
    normalized = " ".join(_field(value, "文字", 180).split())
    return (html.escape(normalized, quote=True).replace(chr(96), "&#96;")
            .replace("%", "％").replace("[", "［").replace("]", "］"))


def _drawio(brief: dict[str, Any]) -> str | None:
    components = _list(brief.get("components"), "components", 40)
    links = _list(brief.get("diagram_relations"), "diagram_relations", 40)
    if not links:
        return None
    nodes = {}
    for index, item in enumerate(components):
        number = _field(item.get("number"), "部件编号", 12)
        if not re.fullmatch(r"[A-Za-z0-9-]+", number) or number in nodes:
            raise PatentWorkflowError("原理图零件编号重复或不合法。")
        nodes[number] = (index, _field(item.get("name"), "零件名称", 70))
    if len(nodes) < 2:
        raise PatentWorkflowError("原理图至少需要两个明确的部件。")
    for edge in links:
        if _field(edge.get("source"), "连接起点", 12) not in nodes or _field(edge.get("target"), "连接终点", 12) not in nodes:
            raise PatentWorkflowError("部件关系指向不存在的部件。")
        kind = edge.get("kind", "mechanical")
        if kind not in {"mechanical", "hydraulic", "pneumatic", "electrical", "signal"}:
            raise PatentWorkflowError("未知部件连接种类。")
        _field(edge.get("label", kind), "连接关系说明", 85)
    mxfile = ET.Element("mxfile", {"host": "app.diagrams.net", "type": "device", "version": "1.0"})
    diagram = ET.SubElement(mxfile, "diagram", {"id": "engineering", "name": "原理关系-非尺寸图"})
    model = ET.SubElement(diagram, "mxGraphModel", {
        "dx": "1168", "dy": "740", "grid": "1", "gridSize": "10", "page": "1",
        "pageScale": "1", "pageWidth": "1169", "pageHeight": "827", "math": "0", "shadow": "0",
    })
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    for number, (index, name) in nodes.items():
        row, column = divmod(index, 4)
        cell = ET.SubElement(root, "mxCell", {
            "id": "N" + number, "value": f"{number} {name}",
            "style": "rounded=1;whiteSpace=wrap;html=0;fillColor=#ffffff;strokeColor=#222222;fontColor=#111111;",
            "vertex": "1", "parent": "1",
        })
        ET.SubElement(cell, "mxGeometry", {
            "x": str(55 + column * 275), "y": str(100 + row * 210),
            "width": "190", "height": "88", "as": "geometry",
        })
    for index, edge in enumerate(links, start=1):
        label = edge.get("label", edge.get("kind", "mechanical"))
        style = "endArrow=block;html=0;rounded=0;strokeColor=#333333;"
        if edge.get("kind") in {"signal", "electrical"}:
            style += "dashed=1;"
        cell = ET.SubElement(root, "mxCell", {
            "id": "E" + str(index), "value": _field(label, "连接关系说明", 85),
            "style": style, "edge": "1", "parent": "1",
            "source": "N" + edge["source"], "target": "N" + edge["target"],
        })
        ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(mxfile, encoding="unicode", short_empty_elements=True) + "\n"


def _flowchart(brief: dict[str, Any]) -> str | None:
    steps = _list(brief.get("process_steps"), "process_steps", 30)
    if len(steps) < 2:
        return None
    lines = ["flowchart TD"]
    for i, step in enumerate(steps, 1):
        trigger = _mermaid_label(step.get("trigger"))
        action = _mermaid_label(step.get("action"))
        result = _mermaid_label(step.get("result"))
        lines.append(f'    S{i}["{i}. 触发：{trigger} ；动作：{action} ；结果：{result}"]')
        if i > 1:
            lines.append(f"    S{i-1} --> S{i}")
    return "\n".join(lines) + "\n"


def _sequence(brief: dict[str, Any]) -> str | None:
    messages = _list(brief.get("sequence_messages"), "sequence_messages", 30)
    if not messages:
        return None
    participants: dict[str, str] = {}
    lines = ["sequenceDiagram", "    autonumber"]
    for message in messages:
        for field in ("sender", "receiver"):
            label = _field(message.get(field), field, 70)
            if label not in participants:
                participants[label] = "P" + str(len(participants) + 1)
                if len(participants) > 12:
                    raise PatentWorkflowError("时序图参与者最多12个。")
        _field(message.get("message"), "交互动作", 180)
    for name, identifier in participants.items():
        lines.append(f"    participant {identifier} as {_mermaid_label(name)}")
    for entry in messages:
        arrow = "-->>" if entry.get("type", "call") == "reply" else "->>"
        if entry.get("type", "call") not in {"reply", "call"}:
            raise PatentWorkflowError("未知时序信息类型。")
        lines.append(f'    {participants[entry["sender"]]}{arrow}{participants[entry["receiver"]]}: {_mermaid_label(entry["message"])}')
    return "\n".join(lines) + "\n"


def _safe_figure_dir(case_dir: Path) -> Path:
    root = Path(case_dir)
    if root.is_symlink() or not root.is_dir():
        raise PatentWorkflowError("研究运行目录必须为真实目录。")
    fig = root / "figures"
    if fig.is_symlink():
        raise PatentWorkflowError("figures 目录禁止使用符号链接。")
    fig.mkdir(mode=0o700, exist_ok=True)
    if not fig.resolve().is_relative_to(root.resolve()):
        raise PatentWorkflowError("图示目录越界。")
    return fig


def _write_source(path: Path, content: bytes) -> None:
    if len(content) > MAX_SOURCE_BYTES:
        raise PatentWorkflowError("可编辑图示源文件超出限制。")
    if path.is_symlink():
        raise PatentWorkflowError("图示源文件不能是符号链接。")
    if path.exists():
        if path.read_bytes() != content:
            raise PatentWorkflowError("哈希相同但源文件内容冲突。")
        return
    try:
        with path.open("xb") as fd:
            fd.write(content)
    except FileExistsError:
        if path.is_symlink() or path.read_bytes() != content:
            raise PatentWorkflowError("并发生成源图发生冲突。")
    path.chmod(0o600)


def _file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def prepare_figures(case_dir: Path, *, candidate_id: str, wanted: list[str] | None = None) -> dict[str, Any]:
    """Persist editable sources; external renderers belong only to a separate worker."""
    root = Path(case_dir).resolve()
    brief_path = root / "08a_technical_brief.json"
    if brief_path.is_symlink() or not brief_path.is_file() or brief_path.stat().st_size > 180_000:
        raise PatentWorkflowError("当前研发案卷缺少安全的工程方案。")
    brief_bytes = brief_path.read_bytes()
    brief = json.loads(brief_bytes)
    if brief.get("candidate_id") != candidate_id:
        raise PatentWorkflowError("所选发明编号与研发方案不一致。")
    if wanted is not None and (not isinstance(wanted, list) or len(wanted) > MAX_FIGURES
                               or any(x not in ALLOWED for x in wanted) or len(wanted) != len(set(wanted))):
        raise PatentWorkflowError("指定图示类型不合法。")
    _safe_figure_dir(root)
    candidates = [
        ("principle", _drawio(brief), "结构与接口关系示意（非尺寸图）", "structure", "drawio"),
        ("flowchart", _flowchart(brief), "工作步骤流程图", "process", "mermaid"),
        ("sequence", _sequence(brief), "多主体交互时序图", "process", "mermaid"),
    ]
    entries = []
    unavailable = []
    for kind, body, caption, placement, renderer in candidates:
        if wanted is not None and kind not in wanted:
            continue
        if not body:
            unavailable.append({"kind": kind, "reason": "缺少明确结构连线、连续步骤或主体交互数据"})
            continue
        raw = body.encode("utf-8")
        digest = sha256(raw).hexdigest()
        extension = "drawio" if renderer == "drawio" else "mmd"
        base = f"auto-{kind}-{digest[:16]}"
        source = "figures/" + base + "." + extension
        asset = "figures/" + base + ".pdf"
        _write_source(root / source, raw)
        entries.append({
            "id": base, "kind": kind, "source": source,
            "source_sha256": digest, "asset": asset,
            "caption": caption, "placement": placement, "renderer": renderer,
            "geometry_proven": False,
        })
    out = {
        "format_version": 1,
        "candidate_id": candidate_id, "brief_sha256": sha256(brief_bytes).hexdigest(),
        "status": "sources_ready" if entries else "no_diagrams_needed",
        "entries": entries[:MAX_FIGURES], "unavailable": unavailable,
        "no_real_cad_claim": True, "filing_authorized": False,
    }
    target = root / "08d_figure_plan.json"
    if target.is_symlink():
        raise PatentWorkflowError("图示计划文件不能是符号链接。")
    save_json(target, out)
    return out


def read_figure_plan(case_dir: Path) -> tuple[dict[str, Any], bytes]:
    root = Path(case_dir).resolve()
    plan_path = root / "08d_figure_plan.json"
    if plan_path.is_symlink() or not plan_path.is_file() or plan_path.stat().st_size > 80_000:
        raise PatentWorkflowError("图示计划不存在或不安全。")
    raw = plan_path.read_bytes()
    doc = json.loads(raw)
    if doc.get("format_version") != 1 or not isinstance(doc.get("entries"), list) or len(doc["entries"]) > MAX_FIGURES:
        raise PatentWorkflowError("图示计划格式不兼容。")
    for item in doc["entries"]:
        if not isinstance(item, dict) or item.get("kind") not in ALLOWED:
            raise PatentWorkflowError("图示计划含不允许的类型。")
        if not isinstance(item.get("source"), str) or not SOURCE_RE.fullmatch(item["source"]):
            raise PatentWorkflowError("图示源路径越界或非法。")
        if not isinstance(item.get("asset"), str) or not ASSET_RE.fullmatch(item["asset"]):
            raise PatentWorkflowError("图示产物路径越界或非法。")
        source_file = root / item["source"]
        if source_file.is_symlink() or not source_file.is_file() or source_file.stat().st_size > MAX_SOURCE_BYTES:
            raise PatentWorkflowError("原始图源缺失或不安全。")
        if _file_sha(source_file) != item.get("source_sha256"):
            raise PatentWorkflowError("原始图源已被篡改，需要重新规划。")
    return doc, raw
