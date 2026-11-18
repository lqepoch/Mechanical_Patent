# 论文多平台检索、统一转换与案卷记忆

2026-11-18。机械发明研发项目统一学术数据源与操作规则。

## 来源选择矩阵

| 来源 | 最适合的需求 | 身份与费用边界 |
| --- | --- | --- |
| OpenAlex | 全领域论文/引用/OA 发现 | 免费预算及超额按量，OPENALEX_API_KEY 可选 |
| Crossref | DOI、出版社、发表日期核验 | 公共 API，PATENT_CONTACT_EMAIL 可选 |
| Semantic Scholar | 学术关联/引用/开放 PDF 线索 | SEMANTIC_SCHOLAR_API_KEY 可选，有限额 |
| arXiv | 物理/机械/算法预印本 | 免费 Atom XML API，限制查询频率 |
| Europe PMC | 医药、材料和生物跨学科 | 免费 REST，部分开放全文 |
| PubMed | 医学与生理学线索 | 免费 E-Utilities，NCBI_API_KEY 可选 |
| CORE | 开放仓储、机构学术文献、全文线索 | CORE_API_KEY；机构商用须复核条款 |
| Lens | 论文被专利引用与学术专利融合 | LENS_API_TOKEN；机构订阅授权 |
| Unpaywall | 已知 DOI 的合法 OA PDF 位置 | UNPAYWALL_EMAIL；仅富化 DOI，不做关键词检索 |

推荐默认：OpenAlex + Crossref + Semantic Scholar；前沿物理/控制加 arXiv；生物/医疗加 Europe PMC + PubMed；有企业商业许可时可用 CORE / Lens。DOI 已知、需要公开 PDF 时开启 Unpaywall 富化。

## 标准数据契约

继承 src/mechanical_patent/core.py 的 Evidence 标准模型，论文记录在原始 publication/title/url/source/retrieved_at/abstract/verified 字段外增加：

- pdf_url：仅存合法 HTTPS 候选位置，不能假定有效和已授权。
- paper_metadata.schema_version：当前为 1。
- paper_metadata.doi：统一小写的 DOI；无 DOI 则保留 arxiv/pmid/core/lens 的原生标识。
- paper_metadata.authors：已识别作者姓名列表。
- paper_metadata.citation_count：提供方可用的引文计数，非普遍一致的真值。
- paper_metadata.is_open_access、oa_status、license：从提供方披露的开放与许可信息。
- paper_metadata.source_ids：每个数据源的原生文献 ID 映射。
- paper_metadata.sources：统一合并结果来自哪些平台。
- paper_metadata.pdf_link_status：unverified_discovery 或 not_found。
- paper_metadata.full_text_verified：固定初始 false，必须独立核验 PDF 原文才能升级。

同 DOI 将不同来源合并，优先保留较完整的摘要和补充来源 ID；无 DOI 跨平台文献不凭标题相似度强行去重。metadata verified 只指从来源 API 获取了元数据，不代表论文科学结论被验证。

### 实例：单轮指定多个平台

    python -m mechanical_patent paper-sources

    python -m mechanical_patent research \
      --direction "高海拔消防泵吸水汽蚀" \
      --paper-query "high altitude centrifugal pump cavitation" \
      --paper-provider openalex --paper-provider crossref \
      --paper-provider semantic-scholar --paper-provider arxiv \
      --enrich-unpaywall --unpaywall-limit 15 \
      --allow-search-exposure --case-dir cases/high-altitude-pump

使用 CORE/Lens 时，还需合法企业许可、对应 API Token 和 --allow-paid-paper-apis。paper-provider all 只自动包含明确符合商业授权门禁的付费源；数据源断线/限额会保留错误并继续使用其他可用渠道。

### MCP 统一接口

- patent_capabilities 返回 paper_sources，每个包含 id、capability、description、commercial_license_gate、configured。
- patent_research 保留 case_id、patent_queries、paper_queries、limit，增加可选 paper_sources、enrich_unpaywall、allow_paid_paper_apis。
- MCP 仍先检查 LocalPatentWorkspace 当前轮保密外发批准。无授权直接阻断，不向任何平台发送敏感词。
- 单次结果写入 03_papers.json 与 04_evidence.json，调用原有案卷质量和审计流程。

### 本地 SQLite 和长上下文记忆

SQLite documents 表新增 paper_metadata_json；启动时检查列并执行向后兼容迁移，原有文献核验信息不因迁移删除。每一篇论文建立 03_paper_memory/EV-编号.md 并写入 manifest 的 SHA256 哈希，包括：DOI、作者、标题、来源、PDF 候选 URL、许可、摘要以及后续待核验的方程、工况、实验、工程迁移、反证任务。相同项目应重复加载存档而不是在上下文压缩后重新检索。不能把摘要卡片标记为已阅读全文。

### 工程安全、运营边界和未来扩容

1. 所有远程检索须通过已有保密审批；严禁上传内部 CAD/BOM、客户材料或尚未申请的新发明细节。
2. 按提供方文档和合同执行授权、费率与访问限制。普通 API Key 不等于购买了商业数据再分发许可。
3. 单次返回保留原有每来源每检索式最多 25 篇的有界限制；千篇检索可通过多轮和多查询组合取得，但尚未实现全量游标分页、跨进程统一限流、增量任务队列及持久断点续传。此部分需在后续企业级扩展阶段完成。
4. 目前仅进程内保守限流，长时间和跨实例部署需要 Redis 等集中配额、429 Retry-After 退避、熔断、预算上限和来源健康监控。
5. PDF 文件需要经版权、许可、保密审核后才能下载；逐页验证及 Docling 结构化抽取单独执行。候选 PDF URL 是元数据线索，不是已取得 PDF。
6. 质量检查包含 DOI 归并、版权字段、失败覆盖、 SQLite 迁移、MCP 协议及跨来源样例；供应商真实网络连通性/商业授权须用受控账号验证。

### 官方资料（2026-11-18）

- OpenAlex https://help.openalex.org/api/authentication/
- Crossref https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- Semantic Scholar https://api.semanticscholar.org/api-docs
- arXiv https://info.arxiv.org/help/api/user-manual.html
- Europe PMC https://europepmc.org/RestfulWebService
- NCBI E-Utilities https://www.ncbi.nlm.nih.gov/books/NBK25501/
- CORE https://core.ac.uk/services/api
- Lens https://docs.api.lens.org/request-scholar.html
- Unpaywall https://unpaywall.org/products/api


## 论文 PDF 权利门禁与机器页码证据（2026-11-19）

项目级 `LiteratureMemoryStore` 现在可以记录原生 `pdf_url`、`paper_metadata_json` 和跨检索批次来源谱系；原有分析笔记保持独立且不被新元数据覆盖。新增 `PaperFullTextService` 将论文 PDF 分为 `not_downloaded → downloading → downloaded → parsing → parsed_unverified`，失败为 `download_failed` 或 `parse_failed` 并允许重试。仅在检索词外发获批、合法全文使用依据可查、域名白名单和明确操作授权同时满足时触发下载。

下载调用已有 DNS 钉扎 HTTPS/PDF 头/大小上限/不跟随重定向的 `download_pdf`；按 SHA256 内容寻址，留在项目私有 `knowledge/pdf_objects`。离线解析重用 Docling `parse_local_pdf`，模型须预装本地 artifacts，输出 `knowledge/pdf_extracted` 的逐页 JSON。自动状态写入论文 MD 的机器区，研究人员/AI 批注区长期保存，全文结论标记待原始 PDF 复核。

本次 MCP 增加只读 `patent_paper_pdf_status` 和 `patent_paper_pdf_page`；写入操作通过具有企业权限审计的本地 CLI `literature pdf-fetch` 和 `literature pdf-parse` 执行。任何 AI 不得自行猜测版权许可，不得从未核实的机器提取中产生已验证的实验结论。操作和状态见 [PAPER_FULLTEXT.md](PAPER_FULLTEXT.md)。
