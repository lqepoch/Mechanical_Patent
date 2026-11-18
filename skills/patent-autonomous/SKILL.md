---
name: patent-autonomous
description: "输入机械技术问题，自动开展中外专利查新、TRIZ/SCAMPER创新构思、反证检索、工程可行性论证，形成中国发明专利交底及申请草稿，保存证据与审核门禁。"
user-invocable: true
---

# Autonomous Mechanical Patent R&D

Use when the user asks to discover technical inventions, improve a machine/design, evaluate mechanical novelty or draft an invention patent from one technical direction.

## Required inputs

- User's technical problem and application constraints. Assume reasonable parameters where unknown but mark all assumptions.
- Whether unpublished technical details can be sent to external model/search providers.
- Optional CAD/STEP/BOM and existing disclosure references. Never upload private materials without authorization.

## Procedure

1. Read the root AGENTS.md, README.md, docs/ARCHITECTURE.md and docs/UPSTREAM_AUDIT.md.
2. Execute the Mechanical Patent CLI using an authenticated live provider and local OpenAI-compatible model. The CLI returns a research dossier and stage-level JSON.
3. If the provider is unavailable, disclose failure. Imported records are UNVERIFIED. Do not claim global search or novelty.
4. Interpret the five independent generated directions, contrarian evidence, mechanical feasibility equations and uncertainty register.
5. For a Chinese application, if the pinned handsomestWei/patent-disclosure-skill is installed, explicitly dispatch to its patent-disclosure and patent-application subskills. Provide it with the selected candidate, evidence and full engineering source. Its local CNIPA quick scan is only supplemental.
6. If a STEP assembly exists and the PisenAILab china-patent-figure-skill has passed a local environment acceptance check, use that isolated tool for reproducible patent figure generation. Require human part-number and disclosure mapping review.
7. Run independent QA: novelty/inventiveness risk, claim-to-specification traceability, theoretical feasibility, drawing labels, official CNIPA formatting, data confidentiality, provenance and inventor confirmation.
8. Output an evidence-linked prior-art report, full candidate matrix, engineering verification plan, draft disclosure, claims, abstract, description, figure plan and issues list. Filing authorization is always a human action.

## Safety

- WIPO PATENTSCOPE public search is not an authorized scraper source.
- Absent literature results never prove novelty or patentability; abstract-only retrieval is insufficient for full claim mapping.
- Do not invent experiments, calculations, source references or inventors.
- A theoretically implementable idea still needs sufficient technical disclosure and examination for Chinese patent registration.
- No automatic infringement/FTO clearance or legal filing.
