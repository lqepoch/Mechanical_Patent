# Mechanical_Patent

基于可核验现有技术的机械发明专利研发系统：一句指令触发 **专利检索 → 创新方案生成 → 反证检索 → 工程可行性审查 → 中国发明专利申请底稿 → 人工核验**。

**Current status: foundation integrated, not a finished enterprise production platform.** The runnable Python workflow, EPO OPS adapter, privacy gates, evidence manifests and deterministic unit tests are included. CNIPA/Patsnap/academic data connectors, full-text coverage, production authorization and CAD drawing integrations are separate follow-up deliverables. No model output is an approval to file.

## Design principles

1. Search authentic prior art first. All results include source, document number, URL, retrieval time and source verification state.
2. Generate multiple independent mechanical ideas (TRIZ, SCAMPER, cross-industry transfer, FMEA, radical physical hypothesis).
3. Red-team each idea, search for counterexamples, analyze novelty and obviousness risks.
4. Analyze physics, stress, flow, heat, mechanisms, interfaces, test plans and unknown parameters; do not make up experimental evidence.
5. Draft independent and dependent claims, specification, embodiments, abstract and figure plan as an unapproved Chinese invention application draft.
6. Preserve JSON evidence, model decisions, complete dossier and SHA-256 file digests.
7. No automatic filing, no false freedom-to-operate clearance, no worldwide completeness assertion.

## Quick start

Requires Python 3.11+. For sensitive designs, keep your model on a trusted local network.

~~~bash
python -m pip install -e .
python -m unittest discover -s tests -v
~~~

Example with a locally hosted OpenAI-compatible API and the authorized EPO OPS service:

~~~bash
export PATENT_LLM_BASE_URL=http://127.0.0.1:11434/v1
export PATENT_LLM_MODEL=qwen3
export EPO_OPS_CLIENT_ID=YOUR_EPO_ID
export EPO_OPS_CLIENT_SECRET=YOUR_EPO_SECRET
python -m mechanical_patent run \
  --direction "提出一种在高海拔低温环境下抑制消防泵吸水汽蚀的机械结构和控制方法" \
  --provider epo-ops --allow-search-exposure \
  --case-dir cases/altitude-pump
~~~

If a confidential invention is transmitted to a remote LLM, the system requires the explicit --allow-external-llm flag; remote endpoints must use HTTPS. An external patent search may also disclose search keywords and requires --allow-search-exposure. Review company secrecy restrictions before enabling either.

Offline imported corpus for testing:

~~~bash
python -m mechanical_patent run --direction "消防泵控制方案" \
  --provider import --import-json examples/imported_patents.json \
  --case-dir cases/offline-example
~~~

Imported documents are always labeled UNVERIFIED; the filing-review gate remains blocked until real authenticated sources and claim text have been independently confirmed. Running the command still requires a configured LLM.

## Outputs

Every case receives its own private directory. Case folders are excluded from Git by default.

- 00_intake.json: intake / model / provider
- 01_search_plan.json: multilingual queries and IPC/CPC hints
- 02_prior_art.json: retrieved records and incompleteness statement
- 03_landscape.json: technology map and problem gaps
- 04_inventions.json: multi-method innovation candidates
- 05_adversarial_challenges.json: independent counterargument and follow-up searches
- 06_engineering_feasibility.json: equations, assumptions, validation plan
- 07_updated_prior_art.json: post-ideation countersearch corpus
- 08_application_draft.json: Chinese application draft and claim-support mapping
- 09_quality_gate.json: review issues, safety and authorization gates
- manifest.json: integrity hashes; DOSSIER.md: review-readable consolidated report

## Architecture

The current runtime uses a cloud-neutral Python workflow with OpenAI-compatible model and injectable patent providers. It deliberately does not require containers. The models/protocols can be called from AWS Lambda or Alibaba FC through thin HTTP entrypoints when execution budgets and long-running task orchestration have been addressed.

See docs/ARCHITECTURE.md, docs/UPSTREAM_AUDIT.md, docs/SECURITY.md, and CODEX_EXECUTION_PROMPT.md.

## Upstream integration policy

- handsomestWei/patent-disclosure-skill: **retain** as a separately version-pinned Chinese disclosure/application/office-action Skill. Its internal lightweight CNIPA search should be complemented by a broader evidence-first retrieval gateway.
- wangziying1004/AutoPatent: **adapt the multi-stage methodology**; code not copied because a clearly reusable license was not established during audit.
- joyboseroy/ideaforge: adapt multi-method ideation and explicit concept lineage; FalkorDB is optional, with no production dependency until assessed.
- open1s/trinno: adapt hypothesis, experiment, reproducibility and rollback records.
- PisenAILab/china-patent-figure-skill: external local STEP geometry/figure service with isolated runtime; DO NOT render confidential assemblies in third-party cloud services.
- lianghugjil/patent-template: selective QA checks; distinguish mandatory regulations from template preferences.
- Patsnap, CNIPA, EPO OPS, PQAI: source adapters; any upstream API access is subject to separate legal rights and provider quotas.

No third-party source code has been copied into this repository. External projects require license review, pinned commits, dependency scanning and interface tests before production import.

## Patent law and validation

For China, see CNIPA Patent Law Article 22 (novelty/inventiveness/industrial applicability), Article 26 (sufficient disclosure and claim support), and the revised Patent Examination Guidelines effective 2026-01-01.

A functional prototype is not intrinsically a legal prerequisite to filing. However, a purely speculative effect, a physically impossible mechanism or missing enabling steps cannot be treated as an implementation-ready invention. Simulated, measured, proposed and unknown evidence must be clearly labeled.

If the decision is to file overseas for inventions completed in China, run an additional confidentiality-examination review before filing.

## Scope and limitations

The initial integration searches EPO OPS (authorized credentials required) and optionally user-imported documents. EPO bibliographic XML may not contain claims or abstracts; the program fetches claims separately when available. OPS coverage cannot establish an exhaustive worldwide search. Professional searching for CNIPA, WIPO/PCT, US and non-patent literature remains an explicitly tracked rollout item.

Automatic legal filing, automatic inventor attribution and automatic patentability guarantees are intentionally excluded.


## Full upstream source and Crawl4AI

The project now pins five complete licensed upstream codebases through Git submodules. Use the recursive checkout to obtain their full original code and license files:

    git clone --recurse-submodules https://github.com/lqepoch/Mechanical_Patent.git
    git submodule update --init --recursive

To copy one pinned licensed source into this repository for direct modifications:

    python scripts/vendor_upstreams.py chinese-patent
    python scripts/vendor_upstreams.py figure
    python scripts/vendor_upstreams.py all

This populates vendor/<name> with an auditable Git commit snapshot, license and metadata. Source upgrades are deliberate PRs. AutoPatent code is excluded until a compatible license is confirmed.

For HTML pages and online technical documents, Mechanical_Patent uses **Crawl4AI**. Official patent database retrieval remains separate from web scraping. Crawl4AI is an opt-in dependency:

    python -m pip install -e ".[web]"
    crawl4ai-setup
    crawl4ai-doctor

To include an authorized public webpage as non-patent evidence, use the run command with --web-url, --web-allow-domain and --allow-web-exposure. Robots checking, explicit host permission and provenance records are built in. See docs/CRAWL4AI.md, docs/SECURITY.md and NOTICE. Substantive and legal review still applies.

**Important:** Current production completeness remains limited to the evidenced Python research slice, EPO OPS integration requiring credentials, and a Chinese drafting prompt adapter. The pinned source trees expose upstream scripts but do not automatically certify their operations or grant rights to patent databases.
