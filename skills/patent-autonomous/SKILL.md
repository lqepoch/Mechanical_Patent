---
name: patent-autonomous
description: "一条指令自动检索中国和全球专利、学术论文与跨领域技术文献，产生可解释机械发明方案，完成反证检索、工程可行性分析、中国发明专利交底与申请草稿。由当前 ChatGPT/Codex 模型直接执行，不要求配置外部模型 API。"
user-invocable: true
---

# Patent Autonomous — AI native

## Mandatory operating model

The CURRENT ChatGPT/Codex/compatible AI client is the inventor, reviewer and patent drafter. This Skill supplies instructions and tool contracts; it never asks to install Qwen/Ollama or configure an OpenAI-compatible LLM API.

Read repo AGENTS.md and docs/AI_CLIENTS.md first. When there is no local terminal (ChatGPT website), use the current conversation's authorized web, repository connector and document tools and write the reports in the chat or connected repo. Do not claim a downloaded local repository is automatically visible in ChatGPT web.

## Single instruction, full workflow

1. Identify real-world engineering problem, physical environment, constraints, confidentiality class and intended invention patent jurisdiction.
2. Run prior-art patent search AND scholarly paper search before any invention writing. Read sibling skills/patent-global-search/SKILL.md and skills/patent-paper-search/SKILL.md. Expand Mandarin/English synonyms, mechanical principles, IPC/CPC and cross-field analogs. Record both result sets with publication dates and exact identifiers.
3. Compare patents by claims/description/figures, and scholarly papers by principles, method, assumptions and experimental scope. Extract technical defects and residual contradictions. Record inadequate search coverage.
4. Generate multiple independent designs using TRIZ, SCAMPER, FMEA, Design Thinking, biomimicry/cross-domain physical principles and ambitious but physically coherent hypotheses. Each candidate needs components, assembly/control interactions, stepwise mechanisms, falsifiable equations, design constraints and alternatives.
5. For EACH candidate perform new patent and paper countersearch: feature-by-feature D1/D2 comparison, motivation-to-combine analysis and citation-backed objection table. Novelty/inventiveness, feasibility and FTO are distinct evaluations.
6. Verify theory via engineering checks: force, flow/NPSH, energy, heat, tolerance, materials, kinematics, boundaries, reliability and safety as applicable. Do not pretend to run SolidWorks/ANSYS or physical experiments unless actual tools and files are available. State equations, units, parameter assumptions, failure mechanisms and verification plan.
7. Use pinned Chinese subskills external/patent-disclosure-skill/skills/patent-disclosure/SKILL.md and .../patent-application/SKILL.md for thorough legal drafting and Chinese terminology. Include technical disclosure, abstract, independent and dependent claims, complete enabling specification, drawing legend and claim-support matrix. If STEP CAD is available, use isolated china-patent-figure-skill for line art and cross-check marks.
8. Independently audit: every citation real and dated, every distinction grounded, each claim supported, sufficient disclosure of reproducible mechanism and boundaries, numbering, official statutory formatting vs template preferences, confidentiality, actual human inventors. Mark a draft as pending engineering/patent-professional review. Never automatically submit the application.

## Tool contract (optional CLI)

The native AI produces the queries and authored material. Python tools only fetch and structure data, never request an LLM.

    python -m mechanical_patent research \
      --direction "消防泵高海拔吸水创新" \
      --patent-query "high altitude pump inlet air separation" \
      --paper-query "cavitation high altitude centrifugal pump" \
      --allow-search-exposure --case-dir cases/new-case-001

Academic APIs use OpenAlex + Crossref by default after search approval, with optional no-key public access. Patent APIs may require EPO/other authorized provider accounts. If data access is missing, report this and continue using permitted native web search. Read AGENT_NEXT_STEPS.md and fill 05_inventions.json, 06_countersearch.json, 07_engineering.json, 08_application.json with evidence IDs. Then run the static gate:

    python -m mechanical_patent validate --case-dir cases/new-case-001

## Output

Patent and paper search logs, source coverage, parallel invention matrix, patent/paper counterevidence, physics and implementation report, Chinese invention application draft, figure plan and uncertainty/approval checklist.

Missing literature or experiments must remain identified as missing. Any invented public patent number, fake paper, fabricated measurement or claim of authorization is a hard failure.
