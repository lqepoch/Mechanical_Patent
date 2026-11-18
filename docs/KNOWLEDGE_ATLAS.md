# 三级知识星图：按案卷隔离的证据关联与文献记忆

日期：2026-11-18。源码：src/mechanical_patent/knowledge_atlas.py，浏览器：atlas-web/。
系统沿用现有 04b_technology_graph.json、04c_paper_citations.json、04_evidence.json，不将抽取模型写成新的基础依赖，不要求 LLM API Key。

## 三个范围与权限

| 范围 | 数据 | 访问 |
|---|---|---|
| document | 单个 EV-证据编号、提及词项、人工复核候选事实、相似/引用文献 | 仅属于当前真实案卷 |
| project | 该研究运行内所有专利、论文、词项、现有谱系、候选发明、引用和相似度 | 当前本地案卷；项目 SQLite 物理隔离 |
| global_public | 唯一获准标记“公开”的项目与其真实公开文献、项目文献归属、共用公开号/DOI | 白名单式公开投影，不返回其他项目数据 |

注意：global_public 只扫描 workspace/index.sqlite3 中 confidentiality='公开' 的项目。现阶段没有企业级用户登录与 ABAC，私有跨项目星图处于设计阶段，相关能力必须通过真实身份鉴权、逐边权限求交、审计验证后开放。任何“秘密/受控/内部”不出现在现有全局投影中。

## 数据模型和来源强弱

节点类型：专利文献、论文文献、候选词项、候选技术实体、现有图谱中的发明候选/技术特征/实验等、公开项目。

边的 method 含义：
- existing_lineage：04b 原有显式 evidence_id / 来源字段，继续按原工作流审计，不表示其法律结论已成立；
- opencitations：04c 中真实 API 导入的 DOI 引证记录，默认仅引用元数据；
- tfidf_cosine：中英文词项/中文二三字片段生成 TF-IDF 余弦相似度。用于检索候选召回，与全文语义、专利权项等同均有距离；
- lexical：标题/摘要/权利要求统计得出的“提及词项”，不能冒充机械结构真实性；
- ai_review_pending：经本地存档标题、摘要或权利要求逐字对照的 AI 候选关系，仍需查原始文献和工程师审核；
- same_publication：两公开项目中的同一公开号/DOI；
- project_membership：批准公开的项目下同一文献的归属。

后续扩展关系：同族、IPC/CPC 技术分类、正/反引证、权利要求技术特征覆盖、工程约束/失效模式、发明人/申请人/年代、原文图纸部件引用；均需合法著录源和证据标识。

每条文献生成 document_memory/generated/EV-xxxx.md，保留来源、内容 SHA-256、检索关键词、相邻文献。人工修改只能写 document_memory/manual/EV-xxxx.md；机器绝不会触碰该目录。案卷新增证据后须重建图谱。每份知识库快照记录 digest，重复输入时无需重新写 SQLite。

## 命令行

从项目源码目录安装基础 Python 3.11+（无需 LLM）：

    python -m pip install -e .

构建单研究运行知识星图：

    python -m mechanical_patent atlas-index --case-dir private_patent_workspace/cases/PUMP-001/runs/RUN-XXX --top-k 8 --threshold 0.15

导出单文献知识星图：

    python -m mechanical_patent atlas-export --case-dir private_patent_workspace/cases/PUMP-001/runs/RUN-XXX --scope document --document-id EV-XXXXXXXXXXXX --max-nodes 100 --output /私有目录/doc-graph.json

导出项目星图：

    python -m mechanical_patent atlas-export --case-dir private_patent_workspace/cases/PUMP-001/runs/RUN-XXX --scope project --max-nodes 250 --output /私有目录/project-graph.json

仅导出已批准公开项目的全局知识星图：

    python -m mechanical_patent atlas-global --workspace private_patent_workspace --max-nodes 250 --output /私有目录/global-public.json

MCP 服务工具：
- patent_knowledge_index(case_id, run_id, top_k=8, threshold=0.15)
- patent_knowledge_graph(case_id, run_id, scope="project" | "document", document_id="", max_nodes=250, min_score=0.0)
- patent_knowledge_record_fact(case_id, run_id, document_id, subject, predicate, object, quote, location="")
- patent_knowledge_global_public(max_nodes=250)

登记候选关系时必须提交已存原文的 quote。字段长度、关系类型和文献归属严格校验，原文不能对应则返回错误。登记后执行 index，图谱显示 AI待人工复核；没有可校验全文就不能用该接口登记“事实”。

## 浏览器可视化

Web 代码采用 MIT 许可的 Cytoscape.js 3.35.0，Vite 8.3.8 仅用于本地静态打包，线上访问不依赖外部 CDN。

    cd atlas-web
    npm install --no-audit
    npm run build
    npm run dev

浏览器打开本地 Vite 地址，使用文件选择按钮导入 atlas-export 生成的 JSON。所有处理留在浏览器本地；可选择节点、浏览原始 HTTPS 来源、调整词项/预测边/相似阈值与交互布局。生产发布前需提交锁文件、供应链扫描、前端 E2E 与浏览器性能证据。

## 开源组件取舍

| 方案 | 许可证 | 用途 | 当前状态 |
|---|---|---|---|
| Cytoscape.js | MIT | 主交互图 | 已作为 atlas-web 直接依赖 |
| Sigma.js + Graphology | MIT | 万级以上 WebGL 图形 | 预留渲染适配，未引入 |
| sqlite-vec | MIT / Apache-2.0 | 每案卷向量扩展 | 预留；需要审查索引、模型及规模 |
| Microsoft GraphRAG | MIT | 实体关系抽取、社区摘要 | 研究型可选，未接生产调用 |
| LightRAG | MIT | 图与向量混合检索 | 研究型可选，未接生产调用 |
| Graphiti | Apache-2.0 | 具有时间效力的关系记忆 | 研究型可选，未接生产调用 |

官方来源：https://github.com/cytoscape/cytoscape.js 、 https://github.com/jacomyal/sigma.js 、 https://github.com/graphology/graphology 、 https://github.com/asg017/sqlite-vec 、 https://github.com/microsoft/graphrag 、 https://github.com/HKUDS/LightRAG 、 https://github.com/getzep/graphiti 。

## 指标、边界和后续验收

质量指标：人工标注相似文献 Recall@K、权项特征证据锚点命中率、重复 DOI 合并率、未核验误标为已验证的次数（必须为零）、跨保密级别泄露事件（必须为零）、图谱导出可重复率。

稳定性指标：千份/万份文献索引耗时、p95 邻域查询延迟、峰值 RAM、并发索引锁冲突率、结构化文本大小、前端 FPS，以及索引崩溃恢复。

本期离线方案已有：项目级 SQLite、有界计算、词项倒排候选、稳定 ID、幂等输入哈希、证据类型分层、本地可交互 UI、单文献 Markdown 记忆、MCP/CLI 和单测。尚缺：真正大规模 GraphRAG/向量检索、索引任务队列和断点恢复、人工审核工作台、正式多用户 ABAC、专利同族/CPC/法域全量适配、PDF 页面级图节点、图谱精确率黄金评测、前端发布流水线和 SLA。不得把当前版本标为完成生产验收。
