# Mechanical_Patent — 全球专利 × 科研论文 × AI 发明研发

输入一句技术要求，由当前 **ChatGPT / Codex / 兼容 Agent** 完成全球现有技术检索、论文技术视野拓展、TRIZ/跨学科构思、反证检索、机械理论可行性评估，以及中国发明专利交底和申请草稿。

**AI 就是当前会话本身。** 仓库提供 Agent Skills、执行规则、检索数据接口、文档与质量校验工具；不需要本地安装 Qwen/Ollama，也不需要配置 OpenAI 或第三方模型的 API Key。用户在 ChatGPT 网页、Codex 等客户端使用该工作流时，由当前客户端负责推理、写作与工具调用。

> 状态：已实现模型无关的双检索工具底座、案卷生成与静态门禁；完整中外专利数据覆盖、CAD 自动附图、实际仿真、企业权限/审签及生产级部署仍在开发。研究草稿不能自动提交专利申请。

## 你只需发出一个指令

例如：

    调研全球消防车在高海拔低温环境下的消防泵自吸/汽蚀解决方法。
    同时检索中外专利和学术论文，寻找跨领域物理原理。
    提出若干可以理论实现的结构/控制创新方案，逐案开展反证检索，
    推演可制造的实施方案，给出公式、工况、实验验证计划，
    最终撰写中文发明专利交底、独立和从属权利要求、说明书、摘要及附图计划。

AI 默认执行：

1. 专利检索：中外专利数据库、IPC/CPC、权利要求、说明书、同族、引证与公开日期。
2. 论文检索：OpenAlex / Crossref、可访问的 arXiv/科研机构论文、相关技术手册和标准。
3. 现有技术矩阵：比较论文物理理论、专利保护范围及实际技术缺陷。
4. 多路线发明：TRIZ、SCAMPER、Design Thinking、FMEA、跨领域迁移及大胆但符合物理规律的假设。
5. 二次反证：针对每个候选重新检索专利与论文，形成逐特征对照。
6. 机械理论验证：公式、变量单位、力/流体/热/材料分析，限制条件、边界、失效模式与验证方案。
7. 专利撰写：中文技术交底、权利要求、说明书、摘要、附图及技术效果。
8. 独立复审：事实证据、充分公开、权利要求支持、保密/权属与人工审签。

## 运行方式：先区分 AI 客户端

- **Codex/编码 Agent**：克隆本仓库，读根目录 AGENTS.md 或安装 skills/ 下技能。Agent 调用本地数据工具并自行推理撰写。
- **ChatGPT 网页版**：需将 GitHub 仓库通过受支持的连接器或 Work 模式提供给会话。AI 可依托自身可用的检索和文件工具执行同样流程；本地下载的仓库不会被网页会话自动感知。
- **Dot**：可复用任务说明、连接器及持续研究方式，实际能否读取/运行此仓库取决于 Dot 和账号提供的连接能力；不会自动继承本机文件。
- **其他 Agent 客户端**：按其 Agent Skills 机制安装，遵循 SKILL.md，不强制任何特定模型服务。

详见 docs/AI_CLIENTS.md。

## Python 工具：仅负责数据，不承担 AI 推理

Python 3.11+，零 LLM 依赖：

    python -m pip install -e .
    python -m unittest discover -s tests -v

不联网、创建空案卷（让当前 AI 继续检索和补充）：

    python -m mechanical_patent research \
      --direction "消防泵高海拔汽蚀控制创新" \
      --patent-provider none --paper-provider none \
      --case-dir cases/altitude-pump-001

检索真实论文元数据，同时在具备授权 EPO OPS 凭证时检索专利：

    python -m mechanical_patent research \
      --direction "消防泵高海拔吸水方案" \
      --patent-query "pump priming air separation system" \
      --paper-query "centrifugal pump cavitation altitude" \
      --paper-query "air entrainment two phase pump flow" \
      --allow-search-exposure --case-dir cases/altitude-pump-002

默认论文数据源为 OpenAlex + Crossref，两者基础 API 可以无 Key 访问，但受使用额度和限流限制。EPO OPS 授权凭证缺失时，专利渠道标注未覆盖，AI 需要利用当前客户端可用的真实专利检索渠道继续推进。工具不会编造结果。

研究者可以单独指定数据库：

    python -m mechanical_patent research \
      --direction "消防泵低压环境" \
      --patent-provider import --import-json examples/imported_patents.json \
      --paper-provider crossref --paper-query "centrifugal pump cavitation" \
      --allow-search-exposure --case-dir cases/altitude-pump-003

导入的文献始终标记 UNVERIFIED。真正联网获得的论文元数据也不自动代表论文全文已验证。

AI 根据案卷生成 05_inventions.json、06_countersearch.json、07_engineering.json、08_application.json，然后执行：

    python -m mechanical_patent validate --case-dir cases/altitude-pump-002

静态检查只能发现证据和权利支持缺口；完整专利申请仍需真实工程师、发明人及专利专业人员审核。

## Optional：网页正文统一走 Crawl4AI

    python -m pip install -e ".[web]"
    crawl4ai-setup

Crawl4AI 负责合法允许的科研网页、技术文章、公开资料的 HTML 到 Markdown。官方专利数据库检索使用 API / 授权数据接口。需要指定域名白名单、访问授权、robots.txt 检查，遵守出版商条款。具体使用见 docs/CRAWL4AI.md。

## 数据服务配置（可选）

复制 .env.example 按需要配置：

    EPO_OPS_CLIENT_ID=
    EPO_OPS_CLIENT_SECRET=
    OPENALEX_API_KEY=
    PATENT_CONTACT_EMAIL=

这些是**数据供应方**的账号信息，不属于模型推理配置。Crossref 和 OpenAlex 的普通元数据检索无需模型 API。

## 上游完整开源代码

当前代码库以固定版本 Git submodule 保留这些项目及其许可证：

- handsomestWei/patent-disclosure-skill：中文交底、申请及专利法律工作流；
- PisenAILab/china-patent-figure-skill：机械 STEP 专利附图；
- lianghugjil/patent-template：可审计的文档/附图 QA；
- joyboseroy/ideaforge：TRIZ/SCAMPER/知识图谱；
- open1s/trinno：研究假设、实验设计和记录。

下载源码：

    git clone --recurse-submodules https://github.com/lqepoch/Mechanical_Patent.git

经许可核查后可以使用 scripts/vendor_upstreams.py 将固定版本复制至 vendor/ 中做二次开发。AutoPatent 的阶段性创新流程已被独立借鉴；直接复制其源码仍需明确许可证。

## 主要文档

- AGENTS.md：AI 的通用总控指令
- skills/patent-autonomous/SKILL.md：一键发明专利流程
- skills/patent-global-search/SKILL.md：全球专利检索
- skills/patent-paper-search/SKILL.md：科研论文检索
- docs/DUAL_LITERATURE.md：专利 + 论文双检索证据协议
- docs/AI_CLIENTS.md：ChatGPT / Codex / Dot 的使用边界
- CODEX_EXECUTION_PROMPT.md：企业级延伸开发提示词
- docs/ARCHITECTURE.md、docs/SECURITY.md、docs/UPSTREAM_AUDIT.md

研究中不虚构公开号、DOI、授权状态、实验结果或发明人；不承诺全球查全、授权成功或自由实施（FTO）。


## 企业级统一工作流与本地专利库

在双源检索和 AI 撰写之外，项目已加入本地可恢复的任务依赖图与证据索引，支持多 AI 角色领取任务、独立核验检索结果、选择继续/调整方向、记录反证和工程验证，以及申请草稿审核。

详细架构：docs/ENTERPRISE_BLUEPRINT.md。
简体中文操作手册：docs/WORKFLOW_OPERATIONS.md。
13 个 Agent 说明：agents/README.md。
11 个专用 Skills：skills/ 目录。

创建案卷并检查状态：

    python -m mechanical_patent workspace --db cases/index.sqlite3 create \
      --case-id PUMP-001 --direction "高海拔消防泵快速吸水结构研究"

    python -m mechanical_patent workspace --db cases/index.sqlite3 status \
      --case-id PUMP-001

保密审批完成后，当前 AI 可以在同一案卷 ID 下检索：

    python -m mechanical_patent research \
      --workflow-case-id PUMP-001 --workspace-db cases/index.sqlite3 \
      --direction "高海拔消防泵快速吸水结构研究" \
      --patent-query "fire pump vacuum priming" \
      --paper-query "cavitation low ambient pressure" \
      --allow-search-exposure --case-dir cases/PUMP-001-r01

绑定案卷时，即使指定 --allow-search-exposure，程序也会检查当前轮次保密审批，未获授权则拒绝外部检索。AI 客户端负责推演和起草，不需要模型 API 凭证。

本地文献资料保存公开号、DOI、标题、摘要、公开日期、数据源、核验结论和来源链接。原始公开 PDF 保存真实 public_pdf_url，可直接在线打开；经站点许可和明确授权后，可另外下载原始 PDF 到本地以 SHA-256 去重。原始 PDF 的在线核对始终是优先的真实性依据。

默认命令行只显示任务状态与公开文献定位信息，避免把未申请的技术方向、完整审查理由或内部路径写入终端日志。正式企业身份与审签需使用组织权限系统；本地 SQLite 和日志属于可验证基础能力，尚未达到多租户生产级安全标准。


## 新增行业级检索/解析/质量评测能力（2026-11-18）

**零 LLM API、当前 ChatGPT/Codex 自行推理**。本轮扩充：

- Patent Client Agents：经过许可的多国专利 MCP/Python 客户端，完整 Apache-2.0 源码固定在 external/patent-client-agents，需用户自己在 MCP 客户端确认安装/授权。结构化结果可经 mcp-import 导入，状态默认为待核验。
- patentkit：完整 Apache-2.0 源码固定在 external/patentkit，供专业权项拆解、标准数据模型与检索系统二次开发；其可选 AI API 不作为本系统的默认依赖。
- Docling：可选离线 PDF 解析，保留页码、正文、坐标、原始 PDF SHA-256。正式阅读先核对真实公开 PDF；模型资源须单独预置并审核许可。
- 企业专利检索评测：真实授权的黄金标注集，严格计算 Hit@K、Recall@K、MRR@K；缺失预测按零分处理，同族可以展开评测，非商业或未知授权的数据集默认拒绝。
- **Codex 原生 Skills 自动发现**：仓库增加 .agents/skills 下 14 个简体中文技能镜像，CI 严格对照 skills/ canonical 内容。更新技能后运行 python scripts/sync_skill_mirrors.py；检查运行 python scripts/sync_skill_mirrors.py --check。

安装基础组件不要求模型 API：

    python -m pip install -e .
    python -m unittest discover -s tests -v

用户自愿配置行业专利 MCP：

    python -m pip install -e '.[patent-mcp]'

若还未主动连接到 Codex/ChatGPT 的 MCP 工具，此命令只安装代码依赖，不能代替用户确认连接。实际 Codex 插件入口以 https://docs.patentclient.com/ 的当前安装指引为准。

行业 MCP 已获取结构化结果后：

    python -m mechanical_patent mcp-import --input 外部专利工具结果.json --output cases/待核验专利.json

只用于本地获准的原始 PDF：

    python -m pip install -e '.[pdf]'
    python -m mechanical_patent parse-pdf --input patent_library/原始公开专利.pdf --output cases/原文页码.json --source-url https://真实原始公开地址 --docling-artifacts 本地模型资源目录 --authorized

零外部数据的合成示例（仅检查计算程序，不能代表真实专利性能）：

    python -m mechanical_patent benchmark --gold examples/benchmark_demo/gold.jsonl --results examples/benchmark_demo/results.jsonl --rights examples/benchmark_demo/rights.json --output cases/synthetic-scores.json

具体使用边界、许可证和后续工程计划见 docs/INDUSTRY_REUSE.md。

## 文献引证图谱（第三轮行业开源融合）

新增 OpenCitations 官方 DOI 引证网络，能够以一篇已公开论文为起点，找到其参考文献和后来引用它的研究，帮助当前 ChatGPT/Codex 发现跨领域物理机理与反证线索。不会自动调用其他 AI 模型，也不会把 DOI 引用关系认作论文理论或专利创造性的证据。

前置条件：已有通过 research 建立的案卷，且项目保密审批允许对外查询公开 DOI。

    python -m mechanical_patent citations \
      --case-dir cases/已有研究案卷 \
      --doi 10.1162/qss_a_00023 \
      --direction both --max-links 25 --allow-search-exposure

示例 DOI 来自 OpenCitations 文档，仅用于演示命令格式，并未核实与消防泵技术相关。

结果保留 04c_paper_citations.json、每一批 citation_batches/<hash>.json、更新后的 04b_technology_graph.json 及事件哈希链。通过新的专利论文交叉验证 Skill 对新 DOI 进一步核实论文元数据、真实全文和技术可迁移性。

源码及许可证已固定为 git submodule：external/opencitations-api（ISC）、external/paper-qa（Apache-2.0）、external/google-patents-examples（Apache-2.0，原仓库已归档）。详细说明见 docs/CITATION_DISCOVERY.md；新增的 skills/patent-citation-discovery/SKILL.md 与 Codex 的 .agents/skills 镜像保持一致。


## 🧠 新增：全球专利研发 MCP + 多代发明想法裂变

- 统一专利 MCP 服务器：stdio（Codex、AI 桌面客户端）或回环地址上的 Streamable HTTP（由安全网关提供远程接入）。
- MCP 工具支持案卷管理、授权专利/论文检索、证据读取、AI 构思裂变、质量—多样性路线优选、逐权要反证、工程理论审核及中文专利申请底稿。
- 发明谱系独立文件 05a_idea_fission.json，保存父子节点、创新方法、理论假设、证据编号、反证与评分；默认至多四代、120个候选，可继续导入现有 05_inventions.json 工作流。
- 所有 AI 推理和文字撰写由当前 ChatGPT / Codex 等 MCP Host 进行；不需要另外安装 Ollama 或配置模型 API Key。EPO OPS 等专利数据接口有独立凭证和许可要求。

安装（Python 3.11+）：

    python -m pip install -e '.[mcp]'

启动本地 MCP：

    python -m mechanical_patent.mcp_server --transport stdio --workspace ./private_patent_workspace

启动由反向代理保护的 HTTP 后端：

    python -m mechanical_patent.mcp_server --transport streamable-http --host 127.0.0.1 --port 8765 --workspace ./private_patent_workspace

详细接口、示例配置、安全边界见 docs/MCP_INTERFACE.md，创新裂变方法见 docs/IDEA_FISSION.md，Codex 自发现入口为 .agents/skills/patent-idea-fission/SKILL.md。HTTP 默认只接受本机连接，正式远程使用仍必须配备 OAuth2/OIDC、项目访问控制和网络隔离，不可直接对公网暴露。

备注：GitHub 上包含服务端与离线测试，但并不意味着全球数据检索渠道已经全部开通、生产认证已经部署或机械仿真已经执行。专业专利申请前须复核权利要求、公开充分性、工程实现和权属。

跨供应商检索入口：patent_run_create（完全离线）+ patent_source_import（第三方专利/论文结构化证据强制待核验），可连接其他授权 MCP 工具，不依赖 EPO OPS 凭证才能建案。


## 2026-11-18：每项目独立 SQLite、最新索引、LaTeX 论文和前沿发明雷达

所有新 MCP 运行实例都必须显式绑定项目。每项目独立 projects/<project-id>/patents.sqlite3（WAL、来源历史和案卷审计）；项目间无共享业务 SQLite：

    python -m pip install -e ".[mcp]"
    python -m mechanical_patent.mcp_server --workspace ./private_patent_workspace --project-id PM80 --transport stdio

Codex MCP 客户端配置时应当为每个项目设置独立的 server 项与 --project-id；例如另一个项目使用 --project-id PM120。当前一个 MCP 实例管理一个项目内的多个案卷，底层 ProjectStorage 对项目 ID 与文件路径进行隔离验证。

新增 MCP 工具：
- patent_project_info：本项目数据库和案卷数量。
- patent_index_refresh / patent_index_search / patent_index_history：每次真实供应商请求、项目索引及文献历史版本。
- patent_frontier_scan：检索近期 OpenAlex 真实公开论文，保留 DOI、发表日期、时间和来源。
- patent_variant_plan：针对已有真实公开专利名称或公开号生成八种创新变体研究任务；AI 继续具体设计和反证。
- patent_manuscript_create/read/edit/revisions/export：按章节维护 LaTeX 主源稿、BibTeX 与修订历史，Pandoc 导出 DOCX/HTML/Markdown。
- 旧 patent_idea_*：负责多代裂变、父子谱系、工程反证和申请候选优选。

详细查看 docs/PROJECT_SQLITE.md、docs/LATEX_WORKFLOW.md、docs/FRONTIER_EVOLUTION.md；对应三个中文 Skills 已同步到 .agents/skills。单纯安装完成不代表已经获得 EPO 官方数据授权、企业身份认证、完整全球检索覆盖或真实机械仿真能力。


## ✅ 默认工程技术方案书（2026-11-18）

用户给出技术创新问题时，默认研发产物为自然语言工程技术方案，不强行撰写权利要求/说明书。结合结构、操作步骤和现有公开来源选择 CAD/STEP 结构线稿、draw.io 原理图、Mermaid 流程/时序图、技术比较表及验证计划；CTeX/XeLaTeX 排版，源文件可修改。

- 规范：docs/TECHNICAL_BRIEF_STANDARD.md
- 新 Skill：skills/patent-technical-brief/SKILL.md（Codex 自动发现镜像同步）
- 模板：src/mechanical_patent/templates/engineering_brief.tex
- 输入样例：examples/technical_brief_demo.json（示意输入，并非真实成果）
- MCP：patent_brief_save、patent_conversion_status（原 patent_draft_save 现在强制验证独立审批签名）

工程方案审核通过后可以归档结束。仅用户明确申请并通过企业可信签名审批，才允许使用申请转换工具。生产级身份与权限治理仍在 Issue #25 追踪。


工程阶段审阅接口：`patent_brief_audit`，通过双人独立签名返回 `technical_complete`，项目 SQLite 仍用 `--project-id` 单独绑定。

## 项目独立的千篇文献检索和永久 Markdown 记忆（2026-11-18）

已整合基于官方 OpenAlex/Crossref/EPO OPS 的分页检索，项目级 SQLite FTS5 trigram 检索，按 DOI/专利公开号去重，并为每篇文献生成一份 Markdown，保留跨会话白话解读/机理/结构/参数/局限/创新方向。研究恢复入口、待分析队列、文件索引、分页检查点与历史快照全部位于单项目知识目录中。

CLI 示例：

    python -m mechanical_patent literature --project-dir private_workspace/projects/PROJECT1/cases/X01 stats
    python -m mechanical_patent literature --project-dir private_workspace/projects/PROJECT1/cases/X01 search --query "泵入口空化"
    python -m mechanical_patent literature --project-dir private_workspace/projects/PROJECT1/cases/X01 pending --limit 20
    python -m mechanical_patent literature --project-dir private_workspace/projects/PROJECT1/cases/X01 resume-read
    python -m mechanical_patent literature --project-dir private_workspace/projects/PROJECT1/cases/X01 harvest --provider openalex --provider crossref --query "pump cavitation NPSH" --workflow-case-id X01 --workspace-db private_workspace/projects/PROJECT1/patents.sqlite3 --max-documents 1000 --allow-search-exposure

MCP 支持 patent_literature_search/read/note/stats/pending/resume/resume_save/harvest。必须先获工作流外发许可；OpenAlex 深分页超过第一页需要免费 API Key，Crossref/EPO OPS 均受官方配额限制。所有 MD 初次仅含真实源著录数据、摘要/权要摘录，技术深入理解由宿主 AI 按照 patent-literature-memory Skill 逐篇写入并明确原文依据。研究资料不能提交 GitHub。

详细实现、来源权限与企业升级路径参见 docs/ARCHITECTURE.md、docs/DUAL_LITERATURE.md 和 docs/MCP_INTERFACE.md。


## Ubuntu 26.04 Docker / GHCR 部署

提供 `ghcr.io/lqepoch/mechanical_patent:main` 多架构镜像与 Linux Docker Compose。`PATENT_DATA_DIR` 将宿主机独立磁盘挂载到容器 `/data`；`PATENT_MCP_PROJECT_ID` 绑定单独专利项目。独立 SQLite 位于 `/data/projects/<project-id>/patents.sqlite3`；服务只监听宿主机回环 `127.0.0.1:8765`。

~~~bash
cp .env.example .env
chmod 600 .env
# 配置 PATENT_MCP_PROJECT_ID、PATENT_DATA_DIR、PATENT_IMAGE
bash scripts/deploy_ubuntu26.sh init
bash scripts/deploy_ubuntu26.sh up
bash scripts/deploy_ubuntu26.sh status
~~~

完整安装、GHCR 包公开配置、备份/回滚与权限边界见 docs/DEPLOYMENT_UBUNTU26.md。

## 学术检索平台组合与统一元数据（2026-11-18）

先运行 `python -m mechanical_patent paper-sources` 查看可用渠道，再在已有工作流保密审批后使用：

```bash
python -m mechanical_patent research --direction "高海拔泵汽蚀" --paper-query "high altitude centrifugal pump cavitation" \
  --paper-provider openalex --paper-provider semantic-scholar --paper-provider arxiv \
  --enrich-unpaywall --allow-search-exposure --case-dir cases/example-paper-search
```

参数 `--paper-provider all` 会选择全部已授权来源；`--paper-provider core` 或 `lens` 需要对应凭证和 `--allow-paid-paper-apis`。无合法 PDF 时仍可保留 DOI、摘要和相关信息但标记全文未核验。每篇论文生成独立 Markdown 记忆，保存多渠道来源，并索引到案卷 SQLite。详细字段、密钥、配额与安全边界参见 [docs/PAPER_SOURCES.md](docs/PAPER_SOURCES.md)。

### 2026-11-19：跨技术轴的真实双亲构思与负面记忆

在已有四代构思裂变上增添 `patent_idea_crossovers` 与 `patent_idea_reject`。两位已评价的不同技术轴父构思可以组合生成新方案，必须提供可制造的接口定义和机理耦合说明；技术上被否定的方向仍保存在 JSON 谱系中，其失败条件成为下一轮明确的设计约束。近似文字重复只预警，来源、反证、工程和人工批准的独立门禁继续生效。详见 `docs/IDEA_FISSION.md`。

## 论文合法 PDF 全文流水线（2026-11-19）

针对每个项目独立的 `knowledge/literature.sqlite3`，新增逐篇开放许可确认、受控 HTTPS/TLS 固定公网 IP 下载、Docling 离线全文解析、页码证据 FTS5 索引、SHA256 哈希、任务租约与错误恢复。可通过 `mechanical-patent literature --project-dir ... fulltext-plan/fulltext-process/fulltext-status/fulltext-search/fulltext-pending` 操作。MCP 提供 `patent_literature_fulltext_status`、`patent_literature_fulltext_search`、`patent_literature_fulltext_pending` 三个只读工具。相关论文的机器解析产物始终标记待原文核验，开放许可与保密审批必须先行；受控 CLI 执行下载/解析。运行参数、安全要求、模型准备和容灾见 [docs/FULLTEXT_PIPELINE.md](docs/FULLTEXT_PIPELINE.md)。


## 工程方案自动配图流水线（2026-11-19）

研发案卷已保存 `08a_technical_brief.json` 后，调用 MCP `patent_figure_prepare` 生成可编辑 draw.io/Mermaid 原理图、流程图和时序图源；结构关系需明确的部件连线，避免用 AI 猜测机械几何。隔离工作器把图源转换为 PDF，`patent_figure_sync` 核对完整输出哈希并更新 LaTeX；可再用同一隔离工作器编译 PDF 方案书。真实 CAD 仍须通过 STEP/SolidWorks 专用模块取得。参见 docs/TECHNICAL_BRIEF_STANDARD.md 第10节及 skills/patent-figure-cad/SKILL.md。

## 全文证据逐字核验与长期记忆（2026-11-19）

在原有合法论文 PDF 下载、Docling 解析、项目 SQLite/Markdown 文献库基础上，增加 CLI fulltext-quote 和 MCP patent_literature_fulltext_quote，可按 p2:b1 真实页码段落核对短引，返回 PDF/解析版本 SHA256。AI 以 full_text 依据保存技术机理时程序会拒绝错误页码或过期 PDF，单篇 Markdown 保存对应解析版本。引用检查仅验证机器提取文本，真实论文和专利中的公式/技术效果仍需独立人员核对原始 PDF。详见 docs/FULLTEXT_PIPELINE.md。

## 自我发现课题来源平台库（2026-11-19）

系统新增 **可增量复用的公开工程问题来源目录**。首批预置20个公开平台来源和20项消防车结构研究假说，包含科技指南/揭榜挂帅、标准、采购、NASA、FAA、EASA、NFPA、HeroX、MIT Solve及专利论文数据入口；所有课题种子均标记“待验证的创新构想”。

每次 AI 接到“挖掘机械专利课题”任务时先调用 MCP：patent_source_catalog → patent_topic_catalog → patent_discovery_inbox。发现未登记平台，调用 patent_source_propose 进入人工审核候选池；来源证据可通过 patent_public_observe 入库，再调用 patent_topic_derive / patent_topic_plan 产生可证伪课题，最后结合已有专利论文技能继续检索、论证。公开研究笔记始终为待独立核验状态，采用的课题经 patent_topic_adopt 进入当前项目独立 SQLite。

公共目录存于工作区 public_source_catalog/sources.sqlite3；20个数据种子随安装包分发，见 src/mechanical_patent/data。批次巡检通过 mechanical-patent source-catalog cycle --allow-public-network 执行，批准的 RSS 来源增量更新并保留旧版本，失败会退避重试。生产可通过 Docker 持久卷和受控 cron/作业调度启动单次巡检；也提供 Compose 的 discovery 可选后台服务自动轮询已审批公共 RSS。AI 深度研究仍需已授权的 Agent 运行器，保密外发须审批。

完整文档：docs/PROBLEM_DISCOVERY.md。开源网页监测备选：changedetection.io、Huginn 和 RSSHub，尚未自动安装集成。

## 论文深分页与 OA 合法地址补全（2026-11-19）

现有项目文献库可通过 literature harvest 从六个开放论文平台按原生分页机制积累元数据，也可使用 Semantic Scholar Bulk token 深分页。受审批的 literature oa-enrich 用于按 DOI 查询 Unpaywall 的 OA URL；PDF 下载与 Docling 解析继续交由 FulltextPipeline 全文权限工作流处理。详情见 docs/PAPER_SOURCES.md。
