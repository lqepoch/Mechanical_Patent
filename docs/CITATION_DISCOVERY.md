# 学术引证网络增强：OpenCitations × 跨领域发明挖掘

检查日期：2026-11-18。

## 目标

在 Mechanical_Patent 原有的中国及全球专利检索、OpenAlex/Crossref 论文检索、IdeaForge 技术图谱与专利反证流程上，增加一条真实的科学文献引证网络：

种子 DOI → 论文引用的前驱研究（references）/后来的改进研究（citations） → 真实论文元数据与公开正文 → 技术机理、工程边界和跨领域方案 → 逐候选专利及论文反证。

用户仍由当前 ChatGPT/Codex 执行推理，工具只是 DOI 引证数据和本地案卷管理。无需本地 LLM 服务、Ollama 或模型 API Key。

## 开源项目选型

1. OpenCitations / oc_api：ISC 许可证，已经核查并固定上游代码。OpenCitations Index v2 官方 API 提供 references、citations、OCI、创建日期等信息；无需额外模型。引用数据在开放许可下使用，但必须遵守公平访问和来源标注。
2. Future-House / paper-qa：Apache-2.0 许可证，成熟的学术 RAG、证据定位、多元元数据和引用感知方法。上游默认包含额外语言模型/embedding 配置，本仓库不启用其模型工作流，仅提供固定源码用于合法研究和经过接口拆分后的选择性复用。
3. google / patents-public-data：Apache-2.0 许可证，已于 2026-04-18 归档。保留其 SQL 专利地图、Claim Text Extraction、Claim Breadth 示例作为参考，不在生产中盲用过时的 BigQuery 表结构。
4. OpenCitations / oc_docs：官方 API 接口文档，引用接口按当前版本规范接入；作为文档来源，不依赖额外私有账号。

## 现在可运行

- src/mechanical_patent/citations.py：官方 API DOI references/citations 查询、公共标识解析、限定 8 个种子/50 条单方向引用、网络失败记录。
- src/mechanical_patent/case_citations.py：把每批数据保存在当前研发案卷，累计图谱和时间日志，记录 SHA-256 与可复核事件。
- src/mechanical_patent/lineage.py：将论文引用关系写入发明证据图谱，区分已验证的 OpenAlex/Crossref 来源文献与仅从引证关系发现的 DOI。
- skills/patent-citation-discovery/SKILL.md 与 .agents/skills/ 镜像：当前 Codex/ChatGPT 研究流程直接调用。

## 使用示例

需要已有案卷，先经过保密审批及实际授权：

    python -m mechanical_patent citations --case-dir cases/已建案卷 --doi 10.1162/qss_a_00023 --direction both --max-links 20 --allow-search-exposure

这里的 DOI 是 OpenCitations 文档公开示例，只用于说明接口格式，未声明其与消防泵发明有关。

输出：
- citation_batches/<hash>.json：每批原始来源响应归一化、时间、查询 URL、错误和上限。
- 04c_paper_citations.json：累计 DOI 引证网络，检索方向、节点、边、待进一步核验 DOI。
- 04b_technology_graph.json：沿用机械发明原有技术图谱，加入“引用”关系。
- events/*.json + manifest.json：审计事件与文档哈希。

## 生产边界与后续

- 引证库只返回引用记录，不能替代 Crossref/OpenAlex 的论文元数据，也不意味着已合法取得 PDF 全文。
- 需要对引用路径增加来源覆盖率、年份过滤、动态采样、DOI 元数据富化、论文撤稿/勘误监控和非 DOI 引证的适配。
- 可评测 citation-recall@K、跨领域原理归纳正确性、引证原文定位准确率，以及对最终专利 D1/D2 反证召回的贡献。
- 真实企业部署需要 PostgreSQL 案卷、任务队列和项目审批，而当前 SQLite/事件文件只是本地基础。
- 若要把 Google BigQuery 专利分析样例用于生产，必须先按最新 BigQuery 表结构和数据授权审查重新编写查询与成本上限。
- 不得把 PaperQA2 的自动外部模型调用作为默认依赖；其原理仅可在符合本项目当前 AI 客户端模式时重构。

## 核实来源

- OpenCitations Index v2: https://api.opencitations.net/index/v2
- OpenCitations API Quickstart: https://github.com/opencitations/oc_docs/blob/main/docs/api/quickstart.md
- OpenCitations 代码: https://github.com/opencitations/oc_api
- PaperQA2: https://github.com/Future-House/paper-qa
- Google Patents 分析示例: https://github.com/google/patents-public-data
