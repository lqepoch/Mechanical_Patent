---
name: patent-citation-discovery
description: "在检索专利和论文之后，使用 OpenCitations 官方 DOI 引证接口查找一篇科研论文的参考文献、被引研究与跨学科潜在突破口，将引用关系和核验状态保存到现有专利研发案卷；当前 ChatGPT/Codex 自行分析，不需要额外语言模型。"
user-invocable: true
---

# 论文引证扩展与跨领域创新线索发现技能

## 使用时机

专利和论文首轮检索完成后，或当前 AI 发现某个机械原理、材料模型、控制算法来自论文，需要进一步追踪其前驱工作和新一代改进时使用。与 patent-autonomous、patent-paper-search、patent-countersearch 协同执行。

## 目标

把一篇真实公开论文的 DOI 作为种子，查询“该论文引用了什么”以及“后来哪些论文引用了它”，形成时间和来源可追溯的引证图谱，提出新的检索关键词、机理迁移方向及发明反证思路。

本技能由当前 ChatGPT/Codex 的模型执行归纳和创新，Python 只负责 API、DOI 规范化、去重、证据存储与图谱更新。无需配置 LLM API Key。

## 输入资料

- 真实公开论文 DOI（优先来自 03_papers.json 已检索的科研论文）。
- 已存在的技术研究案卷，包含 00_intake.json、04_evidence.json 和原始检索日志。
- 对外查询授权；未公开发明完整结构、内部 CAD、工艺秘密不得写入外部论文检索请求。
- 可选已有工作流数据库和审批状态。

## 工作步骤

1. 检查 DOI 的真实性、规范化与来源；严禁把网页标题或内部项目代号当 DOI。
2. 记录本次授权、种子 DOI、查询时间和每次返回的引用方向及数据源。
3. 对 1–8 个 DOI 分别执行 references（参考文献）与 citations（被引论文）查询，单方向最多返回 50 条，防止递归无预算扩张。
4. 使用 OpenCitations Index v2 官方 API 获取结构化关系。数据内容由开放引证数据库提供，但不能推定科研成果真实可靠、论文已读或全文已获取。
5. 将每一批次保存到 citation_batches/，并合并至 04c_paper_citations.json；生成或更新 04b_technology_graph.json，关系为“论文引用论文”。
6. 当前 AI 依据新 DOI 清单，使用 OpenAlex、Crossref、arXiv 等来源进一步检索真实论文标题、年份、全文及技术机理；允许访问的网页正文交给 Crawl4AI。
7. 对可迁移到机械结构或控制算法的科研方法标注：核心物理原理、原论文的假设、适用工况、潜在限制、转用于本发明的实际实施手段，以及已知反例。
8. 针对每个候选发明，将新论文与专利 D1/D2 并列进行二次反证检索，不能用论文数量或引证频次替代中国发明专利的创造性审查。

## 命令行示例

先通过 patent-autonomous 创建或导入案卷，然后执行：

    python -m mechanical_patent citations --case-dir cases/已有案卷目录 --doi 10.5555/实际论文DOI --direction both --max-links 25 --allow-search-exposure

对于已经绑定了项目工作流的案卷，额外指定 --workflow-case-id 与 --workspace-db，工具会要求当前轮次通过出站保密审批。

## 交付产物

- 每批次引证 JSON、完整 DOI 查询 URL、检索时间、错误、限额。
- 04c_paper_citations.json：去重后的引用关系、种子和待进一步核验的 DOI。
- 04b_technology_graph.json：现有论文证据与新增“仅引证元数据”的节点/引用关系。
- 研究下一轮的候选 DOI 与实际技术检索任务。
- 专利与论文再检索后的发明创新反证报告。

## 硬性门禁

OpenCitations 引证网络具有数据覆盖缺口；引用关系不能证明论文理论、专利新颖性或工业可实施性。新增节点必须标记“仅引证元数据、未核实全文”，不得虚构论文标题、实验数据或授权状态。

来源：OpenCitations 官方 API 文档 https://api.opencitations.net/index/v2 ；代码来源 https://github.com/opencitations/oc_api 。OpenCitations 开放数据许可和 API 访问条件应定期复核。



## 引证文献的长期记忆

对新增真实 DOI 引证节点，通过 OpenAlex/Crossref 填写可核查的标题、DOI、来源和摘要，再导入项目知识库形成一文一篇 MD；原始 DOI 引证关系的发现不等于取得论文全文。用 patent_literature_note 将前驱实验、后续改进、跨学科机理迁移和反证线索写进各篇文献，最终更新 RESEARCH_RESUME.md 记录仍需验证的引用边。