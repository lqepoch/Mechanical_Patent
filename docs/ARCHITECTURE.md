# Mechanical_Patent — target architecture

## Goal and acceptance statement

One instruction triggers: requirements understanding, CN and global patent/NPL search, prior art expansion, mechanical innovation by diverse methods, adversarial reverse search, physical/engineering assessment, Chinese invention disclosure and application draft, systematic QA and reviewer signoff.

A typical request is: "Propose novel self-priming solutions for high-altitude firefighting pumps; search worldwide; verify physically, draft Chinese claims, embodiments and figure plans."

## Trust boundaries

PRIVATE: user instructions, SolidWorks models, bills of materials, unpublished designs, internal simulation reports.
PUBLIC/LICENCED: patent publication metadata/full text, published paper metadata, standards subject to license.
LLM EGRESS: local/private-model gateway by default; external call only with explicit approval and data-classification check.
SEARCH EGRESS: only sanitized nonsecret keywords, with explicit approval and provider audit. No scraping WIPO public PATENTSCOPE.
DELIVERY: draft artifact; legal review, inventor confirmation, application approval, CN overseas confidentiality examination when applicable.

## Target service modules

- Patent Orchestrator: task graph with immutable evidence IDs, checkpoints, budget caps, retries, idempotency, case revision graph.
- Search Planner: Mandarin/English synonyms, IPC/CPC families, patent and NPL query variants, citation expansion and iterative recall.
- Search Gateway: EPO OPS, CNIPA licensed/open data, WIPO licensed products, USPTO open data, Google Patents BigQuery, Patsnap licensed connector and OpenAlex/Crossref NPL. Each connector yields a normalized source with publication date, URLs and provider completeness.
- Corpus: PostgreSQL row-level tenant security, JSONB facts; object storage for licensed originals; pgvector + BM25 for hybrid search. If FalkorDB is introduced, it is a derived explainable concept graph and not the evidence source of truth.
- Specialist Ideation: independent TRIZ, SCAMPER, cross-domain analogical reasoning, FMEA and physically radical concepts, plus multidisciplinary peer review.
- Prior Art Challenger: claim-element decomposition, evidence anchors, combination motivation and secondary non-patent sources. FTO separate from novelty/inventiveness.
- Mechanical Verifier: dimensions, tolerances, mechanism degrees of freedom, heat transfer, fluid performance, force/strength, energy conservation; analytical estimates and explicit simulation/bench test plans.
- CAD Tool Gateway: SolidWorks API (Windows-local licensed execution), STEP export, optional geometric 2D/3D figures via isolated PisenAILab service. Model revisions referenced by SHA-256 and controlled PLM revision IDs.
- CN Drafting: handoff to pinned handsomestWei patent-disclosure-skill for disclosure, independent/dependent claims, description, summary and figure legend; upstream must not silently expand claims beyond disclosed embodiments.
- QA/Legal: independent reviewers, claim-to-description support, figure symbol consistency, sufficient disclosure, uncertainty register, confidentiality and ownership checks.
- Observability: trace IDs, token and data API budgets, provider error rates, retrieval coverage, model versions, decisions, signoffs and immutable audit records.

## State machine

CREATED -> CONFIDENTIALITY_REVIEWED -> SEARCH_PLANNED -> SEARCHED_PARTIAL
  -> LANDSCAPE -> MULTI_IDEATION -> COUNTERSEARCH -> PHYSICS_FEASIBILITY
  -> CLAIM_STRATEGY -> CN_DRAFT -> QUALITY_REVIEW -> ENGINEER_APPROVED
  -> PATENT_PROFESSIONAL_APPROVED -> READY_FOR_MANUAL_FILING

Any missing genuine source, unsupported claim, physically inconsistent mechanism, invalid data-rights assumption or confidentiality concern returns to a previous stage with issue tracking. Every stage creates a content hash and source provenance. No automated filing.

## Current executable slice

Included today: structured evidence, EPO OPS OAuth/bibliographic/claims client, imported corpus with unverified marker, independent five-method ideation, adversarial query generation, independent engineering LLM review, Chinese application drafting JSON/Markdown, privacy gates, test suite and stage digests.

Not yet implemented: CNIPA bulk feed, WIPO licensed feed, Patsnap account connector, full global family/citation normalization, dedicated hybrid retrieval, actual physics solver, CAD viewer/STEP geometry, DOCX/PDF examiner-quality export, database tenancy, queue/orchestrator HA, production SLAs, monitoring, 2-person filing approvals. Build these before treating the platform as enterprise production-ready.

## Vendor-neutral cloud deployment

Domain services communicate through OpenAPI/event contracts and use Postgres/object storage/queue abstractions. Functions use Python handler adapters that are separate for AWS Lambda and Alibaba Cloud FC; code logic is shared without packaging in Docker. Deployment manifests map a single semantic specification to AWS CloudFormation/SAM and Alibaba ROS/FC3; platform-specific IAM and event wiring cannot be identical. Long processes use checkpointed job workers; Lambda/FC should only enqueue/resume, not hold a multi-hour invention task open. Secrets are stored in managed provider-native stores or approved corporate secret systems and never in Git.

## Engineering acceptance metrics

- Search source coverage recorded by database, time interval, jurisdiction, claims/text availability and partial errors.
- Evidence documents have identifiers, linkable original source and exact excerpts when present; no invented patent IDs.
- Expert-reviewed recall@K and claim-chart precision over a frozen 100-case Chinese mechanical patent benchmark.
- Engineering reviewers can reproduce all equations, units, design boundary assumptions and test plans.
- Safety gates block filing when evidence/claim support is missing, and audits are immutable.
- Data confidentiality, user/tenant authorization, rollback, quotas, provider outages and deterministic test fixtures are tested under CI.
