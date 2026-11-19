---
name: patent-autonomous
description: "从自然语言技术问题出发完成全球检索、创意裂变、反证和机械可实施性论证；默认只交付供技术人员审查的白话 LaTeX 技术方案；明确申请并获企业授权后才进入申请文稿。"
user-invocable: true
---

# 自主专利研发总控：技术方案优先

## 默认交付
用户一句话提出机械/消防车辆/液压/控制技术难题时，当前 ChatGPT/Codex 负责创新推演，工具负责检索、证据、事实落盘和质量检查。**默认生成工程技术方案书（阶段 A）**；技术负责人确认创新点与工程实施路线后，即可归档本轮成果。技术评审通过 ≠ 法定新颖性或专利授权成立。

## 执行步骤
1. 读取 AGENTS.md、docs/ARCHITECTURE.md、docs/TECHNICAL_BRIEF_STANDARD.md，创建私有案卷，先完成保密分级。
2. 合规检索真实专利与论文；明确实际检索的国家、时间、权利要求全文覆盖和失效数据源。
3. 利用 TRIZ/SCAMPER/FMEA/跨领域机理形成多代备选，建立引用与因果谱系；不虚构专利号。
4. 对多候选进行专利+论文反证、技术矛盾与工程可行性审核。
5. 由人工/宿主 Agent 选定一个主要发明方案，保存原理、结构、连接关系、操作步骤、区别技术特征和待证伪试验。
6. 调用 skills/patent-technical-brief/SKILL.md 自适应选择 LaTeX 模板、CAD 线稿/draw.io/Mermaid 流程图/时序图和可用图表，MCP 用 patent_brief_save 输出 08a_technical_brief.json/.tex。
7. 对照证据库开展技术人员可读的风险与创新初筛，组织工程评审；通过后可直接完成本项目，未通过则迭代并保留旧版本。
8. **仅用户明确决定提出专利申请且可信外部审批系统验签通过**，再使用 patent-drafting-cn 和专利申请质量审核。专利局正式递交依旧需要真实授权人员。

## 企业级审查
区分技术事实、理论推断和真实台架证据；区分创造性初筛、工程可制造性、FTO、企业 IP 权属；由不同角色独立审核。保密未批准前不发送任何真实未公开技术到外部来源。模型服务不需要单独 API，外部检索供应商可能需要授权凭证。

## MCP 与异常处理
先调用 patent_capabilities；用户不提出申请决策时不要调用 patent_draft_save。研究错误、来源缺口、图纸缺失均如实保存在案卷，严禁静默降级后宣称通过。参考 docs/MCP_INTERFACE.md、docs/IDEA_FISSION.md 与 docs/WORKFLOW_OPERATIONS.md。

## 前沿专利与 LaTeX 主源（2026-11-18）
接到一条全新研发指令后，读取 patent-project-storage、patent-frontier-innovation、patent-latex-research 三项技能；锁定当前 project_id 的 SQLite；按实际供应商检索时间刷新专利索引及公开论文前沿。已有专利名称必须先核对真实公开号再裂变。研究论文独立保存分节 LaTeX 和 BibTeX；默认发明成果先生成白话工程技术方案；各个变种均按原权要逐技术特征反证，不能跳过工程实用性验证。

## 长周期研发与会话级记忆恢复

每个自动研发任务必须读取 patent-literature-memory/SKILL.md；按 case_id 将全文检索索引和文献 MD 存入该项目的知识目录。代理当前会话开始时读取 patent_literature_resume，并使用 patent_literature_search/read 查找已有研究结论与支持原文。对缺失资料开展经过保密审批的批量多源分页检索，先将每篇资料创建来源可追溯 MD，然后调用 patent_literature_pending 逐批研读；每篇写明白话作用、技术机理、构型、参数、局限、创新转移和反证检索线索，通过 patent_literature_note 落盘。阶段末用 resume_save 保存研究状态/下一次任务，使用 SHA256 防覆盖，遇版本变化重新合并。

长期研究既要提高跨文献检索广度，也要区分“被发现、已读摘要、已读权要、已读完整原文、已验证技术结论”多个等级。已入库数不可等同完成审查。用户批准专利申请后再将已选定的白话发明方案转换为代理形式的专利稿，完整资料和未申请发明始终受密级控制。

## 论文数据源选择与研究记忆（2026-11-18）

多轮研究时调用 `paper-sources` 或 MCP capabilities，按任务配置 OpenAlex/Crossref/Semantic Scholar/arXiv/Europe PMC/PubMed/CORE/Lens；通过 Unpaywall 补 DOI 合法 OA PDF。所有检索仍受审批、许可和预算约束；输出跨平台 DOI 归并记录和逐篇 `03_paper_memory/EV-*.md`。每一轮需要加载上轮 Markdown 与来源索引，防止上下文裁剪造成重复检索。存档本地并经哈希检查，全文核验与专利实质对照单独推进。详见 docs/PAPER_SOURCES.md。

## 合法开放全文的增量证据处理（2026-11-19）

在获得论文标题/摘要、候选 PDF 地址之后，按专用 `patent-fulltext-processing` Skill 审查许可/项目保密状态，调用受控 CLI 构建 PDF 任务、固定 IP/TLS 下载、离线 Docling 解析，再用 MCP `patent_literature_fulltext_search` 查询页码证据。机器解析输出只表明已取得文本，仍需工程师核对原始 PDF 后才可用于创造性反证及工程参数判断。维护知识库每篇 Markdown、来源 SHA256、下载恢复点。详见 docs/FULLTEXT_PIPELINE.md。


## 自动图源与隔离渲染（2026-11-19）
根据真实工程事实选择图表：diagram_relations 只表达 components[].number 已明确给出的机械/液压/信号连接；process_steps >= 2 生成顺序流程；sequence_messages 显式给出交互双方及消息时生成时序图。没有对应事实时省略图，不补造几何、尺寸、测量曲线、参与者。调用 patent_figure_prepare 生成以 SHA 命名的可编辑 .drawio/.mmd，MCP 可用 patent_figure_source 读取。渲染只能由运营方隔离 figure_worker 运行，输出正式 PDF 和 08e_figure_render.json，经 patent_figure_sync 验证哈希后更新 LaTeX。任何变更触发已签核方案版本失效；工程质量复核必须针对最新版本。详见 docs/TECHNICAL_BRIEF_STANDARD.md 第10节。

## 自动研究的可核查短引（2026-11-19）

先使用 patent_literature_fulltext_search 查询与机械问题对应的真实页码，再用 patent_literature_fulltext_quote 检查原文短引是否逐字匹配。仅当引用属于当前案卷、当前 PDF SHA256 且来源已解析，才通过 patent_literature_note(basis=full_text) 持久化工程事实。模型推断与专业复核分层保存，文本匹配不等同法律和工程结论已核验。未解析、缺页码及已变更 PDF 的证据要写入待补清单。

## 长期课题来源发现优先级（2026-11-19执行协议）

用户要求“自己找题目/研究方向”、跟踪最新行业问题或开始任何消防机械方向查新时，必须先执行：
1. 使用 MCP patent_source_catalog（approved）、patent_topic_catalog、patent_discovery_inbox 读取已有20个来源种子、20个机械课题和增量公告。CLI 可用 mechanical-patent source-catalog sources/topics/inbox。
2. 优先核实来源官网发布日期和更新频率；过期项目保留历史研究价值但不能视为开放申报。平台新增时通过 patent_source_propose 入 pending，AI 不具备 source approve 权限。
3. 对来源观察执行 patent_public_observe，再以专利/论文/跨行业机制、FMEA、TRIZ 导出具体零部件/可测技术效果。通过 patent_topic_derive 形成可回溯的研究假说，并关联可证伪实验。保密研发信息禁止写入公共目录。
4. 对候选先复用 project 文献记忆，然后调用 patent_topic_plan 与既有多源检索、想法裂变、独立反证、工程审查工具；研究笔记必须标明原始 URL、证据缺口、发生时间和可信度，保存为未独立核验状态。
5. 用户选择课题后使用 patent_topic_adopt 转为单项目 SQLite 案卷，保密审批通过后方可对外发送新检索词。未真实执行工程试验时禁止宣称工程已验证或具备专利授权条件。
6. 只批准和处理有明确版权/访问权的公共数据。独立管理员通过本地 CLI 审批新源；AI 可提议但不能自我认证。
详细工作流参见 docs/PROBLEM_DISCOVERY.md，源码 src/mechanical_patent/problem_sources.py，平台和课题种子存于 src/mechanical_patent/data/。

## 全机械行业通用范围（2026-11-19）

本技能适用于任何机械平台、结构、机构、机电液系统和制造工艺。消防装备仅是一种应用场景，新增来源应覆盖制造/机床、机器人、工程机械、航空航天、海工、轨道、能源、矿山、农机、医疗、精密仪器等。每轮最先调用 patent_mechanical_taxonomy、patent_source_catalog、patent_topic_catalog、patent_discovery_inbox，依据行业×失效物理机理进行检索。使用 patent_mechanical_analogies(target_industry,mechanism) 从其他行业提出真正有连接关系和可证伪指标的迁移构想。任何未列行业可标 unclassified，再登记扩充；不得以消防行业为默认检索范围。已有37个来源与40项假说是初始数据，全部支持持久化与后续扩展。结果需独立权利要求反证与工程验证，禁止 AI 自行标记专利新颖性或实验通过。详见 docs/PROBLEM_DISCOVERY.md。


## 跨课题科研循环编排（2026-11-19）

在用户需要长周期研究、并行 Agent、独立科学验证、专利和论文成果分流时，读取 patent-research-cycle/SKILL.md 及 docs/RESEARCH_CYCLE.md。先建立项目隔离案卷，再用 patent_cycle_create / patent_cycle_status / patent_cycle_claim / patent_cycle_finish 实施有依赖的任务分工；双源检索完成后才进入证据整合和构思，独立评委与构思/反证执行人须不同。若裁决为 iterate，调用 patent_cycle_iterate 开启下一轮，旧记录不可覆写；真实计算与仿真证据须使用项目内附件的 SHA256 校验。科研循环仅保留模型无关的调度记录，当前宿主 AI 执行专业工作；专利申请审批、科学发表和真人实验核验始终走原有独立授权。

## 知识星图闭环：单文献、单项目、跨项目
开展双源检索后，必须读取 skills/patent-knowledge-atlas/SKILL.md。每批真实专利/论文入库后执行 atlas-index 或 MCP patent_knowledge_index；根据 patent_knowledge_graph 的单文献/单项目关联，追查相似专利原始权利要求、跨领域原理与尚未验证的假设。单文献自动记忆在 document_memory/generated/，工程与权要复核写在 document_memory/manual/，任何自动重建不得覆盖人工记忆。对已存正文的 AI 技术三元组使用 patent_knowledge_record_fact 并附可复核原文引句，标记待人工核实；引用数和文本相似不代表法律新颖性或创造性。跨项目图只能调用 global_public 公开投影；保密项目不得写入全局公开索引。可视化采用本地打包 Cytoscape.js，导出 JSON 由浏览器本地加载，禁止外部 CDN 上传案卷数据。
