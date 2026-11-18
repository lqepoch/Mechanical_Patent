# Codex implementation mandate — Mechanical_Patent

Repository: https://github.com/lqepoch/Mechanical_Patent
Goal: a single natural-language instruction results in a source-auditable global patent research process, multiple original mechanical ideas, independent prior-art challenges, physically plausible implementation paths, and a professionally reviewable Chinese invention patent application draft.

Read all of README.md, AGENTS.md, docs/*, skills/patent-autonomous/SKILL.md and source tests. Start with a repository-wide architecture and license audit. Preserve existing working functionality and Git history. Propose changes as parent/child GitHub Issues, implement on feature branches, run tests, submit PR, and merge only after actual checks and permissions pass.

### Mandatory upstream assessment and adapters

- handsomestWei/patent-disclosure-skill: make its complete CN patent disclosure, claims, specification, drawing description and office action workflow available as independently pinned skill. Its CNIPA quick-scan is additive, not the main global search. Replace parent routing so searching, ideation and drafting run automatically on a one-command request. Keep its guardrails.
- wangziying1004/AutoPatent: learn its checkpoints, stage reports and adversarial Claim Chart feedback, but do not copy source without clear permission.
- joyboseroy/ideaforge: integrate TRIZ, SCAMPER, design thinking and cross-domain synthesis using traceable concept lineage; FalkorDB optional behind a graph interface.
- open1s/trinno: add hypothesis, falsification experiment, evidence classification, stage rollback and reproducible run log.
- PisenAILab/china-patent-figure-skill: local isolated STEP to patent figure adapter with CAD/geometry acceptance test; protect confidential CAD, map BOM/part numbers to claims.
- lianghugjil/patent-template: merge only verified format and document QA checks, with separate configurable nonstatutory preferences.
- patent-client-agents / Patsnap / EPO OPS / CNIPA authorized data / USPTO ODP / BigQuery / licensed WIPO products / OpenAlex: adapters with explicit coverage, terms, quotas, rights, metadata and provenance.

### Proposed parent issue: Autonomous Patent Research Platform

Child 1: Source-provider contracts and live CNIPA+EPO+US+PCT+NPL integration.
- licensed authenticated APIs or bulk feeds; no forbidden public scraping;
- DOI/publication/family dedup, full claims, publication date, patents/nonpatents;
- rate limits, cursors, caching, delta refresh, source outages and API usage accounting;
- bilingual queries, IPC/CPC expansion, citation forward/backward graph;
- evidence IDs include verifiable publication/URL/excerpts; no missing-results novelty claims.

Child 2: Hybrid prior-art retrieval and objective evaluation.
- BM25 + multilingual embeddings + cross-encoder rerank;
- 100+ gold mechanical cases, recall@K, claim-chart precision, bilingual coverage;
- D1/D2 closest prior art, feature-element citations with paragraph/claim anchors.

Child 3: Creativity agents and technical constraints.
- TRIZ, SCAMPER, Design Thinking, FMEA, cross-domain analogy, impossible-idea falsifier;
- concept graph traceability, physical mechanism, boundaries, alternatives;
- explicit novel contribution vs routine substitution vs obvious combination.

Child 4: Engineering verification and CAD.
- analytical loads, stress, energy, pump curves, hydraulics, thermal and tolerance checks;
- units and dimensional consistency; compare calculations/FEA/physical tests;
- SolidWorks Windows-local APIs and STEP/assembly BOM source tracking;
- simulation integration must require real solver execution with reproducible inputs.

Child 5: Contrarian claim-chart / patentability / FTO separation.
- separate inventions from prior art; show motivation to combine; independent reviewer;
- CN three-step inventive-step workflow; FTO scope is territory/time/current claims specific;
- never fabricate an attorney's clearance or a grant prediction.

Child 6: CN disclosure and patent application generation.
- pinned Chinese patent-disclosure-skill and patent-application integration;
- independent/dependent claims, support matrix, enabling embodiments, reference numerals;
- DOCX/PDF/SVG/DXF figure formats, auditable redlines and issue list.

Child 7: Security, tenancy, governance.
- project-level identity, SSO, roles, row-level security, immutable evidence and review trail;
- outbound secrecy gates, no silent cloud upload, provider legal terms, retention and backups;
- names/inventors reflect documented real contribution; CN foreign-filing secrecy checks.

Child 8: Production operations, cross-cloud and observability.
- PostgreSQL/pgvector, object storage abstraction, queue, checkpointed execution;
- AWS Lambda/Alibaba FC thin adapters and common vendor-neutral Python business code;
- replay, retry, rate limit, rollback, idempotency, watchdog, cost/token quotas, tracing;
- production alerts, SLOs, runbooks, disaster recovery, CI/CD, penetration tests.

Child 9: Evaluations and quality engineering.
- offline mocked tests + provider contract tests (no real API credential in CI);
- golden cases, hallucination traps, prompt injection from retrieved patent data,
  falsely verified imported data, unsupported claim wording, model/data outage tests;
- specialist patent attorney and mechanical engineer signoff.

Child 10: Governance for external dependencies and releases.
- record upstream commit SHA, license, security notices and accepted code;
- no automatic import of unlicensed AutoPatent code;
- create PRs with evidence of tests and verify status before merging into main;
- use semantic releases and migration scripts, never silently overwrite case data.

### Release gates

G0: documented source/architecture/licenses and working deterministic tests.
G1: authentic live multi-country evidence retrieval with measured coverage and claims.
G2: independent inventive concepts, physical support and adversarial traceability.
G3: full CN claim/specification/figure dossier with specialist signoff.
G4: confidential enterprise production with SSO, logs, SLA, disaster recovery and CAD adapter.

The code in the first integration implements parts of G0 and selected pieces of G1-G3 only. Do not claim a production-ready release before all gates are verified. Keep implementation and tests synchronized.

### Non-negotiable output contract

Every generated patent dossier includes:
A. exact original request, classification and confidentiality decision;
B. source list, retrieval timestamps, search syntax, pagination and coverage holes;
C. prior patents, claims / excerpt anchors and counterevidence;
D. multi-method invention alternatives, mechanism, distinguishing features and rationale;
E. equations with units, theoretical assumptions, physical model, test plan and faults;
F. claim-element support table and draft CN application, including figure plan;
G. open issues, failed steps, legal qualifications, human signoff and file hashes.

No fabricated publication, citation, measurement or patent status. Never automatically submit an application.
