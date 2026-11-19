# Mechanical_Patent 企业级智能体总控规范

## 系统使命

当用户给出任何机械结构、机械装备、机电液控制、传动、流体、热管理、材料成型或机械制造领域的技术难题时，当前 ChatGPT、Codex 或兼容 AI 会话应在能力范围内完成以下完整闭环：

保密分级 → 全球专利检索与论文检索 → 技术路线/创意裂变/反证 → 工程理论验证 → **默认工程技术方案及双人评审** → 归档；仅明确申请且企业可信签名授权后转换中国专利申请文件。

**当前 AI 会话负责推理与撰写。** 工具代码负责检索数据、出处记录、案卷状态和确定性检查。用户无需配置 Ollama、Qwen 或模型 API。EPO OPS 等数据供应方可能需要自己的数据访问凭证，这与模型推理权限互相独立。

## 简体中文统一标准

1. 所有本项目自有的 AGENTS.md、agents/*.md、skills/*/SKILL.md 描述、执行步骤、异常处理和报告均采用简体中文。
2. 为兼容 Agent Skills 规范，技能的 name 与目录名、文件路径和代码符号使用英文小写和连字符；description、章节标题和自然语言指令保持简体中文。
3. 专利公开号、DOI、IPC/CPC、物理符号、标准原文、法律术语及 API 字段保留准确原始格式。
4. 原始第三方许可证和上游代码文档保留其语言；自有适配说明及业务操作指南使用简体中文。


## 全机械工程通用检索原则（2026-11-19）

任何机械行业和未来新型机械平台均可纳入课题发现。消防车只是 fire_rescue 专题示例，AI 无权把消防行业作为默认优先级或检索上限。每次研究应先通过 patent_mechanical_taxonomy 获取行业与物理机理双轴分类，再检索已有来源/课题/观察结果。按故障物理（振动、汽蚀、摩擦磨损、疲劳、热、密封等）调用 patent_mechanical_analogies，从其他行业寻找可迁移的机构和制造原理。行业清单可扩展，暂未分类的设备保存为 unclassified 并经审核补充；全局公共来源 all 始终参加具体行业检索。任何相似方案都需重新执行原始专利权利要求、可制造性与实验反证，AI 研究假说不得标记为已获专利或已通过工程认证。

## 所有机械行业研究任务先复用公开课题来源平台库（2026-11-19）

**每次 AI 用户要求提出机械研发课题、主动挖掘问题、检索技术突破口或扩大研究方向时，第一步必须检索本仓库已持久化的来源目录、已有课题和未处理的新观察；不得未经查询直接重新发散。** 依次调用 patent_source_catalog、patent_topic_catalog、patent_discovery_inbox（或 CLI source-catalog sources/topics/inbox），建立来源和历史研究记录的背景，再继续现有的专利/论文、TRIZ、想法裂变及独立反证。

来源目录按平台、权属/许可、地域、官方/挑战/标准/科研类型、巡检状态、更新周期分类；发现新的大型问题源只能通过 patent_source_propose 记录为 pending，由管理员核对真实性、版权及网页规则后 CLI 批准。AI 不得自行审批新数据源。公开资料观察记录用 patent_public_observe，机械问题和可证伪实验用 patent_topic_derive，后续通过 patent_topic_plan、patent_public_research_note 追溯；选择研究的课题用 patent_topic_adopt 在当前项目独立 SQLite 新建案卷，真实保密审核先于项目检索词外发。

**人类与真实实验审批不可省略**：标题、摘要、行业猜想、AI 自评分不能成为“原创/法律可申请/工程已认证”的证据。临时不可访问的数据源记录错误与覆盖缺口，不用虚构内容代替。来源库公共数据库不得含内部故障、未公开方案、CAD/BOM 等机密；具体见 docs/PROBLEM_DISCOVERY.md 与 skills/patent-autonomous/SKILL.md。

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

## 多代构思裂变补充协议（2026-11-19）

一条技术任务需经过全球专利与论文检索、至少三条独立物理机理路径、反证与工程边界验证，再进入工程技术方案。若存在不同技术轴的已评价候选，优先调用 `patent_idea_crossovers`，构建可实施的多亲本组合创新；必须描述构件接口、控制时序和协同效果假说。对无法自洽、被在先技术挑战或试验否定的方案调用 `patent_idea_reject`，保留失败条件给下一代使用。任何评分、文本近似、构思交叉均不代替来源逐项核验或法律创造性判断。工作流见 `docs/IDEA_FISSION.md` 和 `skills/patent-idea-fission/SKILL.md`。

## 学术 PDF 合法获取与可恢复证据（2026-11-19）

在已完成的论文元数据检索与长期记忆基础上，按 `skills/patent-pdf-evidence/SKILL.md`、`skills/patent-literature-memory/SKILL.md`、`docs/FULLTEXT_PIPELINE.md` 执行：每篇开放许可证核查、当前案卷外发审批、真实授权人及许可依据记录、正式远端 PDF URL 精确域名白名单与固定 IP/TLS 安全下载、内容哈希、离线 Docling、页码原文索引、机器未核验状态、人工技术事实复核。禁止推定 PDF 链接有效、忽略法律许可、把摘要或解析输出标记已校验全文。下载/解析只通过受控 CLI 执行；MCP 提供状态、队列和页码级只读检索。迁移不得删除原有文献与人工批注，失败后保存状态等待人工判断，正式生产执行前仍需要可信企业身份及签名审批。


## 按需可编辑图示流水线（2026-11-19）
工程阶段默认先保存明确的部件连接 diagram_relations、顺序工作步骤 process_steps 和主体交互 sequence_messages；根据实际内容挑选 draw.io 原理关系、Mermaid 流程或时序图。读取 skills/patent-figure-cad/SKILL.md 与 docs/TECHNICAL_BRIEF_STANDARD.md 第10节，调用 patent_figure_prepare 创建内容哈希图源，交给独立无网络、非特权的图示渲染 worker 生成 PDF，再调用 patent_figure_sync 校核产物并更新 LaTeX。MCP 不得直接执行浏览器/Electron/TeX；图源和 PDF 均须记录 SHA256。技术方案修改导致签核哈希失效；任何图不能冒充真实 CAD 尺寸/结构。

## 必须核对全文引用位置（2026-11-19）

对于已经合法归档并解析的论文/专利来源，使用 patent_literature_fulltext_search 定位当前案卷的页码/块，再由 patent_literature_fulltext_quote 检查原文短引真实出现在当前 PDF 解析版本内。只有具体的 p2:b1 等引用通过校验后，才提交 basis=full_text 的 patent_literature_note。批注永久记录源 PDF SHA256、解析版本 SHA256 和未独立核验等级；PDF 更版、未解析、错误文献、缺失页码须拒绝高可信全文分析。应用既有 FulltextPipeline，不创建重复的 PDF 索引表，继续遵守保密/版权/人工法律审查门禁。

## 论文分页与长期记忆工作流（2026-11-19）

按 skills/patent-paper-search 和 skills/patent-literature-memory，选择 OpenAlex、Crossref、Semantic Scholar、arXiv、Europe PMC、PubMed 等来源及官方分页；Semantic Scholar Bulk 要求每页1000条并保留 token。案卷审批、来源许可、费用预算和覆盖缺口逐项核查。跨来源 DOI 归并保留证据、用户批注和最新版权变化，失效优先。Unpaywall OA 发现必须使用经过外发审批的 oa-enrich；PDF 正式下载、Docling 解析与页码证据继续通过 canonical FulltextPipeline 和已有人工门禁。具体见 docs/PAPER_SOURCES.md、docs/FULLTEXT_PIPELINE.md。


## 新增研究编排协议：长周期科研循环（2026-11-19）

当用户需要完整多 Agent 课题/专利/论文研究时，读取 skills/patent-research-cycle/SKILL.md 和 docs/RESEARCH_CYCLE.md。新案卷应先创建保密审批，不允许通过科研循环假装获得外发权限。当前项目的专利与论文检索可以并行，但后续证据必须先在项目案卷里经真实来源核验。构思必须包含可证伪实验，反证须覆盖全部候选；独立裁决 Agent 必须与构思和反证执行者不同，且生产环境要靠真实身份认证约束其独立性。计算/仿真/实验级别的验证需实际项目附件和 SHA256；模型自报级别不能替代人工认证。研究循环产出可以转为技术交底、论文初稿、待审专利候选或新研究任务，不能直接视为已发表、已授权或已完成正式递交。每一轮独立数据保存在项目专属 SQLite；出错后保留审计链及历史记录。MCP 工具见 patent_cycle_*，CLI 见 mechanical-patent cycle。现阶段运行仍依赖宿主 AI，定时巡检及分布式队列是后续独立建设事项。
