# Codex 企业级执行提示词：Mechanical_Patent

仓库：https://github.com/lqepoch/Mechanical_Patent

你当前就是负责研究与编写发明专利的 AI。不得让用户配置 PATENT_LLM_BASE_URL、PATENT_LLM_MODEL、Ollama、Qwen 模型服务器或任何外部 LLM API。用户在 ChatGPT、Codex 或兼容 AI 客户端的当前会话中完成创新推理和写作。本仓库中的 Python 工具仅负责官方/授权数据检索、Crawl4AI 网页采集、案卷结构化、来源记录、几何/工程工具与 QA。

## 总目标

用户只发送一个技术指令，你自动:
A. 中国和全球专利（包括权利要求、同族、引证、日期和 IPC/CPC）检索；
B. 科研论文（OpenAlex、Crossref、arXiv、论文参考文献）与非专利文献检索；
C. 结合论文机理和专利现有方案挖掘技术缺陷/技术矛盾；
D. 通过独立 TRIZ、SCAMPER、Design Thinking、FMEA、跨行业迁移、激进但物理自洽的方法生成 5-10 条不同创新路线；
E. 每条路线开展二轮专利+论文反证检索；
F. 给出有真实理论依据、公式/变量/单位/工况、装配或控制步骤、失效模式、可制造性、验证实验计划的可实施方案；
G. 优选具备明确区别特征、可清楚充分公开的发明候选；
H. 使用 pinned handsomestWei 中文专利 Skill 写交底、权要、说明书、摘要和附图计划；
I. 利用允许的本地 SolidWorks/STEP/ANSYS 工具生成真实附图或仿真（需要实际执行，不得编造），开展独立技术/专利专业复审；
J. 出具全链证据/来源/时间/风险/人工审批报告，最终仅给出待复核申请底稿。

## 已有实际代码与复用范围

读取：
- AGENTS.md、README.md、docs/AI_CLIENTS.md、docs/DUAL_LITERATURE.md
- skills/patent-autonomous/SKILL.md
- skills/patent-global-search/SKILL.md
- skills/patent-paper-search/SKILL.md
- docs/UPSTREAM_AUDIT.md、docs/ARCHITECTURE.md、docs/SECURITY.md

已经存在：
- Python CLI：research、run（alias）、validate
- EPO OPS 专利适配器；OpenAlex/Crossref 学术元数据检索；
- Crawl4AI 可选网页采集；Evidence、DOI/专利号统一记录、来源哈希和私有案卷；
- 上游完整 git submodule（中文专利 Skill、机械专利图、文档 QA、IdeaForge、Trinno），带许可证；
- 原生 Agent Skills 和离线 mock/CI 测试。

上游源码二次开发遵循固定 commit、MIT/Apache 许可、NOTICE 和修改记录。AutoPatent 仓库未确认适用的再分发许可证，其思路可以独立实现，现阶段不复制代码。

## 必须新建或完善的子系统

1. 多源专利适配器：CNIPA 官方合法数据渠道、EPO OPS、USPTO ODP、PCT/WIPO 授权数据、Google Patents BigQuery、Patsnap 商业授权等。保留每一结果的公开时间、完整权利要求、同族、引证、法律状态真实性与版本。
2. 双源检索：中英同义词扩展、IPC/CPC/DOI 引用网络、OpenAlex/Crossref/arXiv 文献覆盖、相关性+语义+全文检索、专业 Gold benchmark；论文方法迁移证据不能等同于专利授权结论。
3. Crawl4AI：唯一 HTML 提取引擎，允许网站且通过规则检查才执行。使用域名白名单、robots/服务条款账本、网络出站策略、DNS/IP 重绑定/重定向阻断、队列、限速、重试、快照、来源哈希。结构化官方 API 直接通过自身 SDK 调用，无需网页采集。
4. 专利创新：IdeaForge / Trinno 方法论、TRIZ 技术矛盾、SCAMPER 结构变换、跨行业可行机理、FMEA、可证伪实验与迭代版本；创新评分仅作候选排序。
5. 工程验证：材料、力学、刚度、流体、热学、控制和安全约束；真 SolidWorks/ANSYS 运行才允许把状态记为仿真已完成或实测已完成。
6. 反证：创新前/创新后两轮专利和论文双检索；以证据逐特征比较权利要求、论文方法、技术效果、组合动机；创造性、充分公开和 FTO 单独审核。
7. 写作：直接复用 handsomestWei patent-disclosure / patent-application 子 Skills，保留全部功能，取消用户在每步重复触发的需要；统一 case JSON 和权利支持；专利附图接入 PisenAILab STEP 工具、DWG/DXF/Word 模板质量检查。
8. 数据与权限：企业/项目/个人隔离、SSO、RBAC+ABAC、机密材料出站授权、RLS、对象存储、版本审计、专业审签、保密和专利权属审查。
9. 工程部署：Python 业务逻辑跨 AWS Lambda/阿里云 FC；独立调度/任务队列；低耦合数据连接器；CI/CD、SBOM、SAST、限速、缓存、日志、指标、回滚和灾备。
10. 测试：假 DOI/假公开号、未验证文献、来源短缺、模型假实验、提示词注入、数据库429、外网超时、多人访问越权、权利要求缺支持和高风险技术方案；所有测试在 CI 可离线执行。

## 具体执行

- 读取仓库和所有相关文件，列出实际已实现与待实施能力；勿覆盖现有成功模块。
- 以 GitHub Epic #2 与 Issues #3-#10 为基础，继续补充父子关系、验收标准与里程碑；每项记录负责人（未知则空）和依赖。
- 优先修复实际双源检索及 Agent 原生调用体验；包括 CLI/README 中不得出现必备的 LLM 模型 API 配置。
- 正常任务先检索再创新，创新后针对每个方案再检索，论证可行性后写申请。
- 每个模块提交有界、可回滚 PR，编译/测试/CI 和许可安全检查通过再合并到 main。
- 若外部数据需要单独 EPO/Patsnap/OpenAlex 授权，只提示其是数据服务凭证；不强制提供。
- 在 ChatGPT 网页等不能直接访问本地的环境，通过现有连接器/web 工具完成当前能力范围内的全部步骤并如实记录实际执行情况。

## 交付与验收

- 完整双源检索计划和搜索记录：中英关键词、数据库、检索日期、DOI、公开号、分类、完整性、空白和来源；
- 论文与专利技术对比矩阵：问题/原理/手段/差异/可迁移性/显而易见性风险；
- 每项可实施创新：零件、接口、运动/控制顺序、计算、参数、约束、替代实施例、风险与证伪实验；
- 中国专利交底、权利要求书、说明书、摘要、附图及引用/支持矩阵；
- 静态 QA、真实仿真/实验（若执行）、人工审签、权属/保密/FTO 检查清单；
- 代码、测试、运行说明、架构更新、Issue/PR、失败记录与回滚计划。

系统不得自动提交专利，不得虚构正式检索覆盖、DOI、公开号、论文全文、物理计算结果或发明人。


## 新增的企业级案卷与原文 PDF 验收要求（2026-11-18）

在现有双源检索和专利写作之上，将所有科研工作纳入持久化 workflow：保密审批、双源检索并行、证据真实性核验、技术方向评审、创新、反证、工程论证、申请文件、独立质量、人工审核。

源码现有 local_workspace.py、workspace_cli.py、pdf_archive.py、audit.py、quality.py、lineage.py。将任务 DAG 与上游 Skills 的结果对接到同一案卷，保留唯一 evidence_id、revision、task_id 与执行日志。AI 角色说明和自有 Skills 全部为简体中文。查询和撰写不通过外部 LLM 服务，继续使用当前 ChatGPT/Codex 客户端。

数据库中专利资料需要可查询的标题、公开号、公开日期、来源、核验状态、原始公开 PDF 链接。正式阅读时优先通过真实公开 PDF 在线定位。许可允许时才下载原文保存本地并记录 SHA-256，防止重复和偷偷改写；不允许跨域重定向、SSRF 和泄露未公开技术。

企业生产剩余任务包括：PostgreSQL + RLS/ABAC、统一身份认证与双人审批、持久队列/Outbox 与分布式锁、API 数据来源合同与增量抓取、真实 CNIPA/EPO/USPTO/WIPO + 论文全文检索、专业检索召回评测、Windows SolidWorks/ANSYS 实测、不可篡改证据存证、成本/告警/SLA 和灾备。任何未实现能力应在父子 Issue 保持打开，不得用示例数据代替真实完成度。

每次提交前执行 CI 全部离线回归、安全扫描和开源许可证审查，确认通过后才允许合并 main。


## 行业项目深度复用与新能力执行任务（2026-11-18）

在 Mechanical_Patent 中继续吸收行业优秀开源项目，并始终保持当前 ChatGPT/Codex 是推理主体，不强制安装另一个 LLM。

已固定完整源码：
- external/patent-client-agents（Apache-2.0）：优先作为多国专利原始著录/权要/同族/MCP 数据客户端。
- external/patentkit（Apache-2.0）：统一专利模型、权利要求特征分析、证据对照和检索架构组件。

优先阅读 docs/INDUSTRY_REUSE.md，并检查两个上游库锁定 SHA、LICENSE、具体 Python API 和测试。复制/改造可授权源码时保留 NOTICE 和审查记录，不要以第三方 Git submodule 存在就宣称功能已经完整联通。

新增的标准使用流程：
1. 检索来源选择：Patent Client Agents MCP / 已授权官方 API / 当前 AI 的网页检索工具。
2. 保存结构化结果到统一来源契约，利用 mechanical-patent mcp-import 标记待独立核实，并与现有本地文献库和案卷 revision 关联。
3. 对真实公开 PDF 优先在线查看；许可允许时用 Docling 本地离线解析，保留页码和哈希以支持权项证据定位。
4. 结合论文和专利，提出多个物理合理创新方向并逐项反证。
5. 使用有明确商业许可的机械专利黄金样本运行 mechanical-patent benchmark，稳定计算同族级 Recall/Hit/MRR，保留测试集版本、样本缺失统计与原始来源。
6. 扩展 PatentAgentBench 式新颖性、FTO、权项对照、撰写与 OA 评测；每项使用真实专家评分与经过许可的资料，非商业限制样本不得挪入企业。
7. GROBID 和 BGE-M3 作为可选后续模块，待企业评测证明业务价值、成本/数据安全可接受后再生产部署。

重要发现：Codex 仓库技能需放在 .agents/skills/ 才能自动发现，现有 14 个简体中文技能已同步，运行 scripts/sync_skill_mirrors.py --check 并在 CI 检测。未经用户明确授权，不连接外部 MCP 账户、上传技术机密或下载论文全文。工程/法律审查和正式专利申请始终由真实人员批准。

## 第三轮开源融合——学术文献引证关联和跨领域发明发现

在全球专利和论文双检索后，优先实施 OpenCitations DOI 引证扩展：
- 源码 src/mechanical_patent/citations.py、case_citations.py；
- 任务 Skill：skills/patent-citation-discovery/SKILL.md；
- 输入真实 DOI，查询 references/citations，保存每批来源和新的潜在论文 DOI；
- 将引用关系写回 04b_technology_graph.json，将新 DOI 标记为待核验，交由论文 Agent 核查全文；
- 避免递归无限扩张：查询 DOI 数、单方向结果数、总节点/边、额度和成本均设置预算；
- 后续应用到专利创新时，必须逐项反证 D1/D2/论文内容，不能用引用数量预测授权概率。

可参考但不作为 AI 运行引擎：
- external/opencitations-api (ISC)：开放科研引证 API 的成熟实现；
- external/paper-qa (Apache-2.0)：论文元数据多源核验、科学证据问答和可信引用，但其原生上游默认要求 LLM/Embedding API；
- external/google-patents-examples (Apache-2.0，2026-04-18 归档)：专利地图、Claim Text Extraction 与 Claim Breadth SQL 方法。对过时的 BigQuery 表结构不得照搬部署。

实现与升级按实际授权、固定 SHA、NOTICE、真实检索来源和 CI 回归执行。增量补检索应记录到同一个案卷及 DOI 引证图谱，人工审批保持必须。


## 追加执行目标：想法裂变与标准 MCP 接口（2026-11-18）

新增加的实际代码包括：src/mechanical_patent/ideation_fission.py、src/mechanical_patent/mcp_server.py，技能 skills/patent-idea-fission 和 .agents 镜像、tests/test_fission_mcp.py。完整协议参阅 docs/MCP_INTERFACE.md，质量—多样性裂变规则参阅 docs/IDEA_FISSION.md。全部 Agent 自有提示词和 Skill 描述使用简体中文。

操作指令：

1. 检查现有源码及业务测试，先执行 python -m unittest discover -s tests -v，针对每个 MCP 工具验证输入 Schema、鉴权边界、操作幂等、跨案卷路径保护和异常处理。
2. 与上游 patent-disclosure-skill 的交底、申请文件、claim-chart 和 Word 工具建立数据适配，统一中文五册结构；避免删除原有能力。
3. 将 AutoPatent 阶段状态/断点恢复、IdeaForge TRIZ/SCAMPER 交叉协作、Trinno 可证伪实验和 Co-Scientist 竞争进化方式，依许可审查后吸收为 05a 构思谱系。IDEAgent/许可证不明项目只吸收公开思想，不复制源码。
4. 将 patent_idea_plan 从计划任务扩展为宿主 AI 侧的多角色并行工作流：每代查新、多个技术轴独立构思、反证、工程分析、质量—多样性保留，最多四代或到预设预算为止。
5. 实现可验证的候选融合：父方案与子方案有清晰区别技术特征和相互作用，简单拼接的方案必须有明确功能关系与技术效果论证。
6. 优先接入真实专利数据库，包括 EPO OPS、授权行业专利 MCP、USPTO 开放接口、CNIPA 合法渠道、Google Patents BigQuery 和商业 Patsnap 许可数据源；缺失供应商或支付授权时报告实际覆盖。
7. 对真实公开号、DOI、来源 PDF、权利要求、审查日期逐项标注；专利权利要求引用必须能匹配原文，论文摘要不可冒充专利权利要求。
8. 对接中国专利五册输出、STEP 附图、DXF/DWG、SolidWorks 与后续 CAE 验证接口；实际未运行的工程计算或实验不得标为已完成。
9. 服务采用官方 MCP SDK v2，stdio + Streamable HTTP；API Schema 能被外部 MCP Host 直接发现，至少覆盖案卷、检索、裂变、反证、工程和申请写作。自有知识图谱与证据库只管理真实已验证的来源状态。
10. 将纯本地例程与生产系统能力分开：生产需 PostgreSQL + RLS、Keycloak/OIDC、限速与授权、队列和 Outbox、原始证据不可改写存储、审计和跨云部署。
11. 每次提交先跑 Python 3.12 完整离线 CI + MCP v2 Client 协议握手与工具调用测试；任何红灯明确记录并修复。分组 Issue 对应后续未闭环项目。
12. 创建 PR 并与 main 比较，检查功能回归及许可证。全部必需检查通过后合并 main，并保留回滚 SHA。

输出应包含真实的用户使用示例：一句任务触发保密审批后的专利/论文检索→多代构思→逐特征反证→理论验证→权要/说明书撰写→审查待办。明确 AI 仅负责生成受验证的研究草稿，最终是否申请交由专利专业人员和企业授权人员决定。

追加数据接入验收：核验 patent_run_create、patent_source_import 可导入第三方授权 MCP 真实结果，同时输入 verified=true 也必须入库标记未核验，重复导入去重、记录检索式与原始来源；无法通过源文件核对时不得出具创造性审核通过结论。


## 追加 CODEX 执行任务（2026-11-18）：项目数据库隔离、论文 LaTeX、实时前沿专利

当前仓库 main 的核心目标已经扩展至：
1. 每个研发 project_id 独占 SQLite 与 evidence/manuscript 目录；同项目不同案卷可共用项目 DB，跨项目零共享。默认 MCP 启动需显式 --project-id。旧版单库仅为历史过渡。
2. 实时检索最新公开专利时，每次访问授权 EPO OPS 并保存检索式、来源、检查时间、结果、新增与变更历史，失败保留旧快照且明确 stale。不得推定全球完整覆盖；继续建设 CNIPA/USPTO/WIPO/商业数据库授权适配和合法全量增量索引。
3. 使用 LaTeX 作为研究论文及理论论证的唯一规范主源；分章节/版本/BibTeX，利用 Pandoc 导出 Word、HTML、Markdown。生成 PDF 必须在不挂载秘密文件的离线隔离容器内执行 Tectonic/TeX Live，禁止无沙箱运行任意 TeX。
4. 当前前沿主动发现通过 OpenAlex 查询近期真实元数据，明确发表日期与数据库更新时间的区别；补充 arXiv、当前合法专利出版公告、相关标准、工业公开技术。
5. 用户仅给最新专利名称或公开号时，先检索确认真实原件，再触发 patent_variant_plan，沿多种机械/控制/材料/工艺及跨学科技术路径独立构思。
6. 将 AutoPatent/IdeaForge/Trinno 和 Apache-2.0 的 Co-Scientist 公开方法吸收到 AI Host 的生成—反思—竞争排名—进化—去重—总评；要记录真实来源、父子关系、反证意见、失效验证和淘汰原因。
7. 每个分支技术候选都独立二轮反证检索，工程计算包含量纲、约束和制造可行性，才进入中文发明权利要求/说明书/摘要/附图生成。
8. 生产远程 MCP 继续建设 OIDC/Keycloak、逐项目权限、事务/队列/审计、备份及异常回滚；现有文件式项目隔离不能代替真实多用户认证。

代码入口：src/mechanical_patent/project_storage.py、patent_index.py、latex_manuscript.py、frontier_radar.py、mcp_extensions.py。MCP 工具协议由 tests/test_project_latex_frontier.py 及 tests/test_fission_mcp.py 验收。CI 必须同时跑离线模拟场景、真实 Pandoc 转换、MCP SDK v2 发现/调用；任何红灯先修复再合并。

未解决工作开 Issue，保留明确验收、数据许可、跨云部署、回滚与真实生产测试。任何新颖性、创造性、FTO 结论仍须独立人工专业审查。
