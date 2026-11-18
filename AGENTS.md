# Mechanical_Patent agent instructions

Purpose: when given one technical direction, independently search authentic prior art, invent multiple structurally implementable solutions, red-team them and draft a Chinese invention application. This is an R&D workflow, not a legal adviser or an automatic patent filer.

Default workflow:
1. Read README.md, docs/UPSTREAM_AUDIT.md, docs/ARCHITECTURE.md, docs/SECURITY.md.
2. Classify confidentiality. External model and search are disabled without explicit user authorization.
3. Run recorded Chinese/English search terms against authenticated sources; report what was actually checked, the dates and incomplete coverage.
4. Generate mechanically detailed concepts with independent TRIZ/SCAMPER/cross-domain/FMEA/radical roles. Include parts, interactions, parameter bounds, mechanism and counterfactual test.
5. Independently challenge the novel elements; retrieve contrary prior art. Never invent document numbers.
6. Evaluate conservation laws, loads, fluids, hydraulics, thermodynamics, tolerance stack, manufacturability and safety. Label theory, calculations, simulation and experimental results separately.
7. Write a disclosure and application DRAFT using the pinned external Chinese patent-disclosure and patent-application Skills when installed. Compare claims to exact disclosure content.
8. Use china-patent-figure-skill as a separate trusted local service for STEP to figures; never upload unpublished CAD to public image generation.
9. Preserve stage artifacts, citations, unknowns, competing explanations, provenance, source completeness and professional review tasks.
10. No auto-filing. Report source and verification limitations honestly.

Repository engineering:
- Keep vendor-neutral core; no Docker dependency in Lambda/FC function handlers.
- Preserve Python 3.11+ compatibility, zero unpinned external services by default.
- Existing cases are immutable; new runs use new folders. Tests must not require live provider keys or LLM APIs.
- Read upstream LICENSE and exact commit before copying any source. AutoPatent currently has no clearly established reuse license.
- CI tests and review required before PR merge. Do not bypass branch rules or protected requirements.
- Every enhancement should update architecture, privacy policy, contract tests and versioned source provenance.
