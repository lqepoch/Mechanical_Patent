# 专利 + 论文：双源检索与创造性反证

## 为什么必须同时检索

专利文献显示结构、系统、控制方法的保护边界、公开实施例及技术路线。
学术论文显示物理机理、数学模型、参数规律、材料、工艺、实验局限和异行业方法。
两类文献都可能构成现有技术。论文的学术新颖性和专利的法律创造性是不同评价目标，独立分析。

## 当前提供的数据接入

| 数据源 | 无模型 API | 数据范围 | 缺口 |
| --- | --- | --- | --- |
| EPO OPS | 是 | 授权检索元数据、部分权利要求 | 需要 EPO 数据账号，国家/全文覆盖有限 |
| OpenAlex works | 是 | 学术论文标题、DOI、发表日期、可用摘要倒排索引 | 匿名额度有限；全文通常需要另行获取 |
| Crossref works | 是 | 学术 DOI、书目信息、可用 JATS 摘要 | 多数记录没有全文，部分无摘要 |
| Imported fixture | 是 | 用户提供的本地专利/论文元数据 | 全部标记未核实 |
| Crawl4AI | 是 | 经许可的学术网页、技术公开页正文 | 网站权利/robots、反爬限制、SSRF 网络隔离 |

OPENALEX_API_KEY（可选）只是论文数据库服务额度，不是 LLM 推理 Key。Crossref 可用 PATENT_CONTACT_EMAIL 进入 polite pool，必须用真实自己可控制的地址。实际完整的 CNIPA、USPTO、WIPO、Patsnap 数据链仍属后续集成 Issue，不以单一数据库冒充全球覆盖。

## 8 步双源工作流

1. AI 将技术问题拆成应用场景、待解决问题、已知手段、可替代物理机理和约束。
2. 专利检索：中英关键词、IPC/CPC、全文/权要、发明人/企业、同族引证和近义词。
3. 论文检索：工程科学原理、模型变量、未解决实验难题、异行业机理迁移。
4. 论文/专利归一化：DOI、公开号、日期、作者/申请人、来源、摘要/权要全文状态、技术机制。
5. 首轮技术路线与空白分析：限定“在本次已检索源范围内”。
6. 多 Agent 独立设计并行：TRIZ、SCAMPER、FMEA、跨领域迁移和激进但物理自洽方案。
7. 对每个新发明再次进行专利与论文反证；核对特征是否已有公开，以及组合动机；以真实公式及工况检查实施可能性。
8. 选择具有明确技术贡献、可再现实施路径且风险可审查的构思，生成中国申请草稿及支持矩阵。

## 统一数据结构与门禁

Evidence:
- publication = 专利公布号 / 规范化 DOI / OpenAlex ID
- kind = patent | paper | web | standard | manual
- source = 源数据供应方，如 epo-ops / openalex / crossref / crawl4ai
- title, publication_date, retrieved_at, url, abstract, claims（通常仅专利）
- verified = 是否由在线源直接获取其元数据（不代表学术内容、结论或法律状态真实）
- evidence_id = 与证据类型和出版标识绑定的稳定哈希

论文在 OpenAlex/Crossref 中同 DOI 自动去重；未提供 DOI 时使用学术机构记录 ID。完整权利要求、实际论文全文、法律状态和真值核对需要单独完成。

注意：不因同一技术方向检出“0 条文献”就宣称全球没有现有技术。检索结果数目、可获取全文比例、语言/时间/来源缺口均需报告。

## 举例：消防车高海拔吸水

Patent queries:
- high altitude fire pump vacuum priming system
- centrifugal pump inlet gas separator
- suction pipe air entrainment control

Paper queries:
- cavitation inception centrifugal pump low ambient pressure
- two phase air water flow priming hydraulic system
- NPSH atmospheric pressure elevation
- entrained gas bubble separation in pump inlet

AI 再把论文的流动机理、汽蚀阈值、传感控制和材料知识转换为物理实现候选，逐个进行逆向文献检索、工程约束检验及专利权利要求对照。

## 论文扩展方向

后续加 arXiv 官方 API（速率合规）、OpenAlex DOI 引证网络、Crossref references、Semantic Scholar Academic Graph（授权限制核对）、CORE/高校仓储及合法开放获取全文。独立搜集高质量中文科研期刊元数据（以官方许可和来源为准）。验证数据覆盖、检索召回率、交叉语言别名与 PDF 可读性后再扩大系统规模。

截至 2026-11-18 的官方资料：
- OpenAlex API Authentication: https://help.openalex.org/api/authentication/
- OpenAlex API Reference: https://help.openalex.org/api/
- Crossref Public API: https://www.crossref.org/documentation/retrieve-metadata/rest-api
- Crossref authentication & rate limits: https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/


## 千篇双源文献的增量检索、落盘与研读

新增 literature CLI 和 patent_literature_* MCP 工具。单词默认预算最多1000条、每页100、最多30页或600秒；预算是上限，不等于一定发现1000篇，也不意味着查全所有专利。官方 OpenAlex Cursor 超过第一页需要免费 API Key；Crossref cursor 约五分钟会过期，可从头幂等重检；EPO OPS 免费额度与频率受官方公平使用政策控制。论文来源合法元数据、摘要、权利要求与全文必须分别记载可用性。

    python -m mechanical_patent literature --project-dir private/cases/X01 stats
    python -m mechanical_patent literature --project-dir private/cases/X01 search --query "消防泵汽蚀"
    python -m mechanical_patent literature --project-dir private/cases/X01 pending --limit 20
    python -m mechanical_patent literature --project-dir private/cases/X01 harvest --provider openalex --provider crossref --query "centrifugal pump cavitation" --workflow-case-id X01 --workspace-db private/index.sqlite3 --max-documents 1000 --allow-search-exposure

每发现一篇资料，立即生成带证据编号和可打开链接的 Markdown。AI 按每批10–30篇进行白话技术解读，记录原理、结构、控制、参数、作用效果、缺点、反证、创新点和跨文献连接；basis 标记 metadata/abstract/claims/full_text，声称读过完整原文必须记录页码/章节。研究快照 RESEARCH_RESUME.md 保存当前事实、发明候选、未解决问题、下次任务。元数据自动成文不等于实质读完。

开源复用：官方 OpenAlex、Crossref 元数据 API；已有引证扩展 OpenCitations；合法全文可接已有 Docling PDF 解析、PaperQA2 证据检索方式及 GROBID TEI，但要核查模型权重、版权和使用许可。大规模批量离线可评估 OpenAlex Snapshot，降低反复 API 查询成本。专业检索覆盖用已授权的召回金标准持续验证。

## 论文检索多来源标准接口（2026-11-18）

统一论文记录扩展 `Evidence.pdf_url` 和 `Evidence.paper_metadata`（包含 `doi`、`authors`、`citation_count`、`is_open_access`、`oa_status`、`license`、`source_ids`、`sources`、`pdf_link_status`、`full_text_verified`）。统一 DOI 合并各渠道摘要及来源 ID，保留 URL 来源和真实性区分，原生无 DOI 编号保留，不猜测跨来源同一性。

平台：OpenAlex、Crossref、Semantic Scholar、arXiv、Europe PMC、PubMed 为默认可选来源；CORE、Lens 加显式凭证和付费/许可证门禁。Unpaywall 为 DOI→OA PDF 位置增补，不能关键词检索。入库文档仅表示来源元数据，`full_text_verified=false`，真实 PDF 解析和版权审核另由批准流程处理。每次研究运行会生成逐篇 `03_paper_memory/EV-*.md` 和 SHA256 清单，作为长上下文研究的持久记忆。

CLI `paper-sources` 列举来源能力；`research --paper-provider arxiv --paper-provider openalex --enrich-unpaywall` 可组合使用；MCP `patent_research(paper_sources=[...],enrich_unpaywall=true)` 保持同一行为。外发保密审批、按案例 SQLite 隔离、授权 API 配额和提供方错误报告保留。技术细节见 [docs/PAPER_SOURCES.md](PAPER_SOURCES.md)。
