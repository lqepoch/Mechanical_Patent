"""同步 canonical skills/ 到 Codex 自动识别的 .agents/skills/（跨 Windows/Linux）。

Codex 读取仓库级 .agents/skills，而 skills/ 是本项目可复用的源目录。
不依赖 Windows 符号链接和外部模型，不接受外部路径输入。
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills"
TARGET = ROOT / ".agents" / "skills"


def mirror_skills(*, check_only: bool) -> list[str]:
    problems = []
    sources = sorted(SOURCE.glob("*/SKILL.md"))
    if not sources:
        raise RuntimeError("缺少任何自有 Agent Skills。")
    known = set()
    for source in sources:
        name = source.parent.name
        if not name.startswith("patent-"):
            raise RuntimeError("技能目录名称未通过约定检查。")
        known.add(name)
        mirrored = TARGET / name / "SKILL.md"
        if not mirrored.is_file() or mirrored.read_bytes() != source.read_bytes():
            problems.append(f"{name}: Codex 自动发现目录缺失或内容未同步")
            if not check_only:
                mirrored.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, mirrored)
    for extra in TARGET.glob("*/SKILL.md"):
        if extra.parent.name not in known:
            problems.append(f"{extra.parent.name}: 存在过期/未登记 Codex 技能")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="检查/更新仓库级简体中文技能镜像")
    parser.add_argument("--check", action="store_true", help="严格检查不写入文件，供 CI 使用")
    args = parser.parse_args()
    try:
        issues = mirror_skills(check_only=args.check)
    except RuntimeError as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 2
    if issues:
        for issue in issues:
            print(issue)
        return 1 if args.check else 0
    print("所有自有 Skills 与 Codex 自动发现目录已同步。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
