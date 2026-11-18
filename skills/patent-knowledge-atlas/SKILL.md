---
name: patent-knowledge-atlas
description: "在机械专利研发时为每篇专利/论文建立可追溯技术知识星图，在同一案卷内寻找相似文献，并从已获授权公开的项目构造全局知识星图。"
user-invocable: true
---

# 专利研发三级知识星图

## 适用场景
用户希望寻找相似专利、论文之间的共同机械机理、隐含关联、技术簇、研究空白或未来发明方向时触发；每次新检索导入后更新本案卷索引。

## 基础约束
- 当前 ChatGPT/Codex 执行推理；仓库 Python 仅做离线可审计的索引、相似候选和证据管理。无需配置单独的 LLM API Key。
- 单次研究运行拥有独立 knowledge.sqlite3 与 document_memory/；原始文献存于 04_evidence.json，已有 04b_technology_graph.json 和 04c_paper_citations.json 保持为证据源。
- 边的 method=tfidf_cosine 仅为算法推荐；method=opencitations 为已获取引证元数据；method=existing_lineage 为案卷已有结构化来源；method=ai_review_pending 为经字面引文核对、仍待人工核实的技术三元组。
- 引文、文本相似、共享概念或引用数量均不代表发明新颖性、创造性、权利范围重叠、侵权或工程效果。图谱是发现线索的入口，接下来必须打开原始公开文件逐特征核对。
- 任何保密、内部或受控项目绝不进入 global_public 全局投影；未经真实企业 IAM/ABAC 改造，不向跨用户展示私有项目关系。

## 可重复执行流程
1. 按 patent-autonomous 创建案卷，完成保密分类和外部检索审批后，由 patent-global-search 与 patent-paper-search 收集合法取得的证据。不得额外发送未申请技术到第三方模型/公共 embedding 接口。
2. 对每篇文献确认公开号/DOI、公开日期、引用 URL、可访问 PDF、页码与原文核验状态；仅取得摘要时保留 unverified。
3. 对案卷执行：python -m mechanical_patent atlas-index --case-dir cases/某研究运行 。或调用 MCP patent_knowledge_index。
4. 使用 patent_knowledge_graph(case_id, run_id, scope="document", document_id="EV-...") 查看单文献星图；scope="project" 查看本案卷图谱；字段有上限 max_nodes 与 min_score。
5. 当 AI 在真实存档的标题/摘要/权利要求发现可解释的机械关系时，使用 patent_knowledge_record_fact 登记 subject、predicate、object、真实原文 quote、location。关系仍标“AI待人工复核”，不能在图谱自动升级为事实。
6. 新文献或新三元组登记后重建 atlas-index，生成 document_memory/generated/EV-*.md；人工归纳只能写在 document_memory/manual/EV-*.md。生成文件将更新，人工文件必须永久保护。
7. 调用 patent_knowledge_global_public(max_nodes=...) 查看已批准公开项目跨案卷网络。该工具只允许公开项目，无秘密图谱权限提升参数。
8. 用 atlas-export 或 atlas-global 导出 Cytoscape.js JSON；在 atlas-web 本地导入进行选择、放缩、关系筛选和原始 URL 跳转。前端本地构建，不依赖第三方 CDN。
9. 每次用技术迁移生成新的创新假说时，必须将相似文献 ID、差异特征、来源引句、未验证的机理假设及后续检索计划写入当前案卷；调用 patent-idea-fission 继续多代构思与反证。

## 质量门禁
- 每一条非启发式关系必须能追溯到真实已存来源；导入后仍需专业核验。
- 边的性质与分数分别展示，不做“知识正确率”“授权概率”的虚假推断。
- 局部 SQLite 只作为单用户工具底座；组织生产需要 Keycloak/OIDC、逐项目 ABAC、访问审计、备份与恢复、索引任务队列、许可证/模型权重审批、规模/召回评测。
- 大规模相似检索可选择 sqlite-vec 的本地向量索引；只有取得独立模型许可和数据外发批准才允许云 embedding。LightRAG/GraphRAG 需经过全栈依赖和安全评估，现阶段作为可插拔增强而非强制依赖。
- 删除或更换原始文献后必须重建派生图谱，清理失效引用，并核查保密投影。


## 已有文献长期记忆的联动

仓库已有 patent-literature-memory / LiteratureMemoryStore：每篇文献的权威 Markdown、研究批注、全文/摘要证据级别均应使用 patent_literature_read 和 patent_literature_note 维护，不能在星图派生文件中重复写人工作业。Atlas 的 document_memory/generated 是按文献 ID 关联的只读图谱邻居索引；document_memory/manual 为兼容旧图谱注释，但新增的核实技术论证优先写入 LiteratureMemoryStore。资料被收录到项目文献库，但未进入某次 04_evidence.json 研究运行时，须在当前结论中明确其尚未进入该次案卷星图；后续专门建设跨运行全项目聚合索引。
