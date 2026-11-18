"""Portable, auditable data contracts shared by search, innovation and drafting."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
from typing import Any
from urllib.parse import urlparse


class PatentWorkflowError(RuntimeError):
    """A failed operation or safety gate. Never silently substitute fake results."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Evidence:
    publication: str
    title: str
    url: str
    source: str
    retrieved_at: str
    abstract: str = ""
    claims: str = ""
    publication_date: str = ""
    jurisdiction: str = ""
    kind: str = "patent"
    verified: bool = False
    pdf_url: str = ""
    paper_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.publication.strip() or not self.title.strip() or not self.source.strip():
            raise ValueError("Evidence must include publication, title and source")
        parsed = urlparse(self.url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Evidence requires a publicly inspectable HTTPS source URL")
        if self.kind not in {"patent", "paper", "standard", "manual", "web"}:
            raise ValueError("Unsupported evidence kind")
        if self.pdf_url and (urlparse(self.pdf_url).scheme != "https" or not urlparse(self.pdf_url).netloc):
            raise ValueError("Discovered PDF URL must be HTTPS")
        if not isinstance(self.paper_metadata, dict):
            raise ValueError("Paper metadata must be a structured object")

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, imported: bool = False) -> Evidence:
        names = cls.__dataclass_fields__
        clean = {k: v for k, v in data.items() if k in names}
        if imported:
            clean["verified"] = False
        return cls(**clean)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evidence_id(evidence: Evidence) -> str:
    return "EV-" + sha256((evidence.kind + "|" + evidence.publication.upper()).encode("utf-8")).hexdigest()[:12].upper()


def deduplicate(records: list[Evidence]) -> list[Evidence]:
    """Keep the most complete version of each document, preserving first-seen order."""
    seen: dict[str, Evidence] = {}
    order: list[str] = []
    for record in records:
        key = evidence_id(record)
        if key not in seen:
            order.append(key)
            seen[key] = record
        elif (record.verified, bool(record.claims), len(record.abstract)) > (
            seen[key].verified, bool(seen[key].claims), len(seen[key].abstract)
        ):
            seen[key] = record
    return [seen[k] for k in order]


def coverage(records: list[Evidence], provider_errors: list[str]) -> dict[str, Any]:
    patents = [r for r in records if r.kind == "patent"]
    verified = [r for r in patents if r.verified]
    return {
        "patents": len(patents),
        "verified_patents": len(verified),
        "patents_with_claims": sum(bool(r.claims.strip()) for r in verified),
        "jurisdictions": sorted(set(r.jurisdiction for r in verified if r.jurisdiction)),
        "provider_errors": provider_errors,
        "global_exhaustiveness_confirmed": False,
        "status": "partial_evidence" if verified else "unverified_or_unavailable",
        "note": "Search results cannot establish worldwide absence of prior art or legal FTO clearance.",
    }


def save_json(path: Path, value: Any) -> str:
    """Atomic replace avoids corrupting dossiers after interruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".tmp-", delete=False) as tmp:
        tmp.write(payload)
        tmp.flush()
        temp = Path(tmp.name)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    return sha256(payload).hexdigest()


def safe_filename(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]", "-", name).strip("-")
    return value[:64] or "case"


def validate_draft(draft: dict[str, Any], records: list[Evidence], idea: dict[str, Any]) -> list[str]:
    """Deterministic documentary gates; no algorithm can determine patentability."""
    issues: list[str] = []
    if not records or not any(x.verified and x.kind == "patent" for x in records):
        issues.append("No source-verified patent records; filing review is blocked.")
    if not any(x.verified and x.kind == "patent" and x.claims.strip() for x in records):
        issues.append("No source-verified patent claims; comparison is abstract-only.")
    title = draft.get("title")
    if not isinstance(title, str) or not title.strip():
        issues.append("Missing title.")
    abstract = draft.get("abstract")
    if not isinstance(abstract, str) or not abstract.strip():
        issues.append("Missing abstract.")
    elif len(abstract) > 300:
        issues.append("Abstract exceeds 300 characters; check official character-counting conventions.")
    claims = draft.get("claims")
    if not isinstance(claims, list) or not claims or not all(isinstance(c, str) and c.strip() for c in claims):
        issues.append("Claims must be a nonempty list of texts.")
    description = draft.get("description")
    expected = ("technical_field", "background", "technical_problem", "technical_solution",
                "beneficial_effects", "embodiments", "drawings")
    if not isinstance(description, dict):
        issues.append("Missing description sections.")
    else:
        for section in expected:
            if not description.get(section):
                issues.append("Missing description section: " + section)
    if not idea.get("mechanism") or not idea.get("enabling_details"):
        issues.append("Inventive mechanism/enabling implementation details remain unspecified.")
    support = draft.get("claim_support")
    if not isinstance(support, list) or len(support) != len(claims or []):
        issues.append("Every claim requires a numbered specification support record.")
    else:
        whole_description = (
            " ".join(str(value) for value in description.values())
            if isinstance(description, dict) else ""
        )
        normalized_description = " ".join(whole_description.split())
        for index, entry in enumerate(support, start=1):
            if not isinstance(entry, dict) or not str(entry.get("specification_passage", "")).strip():
                issues.append(f"Claim {index} lacks a specification passage.")
                continue
            passage = " ".join(str(entry["specification_passage"]).split())
            if passage not in normalized_description:
                issues.append(f"Claim {index} support passage is absent from description.")
    return issues
