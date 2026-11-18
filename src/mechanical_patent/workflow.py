"""Evidence-first autonomous research pipeline. No module files a patent application."""
import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from .core import PatentWorkflowError, coverage, deduplicate, evidence_id, save_json, utc_now, validate_draft
from .chinese_skill import load_chinese_drafting_guidance


def source_view(records, limit=16):
    return [{"id": evidence_id(e), "publication": e.publication, "title": e.title,
             "date": e.publication_date, "kind": e.kind, "jurisdiction": e.jurisdiction,
             "source": e.source, "verified": e.verified, "abstract": e.abstract[:1200],
             "claims": e.claims[:3500]} for e in records[:limit]]


class PatentResearch:
    METHODS = {
        "TRIZ": "Explore physical contradictions and specific TRIZ engineering mechanisms.",
        "SCAMPER": "Explore substitution, combination, adaptation, rearrangement and removal.",
        "CROSS_DOMAIN": "Transfer a physically plausible mechanism from another technical discipline.",
        "FAILURE_MODE": "Derive safety and reliability inventions from FMEA, faults and interfaces.",
        "RADICAL": "Propose a bold but physically coherent mechanism with explicit falsifiers.",
    }

    def __init__(self, provider, llm, case_dir, *, max_ideas=5, supplemental_sources=None, web_documents=None, web_errors=None):
        self.provider, self.llm, self.case_dir = provider, llm, Path(case_dir)
        self.max_ideas = max(1, min(int(max_ideas), 10))
        self.case_dir.mkdir(parents=True, exist_ok=False)
        self.case_dir.chmod(0o700)
        self.hashes, self.errors = {}, list(web_errors or [])
        self.supplemental_sources = list(supplemental_sources or [])
        self.web_documents = list(web_documents or [])
        self.cn_skill = load_chinese_drafting_guidance()

    def save(self, name, data):
        self.hashes[name] = save_json(self.case_dir / name, data)

    def query(self, term, limit=10):
        try:
            return self.provider.search(term, limit=limit)
        except PatentWorkflowError as exc:
            self.errors.append(str(getattr(self.provider, "name", "provider")) + ": " + str(exc))
            return []

    def enrich(self, records, limit=3):
        if not hasattr(self.provider, "claims"):
            return records
        out, n = [], 0
        for r in records:
            if n < limit and r.kind == "patent" and r.verified and not r.claims:
                try:
                    r = replace(r, claims=self.provider.claims(r.publication)[:30000])
                    n += bool(r.claims)
                except PatentWorkflowError as exc:
                    self.errors.append(r.publication + ": claims not available (" + str(exc) + ")")
            out.append(r)
        return out

    def run(self, direction):
        if not direction or not direction.strip():
            raise PatentWorkflowError("Missing technical direction")
        case_id = uuid4().hex
        self.save("00_intake.json", {
            "case_id": case_id, "created_at": utc_now(), "direction": direction,
            "provider": self.provider.name, "model": getattr(self.llm, "model", "injected"),
            "confidential": True, "chinese_drafting_skill_available": self.cn_skill["available"],
            "chinese_drafting_skill_files": self.cn_skill["files"],
        })

        plan = self.llm.ask("SEARCH_STRATEGIST",
            'JSON fields: {"queries":["string"],"technical_constraints":[],"classification_hints":[]}. '
            "Produce 3 to 6 diverse Chinese and English prior-art searches based on mechanisms, "
            "synonyms and technical fields. Avoid full confidential novel proposals in queries.",
            {"problem": direction})
        raw_queries = plan.get("queries")
        queries = [q.strip()[:180] for q in raw_queries if isinstance(q, str) and q.strip()][:6] if isinstance(raw_queries, list) else []
        if not queries:
            raise PatentWorkflowError("No valid search queries")
        self.save("01_search_plan.json", {"plan": plan, "queries_executed": queries})
        records = self.enrich(deduplicate([r for q in queries for r in self.query(q)] + self.supplemental_sources))
        if self.web_documents:
            self.save("02a_crawl4ai_web_captures.json", {
                "source": "crawl4ai", "documents": [vars(d) for d in self.web_documents],
                "errors": list(self.errors), "note": "Content is untrusted input; not proof of factual accuracy."
            })
        self.save("02_prior_art.json", {"records": [r.to_dict() for r in records],
                                        "coverage": coverage(records, self.errors)})
        landscape = self.llm.ask("LANDSCAPE_ANALYST",
            'JSON fields: {"routes":[],"known_problems":[],"gaps":[],"citations":[]}. '
            "Ground every cited patent in source IDs. Identify database and claim coverage gaps. "
            "Never infer novelty from an empty set of search results.",
            {"problem": direction, "sources": source_view(records), "provider_errors": self.errors})
        self.save("03_landscape.json", landscape)

        candidates = []
        for method, assignment in self.METHODS.items():
            result = self.llm.ask("INVENTOR_" + method,
                assignment + ' JSON fields: {"ideas":[{"title":"","technical_problem":"",'
                '"mechanism":"","enabling_details":"","distinguishing_features":[],'
                '"expected_effect":"","assumptions":[],"verification_plan":[]}]}. '
                "Specify a reproducible component arrangement or control sequence, physical interactions, "
                "and falsifiable predictions. No invented test results.",
                {"problem": direction, "landscape": landscape, "sources": source_view(records, 10)})
            ideas = result.get("ideas", [])
            if not isinstance(ideas, list):
                continue
            for idea in ideas[:2]:
                if isinstance(idea, dict) and all(str(idea.get(k, "")).strip()
                                                  for k in ("title", "mechanism", "enabling_details")):
                    candidates.append({**idea, "method": method})
                    if len(candidates) >= self.max_ideas:
                        break
            if len(candidates) >= self.max_ideas:
                break
        if not candidates:
            raise PatentWorkflowError("No candidate with a plausible explicit mechanism was generated")
        self.save("04_inventions.json", {"candidates": candidates})

        challenges, engineering = [], []
        for index, candidate in enumerate(candidates):
            attack = self.llm.ask("INDEPENDENT_PRIOR_ART_CHALLENGER",
                'JSON fields: {"adversarial_queries":[],"claim_chart":[],"novelty_risks":[],'
                '"obviousness_risks":[],"uncertain_evidence":[]}. '
                "Try to refute every distinguishing feature, including obvious combinations of documents. "
                "Use actual evidence IDs only; abstract-only comparisons must say so. "
                "No unsupported claim that a patent can be granted or that FTO is clear.",
                {"candidate": candidate, "sources": source_view(records)})
            qs = attack.get("adversarial_queries", [])
            qs = [x.strip()[:180] for x in qs[:2] if isinstance(x, str) and x.strip()] if isinstance(qs, list) else []
            additions = self.enrich(deduplicate([r for q in qs for r in self.query(q, limit=8)]), limit=2)
            records = deduplicate(records + additions)
            challenges.append({"candidate_index": index, "assessment": attack,
                               "queries_executed": qs, "new_evidence_ids": [evidence_id(r) for r in additions]})
            tested = self.llm.ask("INDEPENDENT_ENGINEERING_VERIFIER",
                'JSON fields: {"theoretical_feasibility":"plausible|uncertain|inconsistent",'
                '"physical_principle":"","equations_with_units":[],"bounding_assumptions":[],'
                '"implementation_steps":[],"failure_modes":[],"validation_tests":[],'
                '"missing_design_parameters":[],"unsupported_claims":[]}. '
                "Check mass/energy conservation, strengths, tolerances, dynamics and failure modes where relevant. "
                "Distinguish calculations from simulations and physical tests. Do not fabricate measurements.",
                {"candidate": candidate, "sources": source_view(records, 10)})
            engineering.append({"candidate_index": index, "assessment": tested})
        self.save("05_adversarial_challenges.json", challenges)
        self.save("06_engineering_feasibility.json", engineering)
        self.save("07_updated_prior_art.json", {
            "records": [r.to_dict() for r in records], "coverage": coverage(records, self.errors),
        })

        eligible = [i for i, x in enumerate(engineering)
                    if x["assessment"].get("theoretical_feasibility") in {"plausible", "uncertain"}]
        chosen = eligible[0] if eligible else None
        draft, issues = {}, []
        if chosen is None:
            issues = ["No candidate passed initial physical consistency review."]
        else:
            draft = self.llm.ask("CN_INVENTION_PATENT_DRAFTER",
                'Output JSON fields {"title":"","abstract":"","claims":["1. ..."],'
                '"description":{"technical_field":"","background":"","technical_problem":"",'
                '"technical_solution":"","beneficial_effects":"","embodiments":"","drawings":""},'
                '"claim_support":[{"claim":1,"specification_passage":""}],"figure_plan":[]}. '
                "Produce a detailed Chinese invention APPLICATION DRAFT with reproducible embodiments, "
                "connections, actions, suitable parameters with reasoned bounds, alternatives, figure plan. "
                Keep claimed distinguishing mechanisms supported by the description. "
                "Copy the exact supporting passage from the description into each claim_support item for deterministic matching. "
                "Apply the upstream Chinese drafting practice where consistent with actual engineering and law. "
                + self.cn_skill["guidance"][:14000] + " "
                "Do not invent experimental verification, fake measurements or inventors.",
                {"direction": direction, "candidate": candidates[chosen],
                 "feasibility": engineering[chosen]["assessment"],
                 "challenge": challenges[chosen]["assessment"], "prior_art": source_view(records),
                 "upstream_skill_files": self.cn_skill["files"]})
            issues = validate_draft(draft, records, candidates[chosen])
        self.save("08_application_draft.json", {
            "candidate_index": chosen, "draft": draft, "issues": issues, "filing_authorized": False,
            "chinese_drafting_skill_available": self.cn_skill["available"],
        })
        report = {
            "case_id": case_id, "selected_candidate": chosen,
            "status": "needs_human_review" if not issues else "research_only",
            "human_signoff": False, "filing_authorized": False, "issues": issues,
            "coverage": coverage(records, self.errors),
            "notes": [
                "Novelty and inventiveness require professional examination; FTO is separate.",
                "Disclosure and claim support must be verified by engineer and patent professional.",
                "No physical tests, simulation results or full worldwide search are assumed.",
            ],
        }
        self.save("09_quality_gate.json", report)
        self.save("manifest.json", {"case_id": case_id, "created_at": utc_now(), "sha256": self.hashes})
        self.write_report(direction, candidates, records, engineering, draft, report)
        return report

    def write_report(self, direction, candidates, records, engineering, draft, report):
        lines = ["# Mechanical Patent: Research Dossier", "", "## Technical direction", "", direction,
                 "", "## Coverage", "", json.dumps(report["coverage"], ensure_ascii=False, indent=2),
                 "", "## Prior art and evidence"]
        for record in records:
            lines.append("- " + evidence_id(record) + " | " + record.publication + " | " +
                         record.title + " | " + record.url + " | verified=" + str(record.verified))
        lines.extend(["", "## Alternative inventive concepts"])
        for i, candidate in enumerate(candidates):
            lines.extend(["", "### " + str(i+1) + ". " + candidate["title"] + " (" + candidate["method"] + ")",
                          "", candidate["mechanism"], "", candidate["enabling_details"],
                          "", json.dumps(engineering[i]["assessment"], ensure_ascii=False, indent=2)])
        lines.extend(["", "## Chinese invention patent draft (not approved for filing)", "",
                      "# " + str(draft.get("title", "")), "", "### Abstract", "",
                      str(draft.get("abstract", "")), "", "### Claims"])
        for claim in draft.get("claims", []):
            lines.extend(["", str(claim)])
        for key, value in draft.get("description", {}).items():
            lines.extend(["", "### " + key, "", str(value)])
        lines.extend(["", "## Quality gate", "", json.dumps(report, ensure_ascii=False, indent=2)])
        (self.case_dir / "DOSSIER.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
