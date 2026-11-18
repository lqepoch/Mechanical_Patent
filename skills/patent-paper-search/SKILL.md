---
name: patent-paper-search
description: "检索全球学术论文、预印本、工程文献，利用 OpenAlex、Crossref、arXiv 等合法来源发掘机械发明原理、方法、理论和跨领域技术；生成 DOI 溯源与反证论文清单。"
user-invocable: true
---

# Scholarly discovery for mechanical inventions

The invoking AI (ChatGPT/Codex) is the search analyst. No LLM API keys are used.

1. From user's mechanical problem, derive 4-8 distinct Chinese/English academic search themes: fundamental physics, system constraints, alternate mechanisms, analogies from adjacent fields and failure modes.
2. Use currently available native web/connector tools. Where a local shell is accessible use OpenAlex and Crossref through the model-free Python providers. Their public metadata APIs may work without keys; optional OpenAlex key raises provider budget.
3. Keep DOI/OpenAlex ID, exact title, date, journal/venue when present, abstract as provided, source URL, and actual retrieval time. Do not synthesize a DOI or quote missing abstracts. Record full-text missingness.
4. For open-access HTML permitted by site policies, delegate article extraction to Crawl4AI. For a PDF supplied by user or available through a proper document handler, inspect the actual file and figures. Obey author/publisher rights and reuse limits.
5. Classify scientific methods by physical assumptions, variables, constraints, validity range, experimental reproducibility and possible adaptation to the target machine.
6. Compare against patent prior art to isolate what the paper teaches, what the patent claims, and what remains unsolved. Papers can be legally relevant prior art even without a patent number.
7. Rerun academic searches for every candidate invention, specifically seeking counterexamples, previous interdisciplinary applications, obvious transfer explanations and inconsistent physical assumptions.
8. Output an evidence-linked technical matrix and DOIs, with hypotheses, falsification tests, uncertainties, exact coverage and source status. Include non-publication sources such as standards or technical handbooks only when legally accessible.

Example for an AI-capable shell, paired with patent queries:

    python -m mechanical_patent research --direction "消防泵低气压吸水" \
      --paper-query "centrifugal pump cavitation altitude" \
      --paper-query "air entrainment two-phase priming" \
      --patent-query "pump inlet gas separator control" \
      --allow-search-exposure --case-dir cases/low-pressure-001

No AI model installation, OpenAI inference API, Qwen runtime or paid research API is required for the default no-key scholarly metadata search. Patent coverage, paper coverage and full-text verification must be reported separately.
