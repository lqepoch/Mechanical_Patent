# Mechanical_Patent 企业级智能体总控规范

## 系统使命

当用户给出机械、消防车辆、应急装备、液压或控制系统的技术难题时，当前 ChatGPT、Codex 或兼容 AI 会话应在能力范围内完成以下完整闭环：

保密分级 → 全球专利检索与论文检索 → 技术路线/创意裂变/反证 → 工程理论验证 → **默认工程技术方案及双人评审** → 归档；仅明确申请且企业可信签名授权后转换中国专利申请文件。

**当前 AI 会话负责推理与撰写。** 工具代码负责检索数据、出处记录、案卷状态和确定性检查。用户无需配置 Ollama、Qwen 或模型 API。EPO OPS 等数据供应方可能需要自己的数据访问凭证，这与模型推理权限互相独立。

## 简体中文统一标准

1. 所有本项目自有的 AGENTS.md、agents/*.md、skills/*/SKILL.md 描述、执行步骤、异常处理和报告均采用简体中文。
2. 为兼容 Agent Skills 规范，技能的 name 与目录名、文件路径和代码符号使用英文小写和连字符；description、章节标题和自然语言指令保持简体中文。
3. 专利公开号、DOI、IPC/CPC、物理符号、标准原文、法律术语及 API 字段保留准确原始格式。
4. 原始第三方许可证和上游代码文档保留其语言；自有适配说明及业务操作指南使用简体中文。

## 核心职责与任务分派

读取 agents/README.md 定位 13 个专业角色；优先按下面次序分派并保存独立结论：

1. 总控与保密：管理案卷、出站授权、费用上限、失败路径、审批依赖。
2. 全球专利检索 + 论文检索：平行检索并记录真实访问源、检索范围、日期、原文状态。
3. 技术路线：将论文科学原理与专利的受保护方案组合成可追踪的问题/机理/技术特征知识图谱。
4. 多创新路径：TRIZ、SCAMPER、设计思维、FMEA、跨领域物理迁移并行提出候选。
5. 独立反证：逐候选对比 D1/D2 与相关论文，搜寻显而易见性、已有公开和实施限制。
6. 工程论证：做量纲一致的理论推导，检查结构、材料、运动、流体/热、控制、强度和安全；列出可证伪试验。
7. 技术方案优先：使用 patent-technical-brief 生成 CTeX 技术说明书与按需结构图/时序/流程图；通过双人评审即可结案，只有独立批准后才调用 patent-drafting-cn。
8. 质量与发布：保存问题清单、证据锚点、权项支持、工程/专利专业人员双重审批待办。

单个 AI 客户端如果不具备并行智能体运行能力，按专业角色依次工作并将产物保存在独立阶段文件中，明确同一模型自审的独立性有限。每阶段使用完整案卷事实和来源编号。

## 标准案卷

案卷目录由 Python 模型无关工具创建，包含：

- 00_intake.json：问题与保密级别
- 01_search_plan.json：专利/论文检索式和语种
- 02_patents.json：专利证据及权利要求可用性
- 03_papers.json：论文 DOI/元数据/全文可用性
- 04_evidence.json：多源证据归一化
- 04b_technology_graph.json：问题、证据、创新和验证关系
- 05_inventions.json：候选发明和区别特征
- 06_countersearch.json：权利特征与原文反证
- 07_engineering.json：理论论证、量纲、失败模式及验证计划
- 08a_technical_brief.json/.tex：默认工程方案与图文排版
- 08c_technical_review.json：工程/IP 双人结案评审签名
- 08b_conversion_approval.json：另行批准专利文本转换
- 08_application.json：仅获转换授权后生成正式申请文件草稿
- 09_quality_gate.json：质量与审批阻断
- events/*.json：具备内容哈希的本地审计事件
- manifest.json：文件哈希清单与案卷头事件
- AGENT_NEXT_STEPS.md：当前 AI 后续工作指引

所有声称已查明的文献必须有来源；所有实验数据需要实际执行证据。AI 概念、理论估算、真实求解器结果、实测数据分别标注。

## 重要法律和安全门禁

- 《专利法》第22条：新颖性、创造性、实用性；第26条：说明书充分公开与权利要求支持。
- 发明人由真实作出创造性贡献的自然人确认；AI 不能虚构发明人。
- 未公开发明、图纸、BOM、实验信息按公司保密要求分级处理，查询词也可能泄露发明方向；外部模型、云服务及搜索接口需要数据外发权限。
- 专利新颖性和创造性、FTO/侵权风险、工程理论可行性、企业商业价值必须分别形成结论。
- 人类工程负责人与专利专业人员独立审核后才能由授权人员作人工递交决策；任何 AI 工具不得自行完成法律申请动作。
- EPO、CNIPA、WIPO、Patsnap、论文平台均须遵守官方/合同授权；网站 HTML 正文统一通过经许可的 Crawl4AI 采集；不得绕开登录、付费墙或禁止自动化的网页。

## 工具与失败处理

优先读取 skills/patent-autonomous/SKILL.md；需要细分技术任务时读取对应子 Skills。用户若没有命名某个 Skill，仍应按完整工作流自主调用相关职责。

命令行支持：

    python -m mechanical_patent research --direction "消防车吸水创新" --patent-query "pump priming system" --paper-query "cavitation NPSH" --allow-search-exposure --case-dir cases/example-001
    python -m mechanical_patent validate --case-dir cases/example-001

无 EPO 凭证、网络、论文全文、STEP 或 ANSYS 时，标记实际能力缺口，利用当前 AI 允许的原生工具继续完成研究并向用户披露未验证部分；不能用虚构结果填补缺口。

运行者应检查 docs/ENTERPRISE_BLUEPRINT.md、docs/DUAL_LITERATURE.md、docs/AI_CLIENTS.md、docs/SECURITY.md 和 docs/UPSTREAM_AUDIT.md。所有自动化提交前运行 CI，保留可回滚的 Git 分支并检查第三方许可证。

## 版本与企业交付

研发案卷的阶段门禁 G0–G4、跨云部署、可观测性、SLO、企业权限、法务审查、源代码复用策略详见 docs/ENTERPRISE_BLUEPRINT.md。当前仅有部分核心工具达到可运行状态，不能把存在文档或 Git 子模块等同于具备生产能力。


## 必须遵循的企业级工作流

接收到单条“寻找发明突破口并写专利”指令后，读取 docs/ENTERPRISE_BLUEPRINT.md 与 docs/WORKFLOW_OPERATIONS.md，使用统一的案卷编号及 SQLite 工作流（当宿主有终端执行能力时）。检索、文献核验、方向判定、创新和申请文件不能只是彼此独立的聊天回答。

工作流应当在保密审批后并行安排专利检索与论文检索。文献核验角色依据真实公开来源审核公开号、DOI、权利要求/论文原文与日期，保存 source_url、public_pdf_url 和理由。没有公开原文时必须标注未核验。方向评审需要明确继续、改换方向或终止，并将依据证据与原因存入数据库；改换方向将开启新 revision，不覆盖之前轮次。

对于一个已有案卷，research 命令必须指定 --workflow-case-id 及 --workspace-db；任何远程查询都需要保密审批 outbound_approved=true，同时通过 --allow-search-exposure 明示允许外发。绝不靠字符串角色名宣称真实企业身份认证，真实工程师和知识产权专业审核须留给获得授权的人员。

多 Agent 长任务通过 workspace claim、heartbeat、finish、fail 等命令处理任务租约与失败重试。每轮始终保存专利和论文索引、独立反证、工程方程和假设、权要支持矩阵、来源图谱和质量清单。

专利只需在本地索引元数据和原文 URL 即能快速定位；有许可时可以归档公开 PDF 并记录哈希，但所有重要技术事实的最终核查应以已打开的原始公开 PDF 为准。GitHub 禁止提交未公开 CAD/BOM、内部原始资料、用户数据库及大体积 PDF。


## 行业成熟能力与 Codex 自动发现（2026-11-18 增强）

Codex 自动扫描仓库级 .agents/skills；本项目 canonical skills/ 和 .agents/skills 同步。运行 CI 的 scripts/sync_skill_mirrors.py --check 以防两者不一致。任何用户克隆完整仓库后，Codex 应能自动识别 14 个简体中文技能，无须再配置一个语言模型服务。

在全球专利检索阶段优先检查 skills/patent-industry-sources/SKILL.md，用户主动连接了 Patent Client Agents 等行业 MCP 时可直接调用其授权的结构化专利数据工具；外部数据写入 src/mechanical_patent/mcp_bridge.py 的统一契约，再保存到本地案卷。导入的文献必须经过原始 PDF/权利要求独立核验。结构化官方数据接口可以使用授权 SDK，网页 HTML 仅能通过 Crawl4AI 合规抓取。

在论文/专利 PDF 核查阶段使用 skills/patent-pdf-evidence/SKILL.md：优先打开在线原始公开 PDF；许可允许本地归档时，可以选择本地 Docling 解析章节、页码、表格，但不能冒充人工核验和真实实验。此模块不得自动下载任何 AI 模型权重。

每一轮候选创新与反证需要可衡量质量：使用 skills/patent-evaluation/SKILL.md 的检索评测工具，对具有企业合法授权的专业机械专利黄金标注集运行 Hit/Recall/MRR，同族去重、缺失样本计零。禁止将 CC BY-NC、许可证不明的数据集放入企业商业评测。第三方评测工具的样本版权与代码许可必须分开审批。

新增上游源码位于 external/patent-client-agents、external/patentkit（均固定 Apache-2.0 源码）；Docling 与 PatentAgentBench 保持可选，分别核查模型权重与数据集许可。完整取舍记录见 docs/INDUSTRY_REUSE.md。
## 文献引证扩展：参考文献与后续科学进展

完成专利和论文双源首轮检索后，对最关键的真实公开 DOI 读取 skills/patent-citation-discovery/SKILL.md。若保密审批允许，从 OpenCitations v2 查询直接参考和被引论文，并保留来源、方向、检索时间、局限和失败情况。每个新增 DOI 先标记“仅引证元数据”，然后通过 OpenAlex/Crossref 和真实公开原文补齐题目、机理与验证条件。

结合 IdeaForge 的技术关联图谱，区分理论前驱、后续方法改进与引用关系；据此寻找跨行业发明方向。每项新构思随后仍须重新检索专利权利要求与论文，并由独立反证角色和工程角色复核。具体记录格式见 docs/CITATION_DISCOVERY.md。

源代码固定在 external/opencitations-api、external/paper-qa、external/google-patents-examples，使用许可和最新数据接口由企业发布审查单独核实。PaperQA2 上游的额外语言模型与 embedding 调用不能作为本项目默认依赖。


## 构思裂变与对外 MCP（2026-11-18）

用户提出技术问题并要求自主研发时，必须读取 skills/patent-idea-fission/SKILL.md；在真实专利/论文检索后创建多技术轴、多创新方法和父子代际构思。每项构思保存 mechanism、enabling_details、distinguishing_features、assumptions、falsification_tests 和 evidence_ids。使用 FissionBoard 或 patent_idea_* MCP 工具保存 05a_idea_fission.json，按质量—多样性保留独立技术方向。研究分数、创新收敛和专利保护价值必须明确分开；同一创新假设未经有效反证与工程复核不得直接认定为已具备创造性。

新增标准 MCP 服务端 src/mechanical_patent/mcp_server.py，采用官方 MCP Python SDK v2，支持 stdio / Streamable HTTP；服务端本身不绑定外部 LLM API。涉及第三方查询词外发时，执行当前轮企业案卷保密审批；无授权时工具直接拒绝。MCP 提供专利检索、发明树、反证、工程假设、中文申请文件、QA 的统一业务工具与中文总控 Prompt。接口见 docs/MCP_INTERFACE.md。

外部系统接入时，必须将 MCP 放在已实现 OAuth2/OIDC + TLS 的受控网关后，限制回环服务访问和真实组织/项目授权，避免未经授权读取未公开专利内容。当前服务未自带生产身份服务，不具备直接公网部署条件。任何真实试验、仿真、专业签核及正式递交都需要独立证据或真实人员操作。


## 新增默认工作流：每项目独立数据库、LaTeX 论文与前沿发明（2026-11-18）

收到任何新的机械发明专利研发任务时，优先确认 project_id；用 ProjectStorage 打开唯一 projects/<project_id>/patents.sqlite3，并让 MCP 进程强制绑定该项目。禁止不同项目共享 SQLite，禁止把旧库在无授权情况下静默合并。旧版 CLI 未声明 project_id 只能用于历史兼容，新任务采用项目模式。

专业检索角色必须使用 patent_index_refresh 执行获准的真实供应商查询，保留来源、最后检查时间、新发现、变更版本、失败原因及上游公开延迟。在线查询失败时保留历史并标记 stale。专利未检索到或数据过期，不能宣称全球不存在该技术。

前沿研究从 patent_frontier_scan 的近期论文 DOI/真实发表日期、patent_variant_plan 的已公开专利公开号及权利要求开始，按照 Co-Scientist 式生成—反思—竞争—进化—聚类—总评、TRIZ/SCAMPER/跨行业类比独立探索，逐个进行二次专利反证并写明确的物理/结构/控制实施方案。科研论文用 patent_manuscript_* 工具维护分章节 LaTeX/BibTeX 初稿与版本，生成 DOCX/HTML/Markdown；正式中国发明申请文件继续走中文专利专业规则包和真实机械附图。无真实实验、仿真或专业审查时明确标示。

关键技能：skills/patent-project-storage/SKILL.md、skills/patent-latex-research/SKILL.md、skills/patent-frontier-innovation/SKILL.md。对应企业安全与 OpenAlex/EPO/Pandoc/Tectonic 资料见 docs/PROJECT_SQLITE.md、docs/LATEX_WORKFLOW.md、docs/FRONTIER_EVOLUTION.md。


## 工程技术方案默认交付（2026-11-18）

任何未明确申请的任务，先执行 skills/patent-technical-brief/SKILL.md 和 docs/TECHNICAL_BRIEF_STANDARD.md；研发报告通过即可结束，正式权要需专门的签名转换许可。旧申请文稿阶段是可选路线，不再自动触发。签名密钥只能由企业审批系统保管，MCP 只读验签，不能伪造人员授权。

## 强制启用：项目级千篇文献长期记忆（2026-11-18）

凡涉及项目专利检索、论文、科学原理、想法裂变、反证或长周期研究，优先读取 skills/patent-literature-memory/SKILL.md。每次先用 patent_literature_resume 恢复研究快照和最新证据；从已入库文献搜索起步，外部检索必须通过保密审批；新检索的每篇专利/论文用稳定 evidence_id 生成独立 Markdown，项目内 knowledge/literature.sqlite3 保存索引/游标/审计；逐篇通过 pending/read/note 补真实技术机理、结构、作用效果、参数、实验边界、已知缺点和新创新线索。项目快照使用 SHA256 乐观锁保存，避免任何模型会话压缩、Agent 交接或并发写入造成研究记忆丢失。

论文元数据、专利权要摘录、完整原文阅读及专业技术核查分别登记；一千篇著录信息不等于一千篇经过细读。补搜必须遵守供应方官方速率与配额。EPO OPS/论文文献分页运行失败保留已存 MD 和检查点；重新运行需追加检索并保留批注。用户仍决定何时由白话发明交底转入正式代理申请格式，默认交付简洁可理解的机械结构、控制逻辑、创新差异和验证计划。


## 容器部署和发行规范（2026-11-18）

容器化、磁盘、GHCR 和灾备任务必须读取 skills/patent-deployment/SKILL.md 与 docs/DEPLOYMENT_UBUNTU26.md。Ubuntu 26.04 使用宿主机独立磁盘挂载 /data，并配置 PATENT_MCP_PROJECT_ID；每项目 SQLite 位于 projects/<project-id>/patents.sqlite3。服务仅允许本机 127.0.0.1:8765 访问；公开镜像不包含私有案卷和密钥。PR 完成测试后由 main / 版本标签发布，远程接入须先落实 OIDC 和项目 ABAC。

## 论文平台选择及长期文献记忆（2026-11-18）

论文检索读取 skills/patent-paper-search/SKILL.md 与 docs/PAPER_SOURCES.md，优先组合 OpenAlex、Crossref、Semantic Scholar；需要预印本、医学研究、开放存储库和论文-专利交叉引用时可分别启用 arXiv、Europe PMC、PubMed、CORE、Lens。每一来源必须按平台授权、费用及速率实际约束执行，不得将 HTTP 200 等同于全文核验。外发前取得本轮案卷审批；CORE/Lens 另经商业许可批准。每篇论文逐篇生成 03_paper_memory Markdown，并记录 DOI、作者、PDF 候选、许可、数据原始来源以及下一步技术分析任务；以本地 SHA256 与项目 SQLite 索引追溯。无完整全文或无法联网时保留能力缺口。代码统一入口为 paper_sources.py、CLI 和 MCP。

## 原始论文 PDF 合法获取及全文证据（2026-11-19）

自主论文研发阶段继续执行 `skills/patent-pdf-evidence/SKILL.md`、`skills/patent-literature-memory/SKILL.md` 和 `docs/FULLTEXT_PIPELINE.md`。论文 PDF 处理须先确认版权/出版许可、组织外发审批与来源白名单；保留 SHA256 版本、许可证记录、项目内原始 PDF、Docling 逐页块和未人工核验状态。通过 `literature fulltext-*` 命令更新原始文献索引，MCP 仅可在所属项目查询来源状态与解析段落。长任务在重新开始时读取项目 RESEARCH_RESUME 和单篇 Markdown；全文段落可用于证据定位但不得自动表示结论已经经人工审查。所有新增代码和 Canonical Skills 更新同步到 .agents/skills；禁止把受控 PDF 上传公开仓库。
