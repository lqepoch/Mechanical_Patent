# Mechanical_Patent：AI 客户端原生专利研发架构

2026-11-18。设计目标：用户发一句技术要求，当前 ChatGPT、Codex 或兼容 Agent 自动开展双源检索、跨学科创新、反证检索、工程论证和中国发明专利撰写。**仓库不维护语言模型推理服务，也不要求任何 LLM API Key。**

## 分层

用户会话（ChatGPT / Codex / 可授权的 Dot 或其他 Agent）
    ↓ 读取 AGENTS.md + skills/patent-autonomous/SKILL.md
当前 AI 的工具调用与多角色推理
    ├─ 全球专利检索（官方/授权数据源）
    ├─ 学术论文检索（OpenAlex、Crossref、未来 arXiv）
    ├─ Crawl4AI 公开网页/科研文章合规正文获取
    ├─ TRIZ / SCAMPER / FMEA / Design Thinking / 跨领域创新
    ├─ 专利 + 论文独立反证
    ├─ 工程理论计算、可行性与验证计划
    ├─ 默认白话工程方案（CTeX/按需 CAD、draw.io、Mermaid）
    ├─ 工程/IP 双人评审完成可归档
    ├─ 仅可信申请转换验签后进行中国发明申请文件审核
    └─ 必要人工门禁
    ↓
统一证据与案卷（JSON、Markdown、DOCX / CAD 输出待接入）

## 数据源职责

### 专利

- EPO OPS：已存在凭证可选的 REST 数据适配器；每条结果标记来源、公布号和可用权利要求。仅代表实际检索范围。
- CNIPA / USPTO / WIPO / Patsnap / Google Patents：作为官方/授权 API、数据服务或当前 Agent 可用工具接入；缺席必须在覆盖报告中显式列出，不得声称已覆盖全球。
- 同族归并、反向/前向引证、IPC/CPC 检索及权利要求完整对照将在 #3、#5 完善。

### 论文

- OpenAlex：官方 works API，DOI、标题、发表日期、abstract_inverted_index 还原；普通匿名用量支持，额外数据服务 Key 可选。
- Crossref：官方 DOI 元数据 API，JATS 摘要清洗、出版日期抽取；匿名或可选 polite-contact 模式。
- Crawl4AI：允许访问的 HTML 正文，独立来源记录与 SHA256；科研全文的版权许可需逐站审查。
- 同一 DOI 跨 OpenAlex/Crossref 去重；无 DOI 的 OpenAlex ID 保留。源元数据检索成功不代表全文已读或学术结论经独立复现。

## 案卷状态

CREATED → DUAL_SEARCH_PLAN → PATENT_RESULTS + PAPER_RESULTS → CROSS_SOURCE_LANDSCAPE
→ PARALLEL_INNOVATIONS → PATENT/PAPER_COUNTERSEARCH → PHYSICS_REVIEW
→ ENGINEERING_TECHNICAL_BRIEF → ENGINEERING_REVIEW → [ARCHIVE_COMPLETE 或 ITERATE]
→ [USER_FILING_DECISION + TRUSTED_SIGNED_CONVERSION_APPROVAL] → CN_DRAFT
→ PATENT_PROFESSIONAL_REVIEW → MANUAL_FILING_DECISION

每个步骤有文档和来源，失败需报告并保留部分结果。缺少真实数据库、正文或关键实验时，可继续创建理论构想与标记缺口的申请草稿，但不能把审核门禁设为通过。

## 当前真正可运行的范围

- CLI 可无任何模型凭证创建案卷，保留检索策略与任务交接文本。
- 正式授权的 EPO OPS 数据接口保持；OpenAlex/Crossref 可检索学术元数据，全部 Python 标准库实现（Crawl4AI 为可选依赖）。
- 已创建 00_intake、01_search_plan、02_patents、03_papers、04_evidence、05_inventions、06_countersearch、07_engineering、08_application、09_quality_gate 和 manifest。
- 05-08 的创意、评估和撰写由当前 ChatGPT/Codex 直接完成，Python 不调用 LLM。validate 会检查已有证据、权利要求支持与缺口。
- 初期静态 QA 不能替代法律审查、全文查新、真实 CAD/仿真测试、可专利性或 FTO 法律分析。

## 上游依赖和许可证

完整源码已作为固定 git submodule 暴露：handsomestWei/patent-disclosure-skill、PisenAILab/china-patent-figure-skill、lianghugjil/patent-template、joyboseroy/ideaforge、open1s/trinno。按许可证及源码级审查后可转入 vendor/ 直接二开。AutoPatent 目前仅借鉴设计，未获得明确复制许可。

## 企业级演进

- 多租户 PostgreSQL + pgvector/全文检索 + 行/项级权限与项目 ABAC；
- 分层缓存与对象存储、专利/论文一致索引、增量数据同步、审计来源；
- AWS Lambda / Alibaba FC 适配入口共享同一业务代码，环境差异由 IaC 映射管理，不强制 Docker；
- 防止未申请技术外发的独立授权网关、密钥托管、审签分离和数据保留策略；
- 真实技术评审 Benchmark、召回率、Claim Chart 精确度、来源完整度、费用、延迟和可靠性；
- SolidWorks Windows-local API、STEP 转附图、ANSYS 真实求解器执行与结果复核；
- GitHub CI、依赖 SBOM、许可证扫描、审计日志、恢复机制、质量门禁、回滚；
- 任何申请提交由真实发明人、企业 IP 管理与专利代理专业人员确认。

详细 backlog 在 Issues #2–#10；最新 Agent 原生适配在 PR #11。

## 消防车与机械结构：公开问题驱动的课题发现层（2026-11-18增补）

在既有专利/论文双源检索入口上游增加 **Problem Discovery（课题发现）** 概念层：

公开问题来源/授权工况及故障 → 来源校验与时效识别 → 失效物理与可量化指标 → 跨行业机理映射 → 专利/论文证据检索 → TRIZ/Quality-Diversity 多路线构思 → 权利要求反证 → 工程验证 → 人工课题立项。

**数据治理**：问题源、候选方案与原始证据均有不可变来源 ID、URL、公开日期、实际检索时间、许可状态、内容哈希与抓取范围；国外标准、政府征集任务、商业专利数据库分开记录授权。已过申报期限的数据可以保留技术情报价值，但不能标成可申请项目。公开问题与项目保密构想分别处理，项目各有独立 SQLite；企业化跨项目分析只能发布经授权脱敏的技术问题摘要。

**交付边界**：当前阶段利用已存在的 patent-landscape、patent-ideation、patent-idea-fission、patent-countersearch 和 patent-engineering-review Skills 执行人工发起的发现研究。后续若开发自动增量采集、事件调度、趋势检测、问题库服务和 MCP 工具，需单独创建业务 Issue，编写合法数据源适配器、分源断路器与限流、断点续采、时间版本、幂等去重、集成测试和监控。现有代码未声称已经实现全自动问题挖掘。

**评审边界**：无法证实“尚未发明”；必须保存检索覆盖、竞争权利要求与可能未公开申请的风险。发现候选只生成通俗技术说明和试验计划，申请专利由发明人选择，企业法务/代理人员评审。

## 2026-11-18 架构升级：白话技术方案优先

按 docs/TECHNICAL_BRIEF_STANDARD.md 构建两个独立审查关口：默认一项发明的一份可读技术方案；仅另行获得签名授权才可进入申报材料。模块化 CTeX 模板和安全图源引用见 src/mechanical_patent/technical_brief.py，转换审批门禁见 src/mechanical_patent/filing_gate.py。该改动不改变现有 EPO/论文来源审批方式；真实组织身份仍需与 #25 集成。

## 项目级长期文献记忆与官方分页（2026-11-18）

原有运行案卷 JSON 保留。新增每项目独立的知识文件：
    private_workspace/projects/{project_id}/cases/{case_id}/
      knowledge/literature.sqlite3            # 单项目独立 FTS5/游标/审计索引
      knowledge/RESEARCH_RESUME.md             # 跨会话研究状态
      knowledge/INDEX.md                       # 文献目录
      knowledge/resume_history/{sha256}.md     # 研究状态历史
      knowledge/documents/patents/EV-*.md      # 一件专利一篇
      knowledge/documents/papers/EV-*.md       # 一篇论文一篇
      runs/RUN-*/                               # 每轮真实检索及工程数据

数据流：保密审批→官方检索多源分页→逐页入库/去重/检查点→每篇生成 Markdown→FTS5 trigram 中英文检索（不支持时降级 LIKE）→当前客户端 AI 逐篇阅读并记录来源层级/技术机理/作用效果/创新线索→有版本保护的项目研究快照→下次会话按需恢复。

- ID 与 kind、DOI/公开号绑定；同文献的机器著录信息可刷新，批注部分持久保留；Markdown 用临时文件原子替换，避免部分写入。
- SQLite 的 documents、documents_fts、harvest_checkpoints、note_audit、resume_audit 承担索引和溯源；原文法律/工程核查仍通过原先的独立审核流程。
- 官方 OpenAlex/Crossref cursor 深分页与 EPO OPS X-OPS-Range 严格受预算、许可、频率和超时控制；出现中断保存游标、已发现文献及错误。
- 恢复文件以 SHA256 乐观锁更新并留存旧版本；pending_analysis 每批取10–30篇，防止千篇文档一次进入模型上下文。
- 来源元数据、摘要、权利要求与完整原文的核查程度严格分离；不能把供应商著录 verified 认定为真正读过全文。

生产演进：地域/语种/同族/IPC/CPC/论文引证与相似专利覆盖；Docling/TEI/GROBID 有许可全文解析与页码；向量 ANN + 词法融合重排；真正可量化的 Recall@k/MRR；重试限流、统一租户 RBAC/ABAC、备份/恢复、审计追踪、KMS 和数据保留。当前 MCP HTTP 服务仍要求安全网关，不能直接作为多租户公网服务。


## GHCR + Ubuntu 26.04 Docker 架构（2026-11-18）

GitHub CI 构建 amd64/arm64 镜像并发布 GHCR。Ubuntu 26.04 Docker Compose 使用 Linux host network 保留 127.0.0.1 回环限制，通过 bind mount 将指定数据磁盘映射到容器 /data。每个进程绑定 PATENT_MCP_PROJECT_ID，存储目录 /data/projects/<project-id>/ 包含独立 SQLite、案卷、科研资料、论文及事件链；容器更新不改变这些持久化内容。支持一致性备份、SHA256 和镜像 digest 回滚。详见 docs/DEPLOYMENT_UBUNTU26.md。

目前缺少公网身份鉴权 OIDC、真实用户/项目 ABAC；需要另行完成认证网关、限流、审计及异地恢复，才能开放远程项目访问。

## 论文检索多来源标准接口（2026-11-18）

统一论文记录扩展 `Evidence.pdf_url` 和 `Evidence.paper_metadata`（包含 `doi`、`authors`、`citation_count`、`is_open_access`、`oa_status`、`license`、`source_ids`、`sources`、`pdf_link_status`、`full_text_verified`）。统一 DOI 合并各渠道摘要及来源 ID，保留 URL 来源和真实性区分，原生无 DOI 编号保留，不猜测跨来源同一性。

平台：OpenAlex、Crossref、Semantic Scholar、arXiv、Europe PMC、PubMed 为默认可选来源；CORE、Lens 加显式凭证和付费/许可证门禁。Unpaywall 为 DOI→OA PDF 位置增补，不能关键词检索。入库文档仅表示来源元数据，`full_text_verified=false`，真实 PDF 解析和版权审核另由批准流程处理。每次研究运行会生成逐篇 `03_paper_memory/EV-*.md` 和 SHA256 清单，作为长上下文研究的持久记忆。

CLI `paper-sources` 列举来源能力；`research --paper-provider arxiv --paper-provider openalex --enrich-unpaywall` 可组合使用；MCP `patent_research(paper_sources=[...],enrich_unpaywall=true)` 保持同一行为。外发保密审批、按案例 SQLite 隔离、授权 API 配额和提供方错误报告保留。技术细节见 [docs/PAPER_SOURCES.md](PAPER_SOURCES.md)。


## 自我发现课题来源平台库（2026-11-19）

系统新增 **可增量复用的公开工程问题来源目录**。首批预置20个公开平台来源和20项消防车结构研究假说，包含科技指南/揭榜挂帅、标准、采购、NASA、FAA、EASA、NFPA、HeroX、MIT Solve及专利论文数据入口；所有课题种子均标记“待验证的创新构想”。

每次 AI 接到“挖掘机械专利课题”任务时先调用 MCP：patent_source_catalog → patent_topic_catalog → patent_discovery_inbox。发现未登记平台，调用 patent_source_propose 进入人工审核候选池；来源证据可通过 patent_public_observe 入库，再调用 patent_topic_derive / patent_topic_plan 产生可证伪课题，最后结合已有专利论文技能继续检索、论证。公开研究笔记始终为待独立核验状态，采用的课题经 patent_topic_adopt 进入当前项目独立 SQLite。

公共目录存于工作区 public_source_catalog/sources.sqlite3；20个数据种子随安装包分发，见 src/mechanical_patent/data。批次巡检通过 mechanical-patent source-catalog cycle --allow-public-network 执行，批准的 RSS 来源增量更新并保留旧版本，失败会退避重试。生产可通过 Docker 持久卷和受控 cron/作业调度启动单次巡检；当前无内建常驻 AI 调度、保密外发仍须审批。

完整文档：docs/PROBLEM_DISCOVERY.md。开源网页监测备选：changedetection.io、Huginn 和 RSSHub，尚未自动安装集成。

企业生产的公网访问需网络出口 allowlist、禁止 DNS rebinding 的代理层、身份/权限审批、外部不可变审计和站点版权授权；AI 不能以自身结论完成工程或法律认证。
