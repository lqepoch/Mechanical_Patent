"""Vendor-pinned Chinese patent skill writing rules used by the automatic drafter.

The upstream Skill has workflow-specific instructions and preferences. Only the
applicable drafting rules are read into a bounded prompt; statutory requirements
are independently verified by a qualified human.
"""
from pathlib import Path
from typing import Any

from .core import PatentWorkflowError


BASE_DIR = Path(__file__).resolve().parents[2]
UPSTREAM_PATH = BASE_DIR / "external" / "patent-disclosure-skill"
SKILL_FILES = (
    "skills/patent-application/prompts/guardrails.md",
    "skills/patent-application/prompts/claim_strategy.md",
    "skills/patent-application/prompts/claims_builder.md",
    "skills/patent-application/prompts/specification_builder.md",
    "skills/patent-application/prompts/consistency.md",
)


def load_chinese_drafting_guidance(root: Path | None = None, *, limit: int = 18000) -> dict[str, Any]:
    base = Path(root) if root is not None else UPSTREAM_PATH
    # A recursive checkout with 'git submodule update --init --recursive' is required.
    parts = []
    loaded = []
    for relative in SKILL_FILES:
        path = base / relative
        if not path.is_file() or path.is_symlink():
            continue
        raw = path.read_text(encoding="utf-8")
        # Prevent a huge prompt from masking primary source evidence or user instructions.
        snippet = raw[: min(4000, max(0, limit - sum(len(p) for p in parts)))]
        if not snippet:
            break
        parts.append("UPSTREAM SOURCE: " + relative + "\n" + snippet)
        loaded.append(relative)
    return {
        "upstream": "handsomestWei/patent-disclosure-skill",
        "available": bool(parts),
        "files": loaded,
        "guidance": "\n\n".join(parts)[:limit],
        "notes": (
            "Upstream template preferences are advisory and must not override Chinese patent "
            "law, original engineering facts or independent human claim review."
        ),
    }
