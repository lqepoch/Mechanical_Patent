# Security and legal controls

Data classes: PUBLIC, LICENSED, INTERNAL, SECRET, CONTROLLED. Patent drafts, not-yet-filed inventions, SolidWorks assemblies and internal BOM should default to SECRET until reviewed. Search terms can disclose invention direction even when patent contents are public.

Current protections: external LLM requires explicit opt-in and HTTPS, outbound patent search requires explicit opt-in, imported patent documents cannot be marked provider-verified, model data and fetched source excerpts are treated as untrusted, stage files are written to a private per-case directory, no deployment secrets are stored in Git, and no automatic filing is implemented.

Additional production controls to build:
- company SSO, RBAC+ABAC project/team security, tenant isolation, PostgreSQL RLS, approval separation of duties;
- classification/redaction layer and DLP audit prior to every model/search egress;
- credential rotation, egress allowlists, API quotas, retry/backoff, circuit breakers and rate-limit accounting;
- hashes, provenance, timestamps, model/prompt versions, content revisioning and append-only legally defensible audit history;
- SBOM, SAST, DAST, dependency pins, protected branch/CI checks and licensing review;
- lifecycle retention, privacy, legal hold and deletion policy for confidential inventions;
- patent ownership, inventorship and foreign-filing security reviews; independently reviewed FTO;
- explicit terms-of-service review for CNIPA, WIPO, EPO, commercial providers and standards.

Risks present in this first implementation: no real tenant ACL, no distributed lock, no automated provider retry/backoff, initial XML parser has not been live contract-tested, EPO-only searching has major scope limits, draft checker has superficial textual support checks, model output can still hallucinate engineering or citations, and no verified complete DOCX submission package exists. These are tracked rollout blockers.
