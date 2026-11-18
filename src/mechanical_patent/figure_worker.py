"""Operator-only figure/PDF worker: never exposed through MCP as process execution.

Deployment must isolate its browser, Electron, and XeLaTeX processes inside a
nonprivileged, network-disabled, resource-limited container.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any
from uuid import uuid4
from .core import PatentWorkflowError, save_json
from .figure_pipeline import _safe_figure_dir, read_figure_plan
from .technical_brief import render_brief

MAX_PDF_BYTES = 12_000_000


def _verify_pdf(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or not 200 <= path.stat().st_size <= MAX_PDF_BYTES:
        raise PatentWorkflowError("渲染输出 PDF 缺失或大小异常。")
    data = path.read_bytes()
    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-1024:]:
        raise PatentWorkflowError("渲染输出不是完整的 PDF 文件。")
    return {"sha256": sha256(data).hexdigest(), "size": len(data)}


def _run(args: list[str], *, cwd: Path, timeout: int) -> None:
    """An explicit local command in an OS sandbox, never a shell command."""
    try:
        result = subprocess.run(args, cwd=cwd, check=False, timeout=timeout,
                                capture_output=True, text=True, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PatentWorkflowError("受控图示构建进程不可用或超时。") from exc
    if result.returncode:
        # Renderer output may echo confidential source text: do not expose stderr.
        raise PatentWorkflowError(f"受控渲染器返回非零退出码：{result.returncode}。")


def _binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise PatentWorkflowError(f"隔离工作器尚未安装{name}，请检查工具镜像。")
    return str(Path(path).resolve())


def render_figures(case_dir: Path, *, timeout: int = 90) -> dict[str, Any]:
    if not 15 <= timeout <= 240:
        raise PatentWorkflowError("图示转换超时必须为15—240秒。")
    root = Path(case_dir).resolve()
    _safe_figure_dir(root)
    plan, plan_bytes = read_figure_plan(root)
    original = root / "08a_technical_brief.json"
    if original.is_symlink() or not original.is_file() or sha256(original.read_bytes()).hexdigest() != plan["brief_sha256"]:
        raise PatentWorkflowError("图示计划与技术方案版本不符，已拒绝渲染。")
    rendered: list[dict[str, Any]] = []
    failures = []
    for entry in plan["entries"]:
        target = root / entry["asset"]
        if target.is_symlink():
            raise PatentWorkflowError("图示产物不能为符号链接。")
        try:
            if not target.exists():
                temp = target.with_name(target.stem + "-pending-" + uuid4().hex[:12] + ".pdf")
                if entry["renderer"] == "mermaid":
                    cmd = [_binary("mmdc"), "-i", str(root / entry["source"]),
                           "-o", str(temp), "-b", "white"]
                elif entry["renderer"] == "drawio":
                    cmd = [_binary("drawio"), "--export", "--format", "pdf", "--crop",
                           "--output", str(temp), str(root / entry["source"])]
                    if not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
                        cmd = [_binary("xvfb-run"), "-a", *cmd]
                else:
                    raise PatentWorkflowError("图示类型未被受控工作器授权。")
                try:
                    _run(cmd, cwd=root, timeout=timeout)
                    info = _verify_pdf(temp)
                    temp.replace(target)
                finally:
                    temp.unlink(missing_ok=True)
            else:
                info = _verify_pdf(target)
            rendered.append({"id": entry["id"], "source_sha256": entry["source_sha256"],
                             "asset": entry["asset"], **info})
        except PatentWorkflowError as exc:
            failures.append({"id": entry["id"], "reason": str(exc)})
    report = {
        "format_version": 1,
        "status": "rendered" if not failures else "partial_failure",
        "manifest_sha256": sha256(plan_bytes).hexdigest(),
        "candidate_id": plan["candidate_id"],
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rendered": rendered, "failures": failures,
        "pdf_content_checked": "header/trailer/size only; isolated renderer remains required",
    }
    path = root / "08e_figure_render.json"
    if path.is_symlink():
        raise PatentWorkflowError("输出的渲染记录不能为符号链接。")
    save_json(path, report)
    return report


def sync_figures(case_dir: Path, *, candidate_id: str) -> dict[str, Any]:
    """Verify all rendered PDFs, update the technical brief and invalidate old signatures."""
    root = Path(case_dir).resolve()
    plan, plan_bytes = read_figure_plan(root)
    report_path = root / "08e_figure_render.json"
    if report_path.is_symlink() or not report_path.is_file() or report_path.stat().st_size > 80_000:
        raise PatentWorkflowError("缺少隔离工作器渲染记录。")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (plan.get("candidate_id") != candidate_id or report.get("candidate_id") != candidate_id
            or report.get("status") != "rendered"
            or report.get("manifest_sha256") != sha256(plan_bytes).hexdigest()
            or len(report.get("rendered", [])) != len(plan["entries"])):
        raise PatentWorkflowError("图示计划、文件与渲染记录不一致或尚未全部完成。")
    expected = {x["id"]: x for x in plan["entries"]}
    for row in report["rendered"]:
        if not isinstance(row, dict) or row.get("id") not in expected:
            raise PatentWorkflowError("未知渲染产物编号。")
        entry = expected.pop(row["id"])
        image = root / entry["asset"]
        info = _verify_pdf(image)
        if row.get("source_sha256") != entry["source_sha256"] or row.get("asset") != entry["asset"] or info != {
            "sha256": row.get("sha256"), "size": row.get("size")
        }:
            raise PatentWorkflowError("图示输出已被替换或哈希不匹配。")
    if expected:
        raise PatentWorkflowError("部分图示未在渲染记录出现。")
    brief_file = root / "08a_technical_brief.json"
    if brief_file.is_symlink() or not brief_file.is_file():
        raise PatentWorkflowError("工程技术方案缺失。")
    previous = brief_file.read_bytes()
    new = json.loads(previous)
    source_hash = sha256(previous).hexdigest()
    sync_file = root / "08f_figure_sync.json"
    if sync_file.is_symlink():
        raise PatentWorkflowError("图示同步状态文件不可信。")
    if source_hash != plan["brief_sha256"]:
        if sync_file.is_file():
            prior = json.loads(sync_file.read_text(encoding="utf-8"))
            if (prior.get("manifest_sha256") == report["manifest_sha256"]
                    and prior.get("new_brief_sha256") == source_hash):
                return {"status": "already_synced", "brief_sha256": source_hash}
        raise PatentWorkflowError("原始技术方案已修改，无法应用旧版本配图。")
    figures = new.setdefault("figures", [])
    for entry in plan["entries"]:
        figure = {"kind": entry["kind"], "caption": entry["caption"],
                  "asset": entry["asset"], "placement": entry["placement"]}
        if not any(x.get("asset") == entry["asset"] for x in figures):
            figures.append(figure)
    latex, quality = render_brief(new, root)
    save_json(brief_file, new)
    tex_file = root / "08a_technical_brief.tex"
    if tex_file.is_symlink():
        raise PatentWorkflowError("LaTeX 文件不能为符号链接。")
    tex_file.write_text(latex, encoding="utf-8")
    new_hash = sha256(brief_file.read_bytes()).hexdigest()
    sync_report = {
        "status": "synced", "manifest_sha256": report["manifest_sha256"],
        "old_brief_sha256": source_hash, "new_brief_sha256": new_hash,
        "tex_sha256": sha256(tex_file.read_bytes()).hexdigest(),
        "candidate_id": candidate_id, "figure_count": len(plan["entries"]),
        "technical_review_invalidated": True, "application_conversion_invalidated": True,
        "filing_authorized": False, "quality": quality,
    }
    save_json(sync_file, sync_report)
    from .audit import append_audit_event
    append_audit_event(root, stage="工程技术方案", action="同步实际渲染图示并生成新技术方案版本",
                       actor="MCP 工具", role="系统",
                       payload={"candidate_id": candidate_id, "new_brief_sha256": new_hash,
                                "manifest_sha256": report["manifest_sha256"]})
    return sync_report


def compile_brief_pdf(case_dir: Path, *, timeout: int = 120) -> dict[str, Any]:
    """Run XeLaTeX twice only inside the operator-managed isolated worker."""
    root = Path(case_dir).resolve()
    if not 30 <= timeout <= 300:
        raise PatentWorkflowError("PDF 编译超时须为30—300秒。")
    tex = root / "08a_technical_brief.tex"
    if root.is_symlink() or not root.is_dir() or tex.is_symlink() or not tex.is_file():
        raise PatentWorkflowError("无法在非私有真实案卷中编译 LaTeX。")
    build = root / "_latex_build"
    if build.is_symlink():
        raise PatentWorkflowError("编译目录不能为符号链接。")
    build.mkdir(mode=0o700, exist_ok=True)
    engine = _binary("xelatex")
    command = [engine, "-no-shell-escape", "-halt-on-error", "-interaction=nonstopmode",
               "-file-line-error", f"-output-directory={build}", tex.name]
    for _ in range(2):
        _run(command, cwd=root, timeout=timeout)
    source = build / "08a_technical_brief.pdf"
    info = _verify_pdf(source)
    output = root / "08a_technical_brief.pdf"
    if output.is_symlink():
        raise PatentWorkflowError("目标 PDF 是不允许的符号链接。")
    tmp = output.with_name(".engineering-" + uuid4().hex + ".pdf")
    try:
        shutil.copyfile(source, tmp)
        tmp.replace(output)
    finally:
        tmp.unlink(missing_ok=True)
    report = {
        "status": "rendered", "tex_sha256": sha256(tex.read_bytes()).hexdigest(),
        "pdf_sha256": info["sha256"], "bytes": info["size"], "filing_authorized": False,
    }
    save_json(root / "08g_pdf_build.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="受控独立图示/PDF构建工作器（应在隔离容器中执行）")
    parser.add_argument("command", choices=["render-figures", "compile-brief-pdf"])
    parser.add_argument("--case-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args(argv)
    try:
        if args.command == "render-figures":
            result = render_figures(args.case_dir, timeout=args.timeout)
        else:
            result = compile_brief_pdf(args.case_dir, timeout=max(args.timeout, 30))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "rendered" else 2
    except (PatentWorkflowError, OSError, ValueError, TypeError):
        print("FIGURE_WORKER_ERROR: blocked unsafe or failed rendering", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
