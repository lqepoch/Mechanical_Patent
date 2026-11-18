"""Model-free literature research and case artifacts for agent-native AI clients.

ChatGPT, Codex and other assistants perform creativity, argumentation and drafting.
Python only fetches source documents, structures evidence and checks artifacts.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from .core import (
    Evidence, PatentWorkflowError, coverage, deduplicate, evidence_id,
    save_json, utc_now, validate_draft,
)


def _bounded_terms(terms: list[str] | None) -> list[str]:
    if not terms:
        return []
    unique: list[str] = []
    for term in terms:
        if not isinstance(term, str) or not term.strip():
            continue
        normalized = term.strip()[:240]
        if normalized not in unique:
            unique.append(normalized)
    if len(unique) > 8:
        raise PatentWorkflowError("Limit each evidence search channel to eight distinct queries.")
    return unique


def _stored_records(path: Path) -> list[Evidence]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise PatentWorkflowError(f"Invalid evidence file: {path.name}")
    return [Evidence.from_dict(item) for item in data["records"]]


def _candidate_template() -> dict[str, Any]:
    return {
        "status": "awaiting_agent",
        "candidates": [],
        "required_fields": [
            "title", "technical_problem", "mechanism", "enabling_details",
            "distinguishing_features", "expected_effect", "assumptions",
            "evidence_ids", "falsification_tests", "inventive_method",
        ],
        "instruction": "AI fills candidates after examining BOTH patent and paper evidence. No invented results.",
    }


def _review_template() -> dict[str, Any]:
    return {
        "status": "awaiting_agent",
        "technical_risk": [],
        "inventive_step_three_step_analysis": [],
        "claim_charts": [],
        "countersearch_queries": [],
        "source_anchors": [],
    }


def _feasibility_template() -> dict[str, Any]:
    return {
        "status": "awaiting_agent",
        "physical_principle": "",
        "equations_and_units": [],
        "assumptions": [],
        "design_constraints": [],
        "failure_modes": [],
        "falsification_tests": [],
        "verification_status": "hypothesis_only",
        "note": "No calculated, simulated or measured result is assumed.",
    }


def _application_template() -> dict[str, Any]:
    return {
        "status": "awaiting_agent",
        "draft": None,
        "source_instructions": "Follow pinned Chinese patent-disclosure-skill and claim-to-description rules.",
        "submission_authorized": False,
    }


class PatentResearch:
    """Only deterministic research tools; the invoking AI uses case artifacts as context."""

    def __init__(self, patent_provider: Any | None, paper_providers: list[Any],
                 case_dir: Path, *, supplemental_sources: list[Evidence] | None = None,
                 web_documents: list[Any] | None = None, web_errors: list[str] | None = None):
        self.patent_provider = patent_provider
        self.paper_providers = paper_providers
        self.case_dir = Path(case_dir)
        self.case_dir.mkdir(parents=True, exist_ok=False)
        try:
            self.case_dir.chmod(0o700)
        except OSError:
            pass
        self.other_sources = list(supplemental_sources or [])
        self.web_documents = list(web_documents or [])
        self.errors: list[str] = list(web_errors or [])
        self.hashes: dict[str, str] = {}

    def save(self, name: str, value: Any) -> None:
        self.hashes[name] = save_json(self.case_dir / name, value)

    def _collect(self, provider: Any, queries: list[str], kind: str, limit: int) -> list[Evidence]:
        records: list[Evidence] = []
        for query in queries:
            try:
                found = provider.search(query, limit=limit)
                records.extend(e for e in found if e.kind == kind)
            except (PatentWorkflowError, ValueError, OSError) as exc:
                self.errors.append(f"{provider.name} query '{query[:60]}': {exc}")
        return deduplicate(records)

    def _enrich_claims(self, records: list[Evidence]) -> list[Evidence]:
        if self.patent_provider is None or not hasattr(self.patent_provider, "claims"):
            return records
        from dataclasses import replace
        result = []
        retrieved = 0
        for item in records:
            if item.verified and not item.claims and retrieved < 5:
                try:
                    raw = self.patent_provider.claims(item.publication)
                    if raw.strip():
                        item = replace(item, claims=raw[:50000])
                        retrieved += 1
                except (PatentWorkflowError, OSError) as exc:
                    self.errors.append(f"Claims {item.publication}: {exc}")
            result.append(item)
        return result

    def run(self, direction: str, patent_queries: list[str] | None = None,
            paper_queries: list[str] | None = None, *, limit: int = 10,
            case_id: str | None = None) -> dict[str, Any]:
        if not direction or not direction.strip():
            raise PatentWorkflowError("Technical direction is required.")
        pq = _bounded_terms(patent_queries)
        lq = _bounded_terms(paper_queries)
        case_id = case_id or uuid4().hex
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", case_id):
            raise PatentWorkflowError("案卷编号须由字母、数字、下划线和连字符组成。")
        self.save("00_intake.json", {
            "case_id": case_id, "direction": direction, "created_at": utc_now(),
            "workflow": "agent_native", "llm_api_required": False,
            "patent_provider": getattr(self.patent_provider, "name", "not_configured"),
            "paper_providers": [x.name for x in self.paper_providers],
            "confidentiality": "unpublished_by_default",
        })
        self.save("01_search_plan.json", {
            "patent_queries": pq, "paper_queries": lq,
            "next_queries_to_derive": ["IPC/CPC expansion", "citations", "technical synonyms",
                                       "cross-industry analogies", "countersearch"],
            "note": "Queries are supplied by the invoking AI; tools do not call an LLM.",
        })

        patents = self._collect(self.patent_provider, pq, "patent", limit) if self.patent_provider and pq else []
        patents = self._enrich_claims(patents)
        papers = []
        if lq:
            for provider in self.paper_providers:
                papers.extend(self._collect(provider, lq, "paper", limit))
        papers = deduplicate(papers)
        self.save("02_patents.json", {
            "records": [x.to_dict() for x in patents],
            "coverage": coverage(patents, self.errors),
            "provider_queries": pq,
        })
        self.save("03_papers.json", {
            "records": [x.to_dict() for x in papers],
            "metadata_verified": sum(x.verified for x in papers),
            "with_abstract": sum(bool(x.abstract.strip()) for x in papers),
            "full_text_verified": 0,
            "provider_queries": lq,
            "limitation": "DOI metadata and optional abstracts are not a verification of entire paper full text.",
        })
        all_records = deduplicate(patents + papers + self.other_sources)
        self.save("04_evidence.json", {
            "records": [x.to_dict() for x in all_records],
            "counts_by_kind": {
                kind: sum(x.kind == kind for x in all_records)
                for kind in ("patent", "paper", "web", "standard", "manual")
            },
            "source_errors": list(self.errors),
            "coverage_limitation": "No search can confirm global absence of prior art.",
        })
        if self.web_documents:
            docs = []
            for d in self.web_documents:
                docs.append({
                    "url": d.url, "title": d.title, "retrieved_at": d.retrieved_at,
                    "sha256": d.content_sha256,
                    "content": d.markdown[:20000], "trust": "untrusted_web_content",
                })
            self.save("04a_crawl4ai.json", {"documents": docs})
        self.save("05_inventions.json", _candidate_template())
        self.save("06_countersearch.json", _review_template())
        self.save("07_engineering.json", _feasibility_template())
        self.save("08_application.json", _application_template())
        quality = {
            "status": "awaiting_agent_and_human_review",
            "filing_authorized": False, "human_signoff": False,
            "patent_claims_available": sum(bool(x.claims) and x.verified for x in patents),
            "papers_discovered": len(papers),
            "search_errors": list(self.errors),
            "blockers": [
                "Agent must generate invention candidates, challenge them and draft supported claims.",
                "Engineer must review theoretical implementation and actual experimental evidence.",
                "Patent professional must review novelty, inventiveness, disclosure, inventorship and filing.",
            ],
        }
        self.save("09_quality_gate.json", quality)
        from .lineage import build_case_graph
        from .audit import append_audit_event, verify_audit_chain
        graph = build_case_graph(self.case_dir)
        self.hashes["04b_technology_graph.json"] = sha256(
            (self.case_dir / "04b_technology_graph.json").read_bytes()
        ).hexdigest()
        append_audit_event(
            self.case_dir, stage="任务接收", action="完成双源基础检索与案卷建立",
            actor="系统工具", role="系统",
            payload={"case_id": case_id, "patent_count": len(patents),
                     "paper_count": len(papers), "source_errors": len(self.errors)},
        )
        self.save("manifest.json", {
            "case_id": case_id, "sha256": self.hashes, "generated_at": utc_now(),
            "audit_chain_head": verify_audit_chain(self.case_dir)["head_sha256"],
        })
        self._write_agent_handoff(direction, patents, papers, quality)
        return quality

    def _write_agent_handoff(self, direction: str, patents: list[Evidence],
                             papers: list[Evidence], quality: dict[str, Any]) -> None:
        lines = [
            "# Agent research handoff", "",
            "**AI client (ChatGPT, Codex or compatible host) now continues the task. "
            "No LLM inference API or local model required by this repository.**",
            "", "## User problem", "", direction,
            "", "## Patent results", "",
        ]
        for e in patents:
            lines.append(f"- [{evidence_id(e)}] {e.publication}, {e.title}; {e.url} "
                         f"(source={e.source}, claims={'yes' if e.claims else 'no'}, verified={e.verified})")
        lines.extend(["", "## Academic paper results", ""])
        for e in papers:
            lines.append(f"- [{evidence_id(e)}] {e.title}; {e.url} "
                         f"(source={e.source}, abstract={'yes' if e.abstract else 'no'})")
        lines.extend([
            "", "## Actions for the AI currently reading this repository", "",
            "1. Evaluate missing patents, papers, languages, IPC/CPC codes and publication dates.",
            "2. Execute additional search queries and follow citation/DOI trails as necessary.",
            "3. Mine papers for transferable physical principles; contrast with patent claim features.",
            "4. Generate independent TRIZ, SCAMPER, FMEA, cross-domain and radical concepts.",
            "5. For EACH candidate, reverse-search patent claims AND non-patent scientific literature.",
            "6. Form a concrete mechanically reproducible design, assumptions, safety and falsification tests.",
            "7. Write the candidate, countersearch, engineering and China application JSON files.",
            "8. Call 'mechanical-patent validate --case-dir <this directory>' and resolve blockers.",
            "9. Have a real engineer and patent professional approve before any filing.",
            "", "## Limitations", "", json.dumps(quality, ensure_ascii=False, indent=2),
        ])
        (self.case_dir / "AGENT_NEXT_STEPS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_case(case_dir: Path) -> dict[str, Any]:
    """执行企业级确定性质检，保存证据关联报告和本地审计事件。"""
    from .quality import audit_research_case
    return audit_research_case(case_dir)
