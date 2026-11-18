# Upstream source audit — 2026-11-18

This assessment is based on inspected GitHub repository contents and should be revalidated at upgrade time. No code is vendored.

| Upstream | Inspected evidence | Decision / constraint |
|---|---|---|
| handsomestWei/patent-disclosure-skill | root SKILL.md v5.2.1, patent-disclosure/SKILL.md, prior_art_search.md, patent-application/SKILL.md | Chinese disclosure/application drafting core. Lightweight CNIPA search: first results page (~10), selected 3–4 terms, abstract re-ranking. Search skill and disclosure prior-art search are explicitly separate. Overseas search requires opt-in. Application generation requires a disclosure and separate routing. Preserve its skill prompts, add orchestrator and source evidence gates in THIS repository. MIT, verify at pinned commit. |
| wangziying1004/AutoPatent | run_patent_agent.py: stages 1/2/3; patent retrieval, idea generation, novelty checker, drafting/review | Useful stage checkpoints and challenge loop. No LICENSE in root during inspection; ideas only, no copied code until owner confirms distribution permissions. One test file found in tests; do not equate risk scores with legal FTO. |
| joyboseroy/ideaforge | README, agents, FalkorDB knowledge graph schema | Borrow TRIZ/Design Thinking/SCAMPER independent ideation and lineage. arXiv-based prior art alone is insufficient; weighting and convergence scores are prioritization heuristics, NOT patentability scores. Apache-2.0 upstream, preserve notices if importing code. |
| open1s/trinno | README, package layout, LICENSE | Hypothesis/experiment log, stage gate and reproducibility; VS Code TypeScript frontend not a necessary production backend dependency. MIT. |
| PisenAILab/china-patent-figure-skill | README, SKILL, tests directory (>20 modules), acceptance tools | Separate service/CLI for STEP projection, labels, vector PDF/DXF and QA. Promising test surface; real performance and Windows deployment must be independently validated. MIT. Avoid direct CAD modifications without review. |
| lianghugjil/patent-template | SKILL and scripts | Good document/figure QA inspiration. Author-specific limits (e.g. number of embodiments) must be configurable as preferences, not CNIPA statutory requirements. MIT. |
| Patsnap patent-literature-search-mcp | public MCP metadata / earlier assessment | Data-backed commercial service; open MCP does not grant rights to the corpus or API calls. Treat as optional licensed provider. |
| EPO OPS | published API protocol | Implemented client in providers.py, requires authorized credentials. Integration tests with live EPO not performed; biblio coverage and claims availability vary. |
| PQAI | public repository | Optional semantic retrieval/reranking component; its hosted US-focused index cannot be described as globally complete. |

## Critical finding

The upstream Chinese patent skill is optimized for human-initiated disclosure and filing tasks, not for one-command autonomous world-scale research. Its own route table says the disclosure's prior-art search DOES NOT use the patent-search skill; overseas retrieval, docket and patent application require explicit routing. Therefore a parent orchestrator is warranted, while retaining the original specialist skills for writing and document formatting.

## Due diligence gates before importing source

1. Check LICENSE and dependencies at an exact commit SHA and keep third-party notices.
2. Check external API terms, data retention, scraping restrictions, rate limits and personal-data handling.
3. Threat-model prompt injection and confidential invention disclosure.
4. Implement adapter contracts; keep vendor-specific code outside patent-domain logic.
5. Run unit, contract, integration, red-team and expert-reviewed claim chart tests.
6. Version CNIPA rules; classify legal hard constraints versus office practice versus template preference.

No claim of production readiness or comprehensive patent search follows from a GitHub star count or a README demonstration.
