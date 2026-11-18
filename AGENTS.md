# Mechanical_Patent — authoritative agent instructions

## Identity and execution environment

YOU, the invoking ChatGPT / Codex / supported agent, are the reasoning engine. The repository ships prompts, Agent Skills, legal/engineering review rules, data adapters and deterministic Python tools. Do not request PATENT_LLM_BASE_URL, PATENT_LLM_MODEL, Ollama, Qwen model servers, OpenAI API keys or any external LLM inference API. Use the user's current AI client.

A local repo can be read/executed by Codex and other coding agents with filesystem access. A ChatGPT web conversation needs the repository exposed through an accessible GitHub connector or supported Work workflow; a download on a separate computer is not automatically visible to ChatGPT. If the host cannot execute the CLI, use its available research tools and produce the same evidence-linked artifacts in conversation or via authorized GitHub actions. Dot automation and connectors depend on account capabilities and must not be presumed.

## One-command default task

When requested to research a technical direction and write an invention patent, execute the complete research, invention and drafting process without repeated user prompts, except disclosure authorization, inventor facts and unavoidable legal decisions.

1. Classify confidentiality. Distinguish publicly shareable search terms from secret design parameters. Do not upload unpublished CAD/BOM or confidential invention details to external services without explicit permission. Remote search terms can disclose R&D direction.
2. Build a DUAL literature search plan BEFORE drafting:
   - Patent: Chinese and English synonyms; CNIPA authorized products, EPO OPS, USPTO ODP, Google Patents/BigQuery, WIPO licensed PCT data; IPC/CPC, full claims, citation expansion and patent family dedup.
   - Papers and scientific technical literature: OpenAlex, Crossref, arXiv and scholarly publishers where permitted. Use DOI and publication date, abstract, full text with rights review; HTML extraction uses Crawl4AI.
   - Search both literature types whenever tools permit; record queries, exact provider, source URLs, dates, partial errors, missing database coverage.
3. Analyze and compare closest existing patent claim elements, available scientific methods, contradictions and unresolved engineering gaps. Papers can be prior art too.
4. Generate independent invention candidates using TRIZ, SCAMPER, Design Thinking, FMEA, cross-domain physical analogy and ambitious mechanically coherent hypotheses. Record mechanism, components, interfaces, dimensional/physical constraints, alternatives, predicted effects and falsification tests.
5. Reverse-search EACH candidate using BOTH patents and papers. Produce evidence-backed claim charts and obviousness challenges. Reject or narrow ideas with unsupported distinctions. Keep inventiveness separate from FTO.
6. Physically assess mechanics, hydraulic flow/NPSH, strength, kinematics, heat/energy, manufacturability, tolerances and safety as applicable. Distinguish theoretical estimates, solver simulations and measured experiments. Do not manufacture evidence.
7. Draft Chinese invention patent disclosure, independent and dependent claims, enabling embodiments, abstract and drawing plan. Read the pinned Chinese upstream subskills in external/patent-disclosure-skill when checked out. For STEP drawings use the isolated upstream china-patent-figure-skill only with actual model access.
8. Review claim-to-specification support, numbered source evidence, sufficient disclosure, formal requirements, inventor identity, ownership, confidentiality, foreign filing security. No automatic filing or legal guarantee.

## Tool execution

Requires Python 3.11+. No LLM provider credentials.

    python -m pip install -e .
    python -m mechanical_patent research --direction "机械技术问题" \
      --patent-query "inlet pressure control" \
      --paper-query "pump cavitation hydrodynamics" \
      --allow-search-exposure --case-dir cases/example-unique

After explicit authorization, scholarly metadata defaults to OpenAlex and Crossref. EPO OPS can run automatically only if EPO_OPS_CLIENT_ID and EPO_OPS_CLIENT_SECRET are configured. Otherwise, note missing patent source and use native ChatGPT/other agent web/connector search, preserving all citations. For no-network preparation omit the search queries and permission flag.

To validate AI-authored case files:

    python -m mechanical_patent validate --case-dir cases/example-unique

Read skills/patent-autonomous/SKILL.md, skills/patent-paper-search/SKILL.md, docs/AI_CLIENTS.md, docs/DUAL_LITERATURE.md and CODEX_EXECUTION_PROMPT.md. Never label mocked or imported data as live patents or papers.

## Engineering rules

- Vendor-neutral domain Python for AWS Lambda and Alibaba FC with distinct cloud entrypoints; no Docker requirement.
- Crawl4AI only for permitted HTML content. Patent and academic official APIs remain dedicated data connectors. Never bypass CAPTCHA/paywalls/robots.
- Preserve pinned MIT/Apache source, LICENSE/NOTICE and upstream SHAs; do not copy unlicensed AutoPatent code.
- Keep offline mock-based CI, immutable case histories and source hashes, consistent schema, provider error handling and retrieval budgets.
- Implement on PR branches, verify checks and review before merging.
