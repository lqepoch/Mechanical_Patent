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


## 🔭 三级知识星图与文献记忆

新增可审计的文献知识星图，覆盖单份专利/论文、单个研发案卷、仅获批准公开的跨项目研究网络。单研究运行独立保存 knowledge.sqlite3，自动记录文献关键词、引用、TF-IDF 候选相似关系、已有技术谱系与逐字校验后仍待人工复核的技术三元组；每个文档创建 document_memory/generated/EV-*.md，人工维护的 manual/ 文件不被覆盖。

    python -m mechanical_patent atlas-index --case-dir cases/已有研究运行
    python -m mechanical_patent atlas-export --case-dir cases/已有研究运行 --scope project --output ./project-graph.json
    python -m mechanical_patent atlas-global --workspace ./private_patent_workspace --output ./global-public.json

本地打包的 atlas-web 使用 Cytoscape.js 浏览生成的 JSON：cd atlas-web && npm install && npm run dev。MCP 新增 patent_knowledge_index、patent_knowledge_graph、patent_knowledge_record_fact 与 patent_knowledge_global_public；内网/未申请项目绝不进入公开全局投影。相似度及待复核技术关系不能代替真实权要核查、人工审查和法律判断。详情：docs/KNOWLEDGE_ATLAS.md、skills/patent-knowledge-atlas/SKILL.md。
