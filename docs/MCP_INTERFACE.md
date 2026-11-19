# Mechanical_Patent 标准 MCP 接口（2026-11-18）

## 目标与适用边界

本项目对外提供标准 Model Context Protocol（MCP）工具，而非专有模型 API。当前 ChatGPT、Codex 或其他 MCP Host 负责创造性推理；Python 工具负责真实专利/论文数据访问、证据、机械构思谱系、结构化发明申请草稿和确定性审核。接口采用 MCP Python SDK **v2**：本地 **stdio**；外部系统通过受控网关使用 **Streamable HTTP**。历史 SSE 仅为旧客户端兼容，不作为新接口设计。

**落地状态**：MCP 业务层已与本项目 SQLite 案卷、EPO OPS、OpenAlex/Crossref、构思裂变、逐项权利要求反证、工程假设、申请文档校验连接。全球全覆盖、完整中文多法域数据、真实 STEP 自动绘图、生产 OAuth2 身份服务和后台长任务队列仍需要后续集成。工具不会自动向国家知识产权局递交申请。

## 安装

Python 3.11+：

    python -m pip install -e '.[mcp]'

启动本地 MCP：

    python -m mechanical_patent.mcp_server --transport stdio --workspace /安全的私有目录/Mechanical_Patent --project-id PM80

在可联网的受控主机部署 HTTP（仅回环）：

    python -m mechanical_patent.mcp_server --transport streamable-http --host 127.0.0.1 --port 8765 --workspace /安全的私有目录/Mechanical_Patent --project-id PM80

HTTP 端点为 http://127.0.0.1:8765/mcp。公网、组织网络访问必须经过 TLS + 身份认证（OAuth2/OIDC/Keycloak）、访问权限和网络隔离网关；本代码拒绝监听 0.0.0.0。严禁将无认证的回环服务公开到公网或以负载均衡方式直接暴露。若有反向代理，必须保证代理到回环服务的链路仅由可信网关连接。生产环境还需要每个组织/项目独立的授权存储租户和真实用户身份审计。

### MCP 客户端配置示例（本地 Codex / 其他 Host）

    {
      "mcpServers": {
        "mechanical-patent": {
          "command": "python",
          "args": [
            "-m", "mechanical_patent.mcp_server",
            "--transport", "stdio",
            "--project-id", "PM80",
            "--workspace", "/安全的私有目录/mechanical-patent"
          ]
        }
      }
    }

这是通用 MCP Host 示例；具体客户端（Codex、Claude Desktop、第三方业务系统）须按其配置文件格式设置。工作空间路径应放到私有目录且具有最小权限，绝对不能与公开 Git 仓库、CI 可访问目录共用。

## 能力契约

| MCP tool | 输入摘要 | 输出及安全边界 |
|---|---|---|
| patent_capabilities | 无 | 支持的方法、技术轴、评分尺度、协议 |
| patent_case_create | case_id, direction, confidentiality | 新建案卷；默认保密 |
| patent_case_status | case_id | 工作流状态及是否获外发批准 |
| patent_research | case_id, patent_queries, paper_queries, limit | 真实数据源检索；无当前轮保密批准即拒绝 |
| patent_run_create | case_id | 离线创建运行，供外部合规 MCP 数据导入 |
| patent_source_import | case_id, run_id, records, patent_queries, paper_queries | 导入外部专利/论文证据，真实性强制标记待核验 |
| patent_case_artifact | case_id, run_id, artifact | 只读取14种白名单案卷文件；限制读取大小 |
| patent_idea_plan | case_id, run_id, parent_id, limit | 多方向裂变任务及物理/验证要求 |
| patent_idea_register | case_id, run_id, candidate | 保存机理、实施路径、父子关系、证据 |
| patent_idea_evaluate | case_id, run_id, candidate_id, scores, review, countersearch_refs, physical_principle, engineering_risks | 七项内部评分与反证假设 |
| patent_idea_frontier | case_id, run_id, top_k | Quality-Diversity 分组优选 |
| patent_idea_promote | case_id, run_id, candidate_id | 移交至发明候选文件，继续审核 |
| patent_countersearch_record | case_id, run_id, candidate_id, feature, source_id, quote | 引用必须存在于已取得且标记核验的专利权利要求正文 |
| patent_engineering_record | case_id, run_id, candidate_id, physical_principle, equations_and_units, assumptions, failure_modes, falsification_tests | 保存理论与待验证计划；严禁伪造仿真/实测 |
| patent_draft_save | case_id, run_id, candidate_id, draft | 保存权利要求、说明书、摘要及支持矩阵；检查审核问题 |
| patent_quality_audit | case_id, run_id, persist | 只读质量检查或持久化审计；不等于法律意见 |

MCP 同时提供 prompt 模板 autonomous_mechanical_patent(direction)，供调用端按一条指令调度全部步骤。MCP 本身没有擅自启动 ChatGPT、Codex 或其他模型服务的能力；宿主必须按提示运行专业 Agent。

### 研发案卷映射

1. 使用 patent_case_create 新建组织内唯一案卷。
2. 经过真实保密审批，将审批结果写入原有 LocalPatentWorkspace 工作流。可用现有 workspace CLI 的任务 claim/finish；MCP 禁止靠调用者自报角色跳过审批。
3. 使用 patent_research 创建 RUN-编号研究运行。没有 EPO OPS 数据凭证则明示缺口。支持调用其他授权检索 MCP 工具后，经本项目 mcp-import 命令将第三方结果导入为待核验资料。
4. 读取 02_patents、03_papers、04_evidence，进行多源差异分析；查询少、跨语种覆盖不足时继续拓展检索。
5. 使用 patent_idea_plan/register/evaluate/frontier 多代裂变；满足入库和反证记录后 promote。
6. 逐特征保存 countersearch_record、engineering_record；进行独立专业反证、理论/计算审核。
7. 在宿主 AI 内调用中文专利撰写 Skill，提供 draft JSON 给 patent_draft_save；机械附图 Skill 使用真实 STEP 文件并通过其独立测试和权限流程。
8. patent_quality_audit 返回真实缺口和待专业审核问题。**filing_authorized 永远是 false**；最终申请提交由获授权人员完成。

现有 CLI 保留：research、workspace、mcp-import、parse-pdf、citations、benchmark、validate。本 MCP 不向用户提供原始文件任意路径访问，不执行任意 Shell，不公开密钥或绕过许可下载。

### 结构化发明字段

candidate 必填：title、technical_problem、mechanism、enabling_details、distinguishing_features、assumptions、falsification_tests、expected_effect、technical_axis、inventive_method。可选 parent_id、evidence_ids。每一个来源编号必须实际存在于案卷 04_evidence.json，不能使用虚构公开号。

draft 包含 title、abstract、claims、description（technical_field/background/technical_problem/technical_solution/beneficial_effects/embodiments/drawings）、claim_support，支持段落必须真实存在于 description 中。格式检测只是基础校验，依然需要官方申请书式和专业人员全面复核。

## 安全、运行和可演进性

- 敏感检索词传出本机属于数据外发。需单独的保密审批和数据供应商合规使用授权。
- root、case_id 和 run_id 严格限制；禁止任意路径读取；不提供修改已批准证据的工具。
- 单机使用 SQLite + 文件锁，生产迁移到 PostgreSQL（RLS）、多租户对象存储、队列租约、Outbox、OIDC/AUD、限速、审计存证与备份。
- HTTP 使用受控上游网关；服务本身没有部署生产 OAuth2。需要在网关确保鉴权、用户与 case_id 的项目授权，随后建立后端逐请求的 ABAC 校验，才能在多租户远程环境使用。
- 单个检索 tool 当前是有界同步调用；生产超时任务应改为创建研究任务、返回 task_id、后台 worker 处理并支持结果轮询。
- 用官方 MCP SDK 的内存客户端测试 tools/list 和真实工具调用；CI 中安装 mcp 可选依赖执行协议测试。客户端可以使用 MCP Inspector 联机检查契约。
- 需要签订 SLA、源数据许可、地区合规和生产性能验收后，才可标为企业生产部署。

## 官方依据

- https://github.com/modelcontextprotocol/python-sdk
- https://py.sdk.modelcontextprotocol.io/
- https://modelcontextprotocol.io/specification/2026-07-28/basic/transports

### 其他数据供应商接入

已有 Patsnap、Patent Client Agents 等授权检索能力的客户端，调用 patent_run_create 生成本地 RUN，再用 patent_source_import 导入结构化文献（publication/title/url/source/kind/abstract/claims 等）。所有输入一律标记为未核验，自动记入本地来源索引、检索词记录及技术证据图谱；随后须打开真实公开 PDF、核验权利要求与公开日期，再进入正式反证。此工具适用于 Factrix 的供应商无关集成，生产级高并发事务需转 PostgreSQL。


## 项目隔离与扩展工具（2026-11-18）

**新服务器必须传 --project-id**（或 PATENT_MCP_PROJECT_ID）。每个进程只持有 projects/<项目ID>/patents.sqlite3；项目内 case_id、run_id、文献、论文、状态与证据同库审计。不能通过另一个 case_id 访问相邻项目。

增加 11 个 MCP 工具：

- patent_project_info：查询当前服务器绑定项目与项目案卷数。
- patent_index_refresh：已获外发批准后实时访问 EPO OPS，写入索引、时间和变化历史。
- patent_index_search / patent_index_history：离线查看专利资料、时间、修改历史和缓存状态。
- patent_frontier_scan：合法访问 OpenAlex 当前公开论文、保存真实 DOI/日期及来源。
- patent_variant_plan：对已有真实公开专利的名称或公开号生成技术变种研究任务。
- patent_manuscript_create/read/edit/revisions/export：保留 LaTeX + BibTeX 的 AI 分章节初稿、历史及 Pandoc 导出。

LaTeX 文稿和实时前沿索引见 docs/LATEX_WORKFLOW.md、docs/FRONTIER_EVOLUTION.md；项目隔离见 docs/PROJECT_SQLITE.md。PDF TeX 编译仅可在隔离沙箱进行，MCP 本身无运行 TeX 的工具。

## 白话技术方案优先与申请转换许可（v1.2，2026-11-18）

- patent_brief_save(case_id, run_id, candidate_id, brief)：保存当前候选的结构化白话技术方案并输出 08a_technical_brief.json/.tex。必备字段、可选配图和版式见 docs/TECHNICAL_BRIEF_STANDARD.md。无图则省略或列待补清单；不会生成申请权利要求。
- patent_conversion_status(case_id, run_id, candidate_id)：只读查询可信企业审批系统对同一方案 SHA256 的 HMAC 签名是否有效，返回 conversion_authorized 与永远为 false 的 filing_authorized。
- patent_draft_save：新增强制可信审批验签门禁。必须由独立审批服务生成 08b_conversion_approval.json 并通过 PATENT_CONVERSION_APPROVAL_KEY 验签；AI/MCP 无签名端点。方案一旦修改，旧审批自然失效；正式向专利局提交仍需要独立的审批和授权人员。

旧版客户端直接调用 patent_draft_save 将收到明确拒绝；改走 patent_brief_save 并由企业审批系统完成转换决定。签名与真实人身绑定的生产化由 #25 完成，当前本地签名控制只适合受控私有工作空间。


### 阶段 A 独立质量接口

- `patent_brief_audit(case_id, run_id, candidate_id)`：独立审阅 `08a_technical_brief.json`，逐创新点核对真实已验证权利要求、D1/D2 对照、工程反证、可证伪试验和图纸完整性，结果为 `revision_required`、`awaiting_dual_human_review` 或 `technical_complete`。
- `technical_complete` 需要企业可信签名的工程人员和 IP 管理人员分别签署 `08c_technical_review.json`（`PATENT_TECHNICAL_REVIEW_KEY` 单独管理），绑定技术方案 SHA、案卷、候选、结论与时间。该状态可直接结案，与独立的申请转换授权无关。单纯结构化校验不等于司法/专利法律上的确定新颖性。

## 项目知识库扩展（契约版本 1.5）

新增 MCP tool 名称和职责：

| Tool | 作用 |
|---|---|
| patent_literature_search | 检索该项目的论文/专利及研究批注，返回稳定证据 ID 与 MD 路径 |
| patent_literature_read | 读取指定单篇 MD，返回截断提示避免上下文膨胀 |
| patent_literature_note | 标注可理解的作用效果、技术机理、工程特征、反例和新发明线索；记录研读层级和出处 |
| patent_literature_stats | 项目数量、实际已分析数、未完成分页检索数 |
| patent_literature_pending | 批次获取尚未详细解读的文献 |
| patent_literature_resume | 取项目研究快照和 SHA256 以恢复会话 |
| patent_literature_resume_save | 基于 SHA256 乐观锁保存新研究快照及旧历史 |
| patent_literature_harvest | 保密审批和显式外发授权后用官方源有界分页检索和增量记忆落盘 |

MCP Host 当前 AI 负责真实研究和白话解读，服务端本身无 LLM 调用。新研究会话应依次调用 resume→search/read→pending→note→resume_save；遇乐观锁冲突先重新读取合并。现有专利检索/导入流程也写入项目记忆。项目路径为 projects/{project_id}/cases/{case_id}/knowledge/；各项目独立 patents.sqlite3 案卷库，每案卷独立 literature.sqlite3 文献库，MCP 进程固定绑定唯一 project_id。

企业正式上线还须增加 MCP 请求身份级授权、项目级 ABAC、集中服务配额、后台 worker、合规原文下载和页码锚定、备份恢复与可观测性。MCP 同步检索有时间/请求预算，不能标记为无配额的全量检索。

## 论文平台动态选择与标准化（2026-11-18）

`patent_research` 新增可选 `paper_sources: list[str]`、`enrich_unpaywall: bool` 和 `allow_paid_paper_apis: bool`。未提供平台时默认 OpenAlex、Crossref、Semantic Scholar。已登记的保密外发批准对所有外部渠道生效；Lens、CORE 除此以外还需 Token 与商业许可明确批准。

`patent_capabilities` 返回 `paper_sources` 清单，包括平台能力、是否需机构许可和是否配置。统一结果位于 `03_papers.json`，单篇记忆落在 `03_paper_memory/EV-*.md`；原有 `patent_case_artifact` 仍按受控白名单读取标准 JSON，不提供任意 Markdown 路径遍历。每份记录保留 DOI、PDF 候选链接、来源、OA、引用与许可元数据，仅当逐篇完成合法全文下载、实际 PDF 解析与证据复核后才能标记为全文已核验。标准接口、故障降级和示例见 [PAPER_SOURCES.md](PAPER_SOURCES.md)。

## 1.7：创新裂变的跨技术轴交叉与否定记忆

| MCP 工具 | 输入 | 返回及边界 |
|---|---|---|
| `patent_idea_crossovers` | case_id、run_id、limit | 已评价且不同技术轴的双亲配对任务，必须由 AI 再提出可实施耦合方案 |
| `patent_idea_reject` | case_id、run_id、candidate_id、reason、learned_constraints、source_ids（可选） | 保留原构思，记录反证与工程失败约束；禁止被否定构思直接晋级申请 |

`patent_idea_register` 新增可选 `parent_ids`（2–3个），该字段存在时 `inventive_method` 必须为 `组合创新`，并提交 `synergy` 和 `interface_definition`。服务端核查父节点、技术轴差异、最大裂变代数、父子谱系和证据编号。历史 `parent_id` 单亲本请求继续兼容。生成结果还包括 `text_overlap_neighbors` 供人工识别重复方案；这只是文本相似预警。

反证记录如果仅有标题/摘要或未核验原始权利要求，不得写成排除授权风险、侵权风险或已实现效果。负面记忆会进入下一轮 `patent_idea_plan` 的 `avoid_failed_constraints`。

### 失败子案修复与可信检索门禁

已归档为 `rejected_research_route` 的候选可以作为单亲本“修复来源”，但新构思必须使用新的 ID，并显式提交 `parent_id`、`repair_of_failed_route=true` 和 `repair_rationale`，描述如何具体消除原来的失败约束。原失败假说持续留档，不允许直接重评或晋级；失败路线也不能参加多亲本交叉。

`patent_idea_promote` 现在额外要求案卷真实存在一份 `verified=true` 且带原文权利要求的专利来源，同时该来源必须出现在构思的 `evidence_ids` 与评审 `countersearch_refs` 中。导入的第三方检索结果默认 `verified=false`，无法通过这一安全门禁。此状态只证明来源被核验，并不代表权利要求反证已通过法律审查。

## 正文页码搜索的 MCP 接口（2026-11-19）

提供 `patent_literature_fulltext_status(case_id,doc_id)`、`patent_literature_fulltext_search(case_id,query,limit=20)`、`patent_literature_fulltext_pending(case_id,limit=30)`；直接使用项目级全文 SQLite，提供可追溯 PDF SHA256、页码及解析状态，不返回文件系统任意读取能力。原文获取、许可审批和本地离线 Docling 由受控 CLI 运行；当前缺少请求级真实企业身份和签名的 MCP 外部写入不提供此能力。见 [FULLTEXT_PIPELINE.md](FULLTEXT_PIPELINE.md)。


## 工程图示生产流水线 / v1.4 (2026-11-19)

- patent_figure_prepare(case_id,run_id,candidate_id,wanted?): 生成不超过三类内容证据驱动的可编辑 .drawio/.mmd 图源，记录源哈希、图类型和建议落点；不运行外部二进制。
- patent_figure_source(case_id,run_id,figure_id): 只读取该案卷白名单中图源内容与 SHA256，可交由人工编辑器接收。
- patent_figure_status(case_id,run_id): 读取已登记计划及隔离渲染结果的概要。
- patent_figure_sync(case_id,run_id,candidate_id): 校验外部工作器完整 PDF 及 SHA256，再把图加入工程技术方案 JSON/TEX，失效之前的签名审批。
- 独立工作器 `python -m mechanical_patent.figure_worker render-figures|compile-brief-pdf --case-dir <案例>`；MCP 不提供执行系统进程的接口。draw.io/Mermaid 的生成源是功能关系示意，真实 CAD 必须另经专用工具确认。

独立工作器必须运行在已配置的企业安全隔离容器中，真实渲染版本需验收；本仓库 CI 对生成、源数据约束、失败关闭、伪造输出和 MCP 合同做离线验证。具体合同见 docs/TECHNICAL_BRIEF_STANDARD.md 第10节。

## 文献短引核验增量 MCP（2026-11-19）

新增 patent_literature_fulltext_quote(case_id, doc_id, anchor, verbatim)：依托当前项目绑定的 FulltextPipeline，检查证据位置形如 p2:b1、文献当前已解析 PDF 的哈希和段落文本是否含指定原文短引。响应 exact_match 与 SHA256、来源 URL、verification_level=parsed_text_match_only 和 full_text_verified=false；错误页码、其他项目来源和旧版 PDF 返回确定性拒绝。此工具只读，依赖已有合法 OA 下载、离线 Docling 和单项目案卷授权机制；没有任意路径或远程文献读取权限。

patent_literature_note 的 full_text 分析层级现在必须通过当前 PDF 段落锚点真实性校验，记录分析使用的 PDF/解析版本 SHA256 以供历史审计。旧版 metadata/abstract 记忆可以保留，不自动升级证据可信等级。


## 公共课题来源和自循环发现 MCP（2026-11-19）

下列工具在每个 MCP 项目实例中复用同一个公共来源目录，保密案卷仍只限当前独立项目：

| 工具 | 用途 |
| --- | --- |
| patent_source_catalog(status,limit) | 先读取已批准/待审来源目录与更新状态 |
| patent_topic_catalog(limit) | 读取历次工程课题与技术假说 |
| patent_discovery_inbox(limit) | 读取公开来源新增观察与待审批的大平台 |
| patent_source_propose(name,url,reason,discovered_from) | AI 自动发现新大平台后进入 pending；绝不自动授权 |
| patent_public_observe(source_id,url,title,summary,published_at) | 保存公开问题来源及原始链接元数据，内容未自动核验 |
| patent_topic_derive(observation_id,problem,hypothesis,falsification,domain) | 提出与真实公开观察绑定的待验证机械研究课题 |
| patent_topic_plan(topic_id) | 获取阶段化研究、反证及可证伪实验计划 |
| patent_public_research_note(topic_id,agent,findings,evidence_urls,public_only) | 留下 AI 研究笔记，状态 unverified_ai_assessment |
| patent_source_cycle(allow_public_network,max_sources) | 显式授权时执行已批准公开 RSS 的一次有限巡检 |
| patent_topic_adopt(case_id,topic_id) | 在当前项目 SQLite 新建保密案卷，不能直接外发检索 |

**数据治理**：共享公开目录保存在 `/data/public_source_catalog/sources.sqlite3`；各项目 SQLite 仍在 `/data/projects/<project-id>/patents.sqlite3`。20个来源和20个假说种子随 Python wheel/GHCR 镜像打包。新来源需管理员在 CLI `source-catalog approve` 批准：MCP 不提供 approve，不允许 AI 自行提高来源信任等级。管理员字符串尚未绑定身份认证，正式企业部署需要可信 OIDC、权限、可回滚审批和独立审计。

**调度**：Docker Compose 可选 `COMPOSE_PROFILES=discovery` 启动 `source-radar`，只对批准公开 RSS 执行增量巡检，支持版本、去重、失败重试、持久化和停机恢复。尚不具备自动唤起 LLM 研究、第三方网站全文采集或实验认证，自动研究需要后续具备身份/预算与审签的独立 Agent 运行平台。详细边界见 `docs/PROBLEM_DISCOVERY.md` 与 Issues #58–#62。

## 论文批量接口（2026-11-19）

patent_literature_harvest 扩充了可选 provider 和 page_size。普通 Semantic Scholar 使用 offset，Bulk 使用 token 每页1000条，arXiv、Europe PMC 和 PubMed 按各自官方 API 分页；仍强制执行项目保密外发门禁。无网、来源限流或许可缺失应保留错误而不伪造全局查全。原有 patent_literature_fulltext_status/search/pending 保持只读，下载与解析继续由本地批准的 FulltextPipeline 执行。

## 全机械行业来源检索与技术机理类比（2026-11-19）

MCP 的 patent_source_catalog(status,limit) 和 patent_topic_catalog(limit) 现新增可选 industry 与 mechanism；patent_source_propose 与 patent_topic_derive 新增 industry_tags 与 mechanism_tags 可选参数。新增 patent_mechanical_taxonomy() 返回18个初始行业/19个初始物理机理；patent_mechanical_analogies(target_industry,mechanism,limit=20) 返回其他行业具有同一物理机理的待验证研究假说。标签可继续扩展，未分类机械研究标记 unclassified。匹配分数与物理相似仅用于检索创新方向，不构成专利新颖性、工程可行性或可实施许可证明；需要独立查新、实验、技术负责人和专利人员审核。旧项目 SQLite 增量迁移保留全部人工审批与历史记录。CLI 入口为 source-catalog taxonomy/sources/topics/analogies。


## 科研循环 MCP 工具（2026-11-19）

新增 patent_cycle_create / status / claim / finish / fail / iterate / audit，可在当前 project_id 的同一 SQLite 案卷上运行。工具只返回任务调度摘要；研究结果存储于当前项目的 research_tasks.result_json，并通过 SHA256 保存内容摘要。十个任务的输出字段、门禁、迭代和安全边界见 docs/RESEARCH_CYCLE.md。MCP 不运行外部 LLM；actor 是调用端登记字段，真实身份与审批来源必须由可信接入网关负责。

### 新增知识星图 MCP 工具

| MCP tool | 输入 | 效果 |
|---|---|---|
| patent_knowledge_index | case_id, run_id, top_k, threshold | 离线建立当前运行隔离的 knowledge.sqlite3 与文献 Markdown 记忆 |
| patent_knowledge_graph | case_id, run_id, scope, document_id, max_nodes, min_score | 输出单文献或单项目星图及 Cytoscape 元素；提供方法、分数、出处 |
| patent_knowledge_record_fact | case_id, run_id, document_id, subject, predicate, object, quote, location | 候选技术三元组逐字引文校验并保存“AI待人工复核”，不代表工程/法律审核通过 |
| patent_knowledge_global_public | max_nodes | 仅查询原工作流中已批准公开项目的最小著录关系，其他密级不可见 |

跨项目私有查询没有绕过权限的 MCP 参数。完整 CLI、图谱本体、构建前端、性能与安全边界见 docs/KNOWLEDGE_ATLAS.md。

## 合规 PDF 全文批次只读状态（2026-11-19）

`patent_literature_fulltext_batch_status(case_id,batch_id,limit=100)` 在当前 project_id/case_id 下读取 `FullTextBatchRunner` 的批次总量、已完成、待处理、失败重试和截断的单篇检查点。MCP 不启动网络请求、PDF 下载或用户授权流程；批次创建与执行仅允许完成真实版权许可及项目外发审批的本地 CLI `literature fulltext-batch`。已有 `FulltextPipeline` 是唯一原文下载/解析状态机，解释见 docs/FULLTEXT_PIPELINE.md。
