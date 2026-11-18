---
name: patent-global-search
description: "中外专利查新、权利要求逐项比较、IPC/CPC 检索、同族与引证、论文交叉检索，生成可追溯的专利证据与创造性反证矩阵。"
user-invocable: true
---

# Global patent prior-art search

Current AI performs planning and interpretation; this Skill controls the provider and evidence workflow.

1. Generate Chinese and English technical terms plus synonyms, IPC/CPC class candidates, alternative machine domains, component function and failure mode queries.
2. Query authorized sources where available: CNIPA, EPO OPS, USPTO open data, Google Patents/BigQuery, WIPO licensed products and legal paid provider APIs. The included EPO client requires EPO-issued data credentials. Record provider permissions, date, query, filters, result count, limits and errors. Never claim a full global search when only EPO or a handful of web results are available.
3. Open at least the relevant claims, description and figures for primary references; avoid novelty claims based solely on abstract similarity.
4. Normalize publication number, application/family and country, publication date, earliest priority when verified, type, exact source URL, retrieved time and quoted passage/page/claim anchor. Keep publication date distinct from grant status and current legal status.
5. Deduplicate families and rank closest patent references, then compare each proposed independent claim's features against D1/D2 evidence with explicit undisclosed elements.
6. Run a second, adversarial search after AI generates inventive proposals, including adjacent fields, synonymous mechanisms and scientific papers. Identify combinations that might render the idea obvious.
7. Separate global technical search, Chinese novelty and inventive step analyses, and legal FTO. FTO needs territory, effective claims, time and legal status information.
8. Return evidence-linked patent landscape and claim chart, source caveats, queries for additional recall and specific engineering design constraints.

Official or licensed patent APIs are separate from Crawl4AI, which only extracts permitted HTML web pages and nonpatent sources. WIPO public PATENTSCOPE crawling is excluded.

See ../patent-paper-search/SKILL.md for mandatory scholarly cross-search and ../patent-autonomous/SKILL.md for invention drafting and feasibility review.
