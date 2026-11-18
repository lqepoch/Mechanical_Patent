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
