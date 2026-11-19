# 论文 PDF 合法获取、离线解析、证据索引和可恢复工作流

更新日期：2026-11-19。服务对象：Mechanical_Patent 项目级知识库和专利研发 MCP。

## 架构与业务边界

已有 OpenAlex、Crossref、Semantic Scholar、arXiv、Europe PMC、PubMed、CORE、Lens 的标准元数据记录，经统一 DOI 去重后保存到每个研发项目自己的 knowledge/literature.sqlite3 和 knowledge/documents/papers/EV-*.md。本阶段对已知合法 OA PDF 链接增加如下真实处理闭环：

1. **文献来源**：meta.pdf_url、metadata.is_open_access、metadata.license、来源 DOI 和原文 URL。缺少真实开放许可证或 PDF 地址时记录 BLOCKED；无授权不得下载。
2. **版权/保密双门禁**：文献需要已知许可白名单（CC0、CC BY、CC BY-SA、公有领域）；通过公司出站审批、人工记录的许可依据和执行授权；付费墙、NC、ND、未知许可直接拦截。来源提供的许可仍需人工独立核验；CLI 审批人字符串不是企业身份鉴权。
3. **受控下载**：调用仓库原有 pdf_archive.download_pdf。仅标准 HTTPS、逐站精确 allowlist、公网 DNS 全地址验证、实际 TLS/SNI 主机名验证、连接到已核准 IP、禁止 HTTP 跳转、文件头验证、最大 40MiB、临时文件与 fsync、内容寻址 SHA256。本机权限加上独立出站防火墙与网络策略才是生产部署。
4. **幂等任务/断点恢复**：FulltextPipeline 在本项目 SQLite 中创建 fulltext_jobs/fulltext_events/fulltext_blocks；任务状态 queued → downloading → downloaded → parsing → parsed；每项保留来源、许可、审批记录、重试次数、30分钟租约、内容哈希、解析哈希、出错原因。中断后原始 PDF 保留，解析可以重试；3次失败后人工重新审核。
5. **离线 Docling**：必须预置已许可的模型资源，禁用远端服务，不从公网下载模型，提取页码/块位置/原文 SHA256/解析器版本。输出永远是 awaiting_original_pdf_review，系统不得把机器抽取或 AI 总结提升为“全文已核验”。
6. **页码证据**：抽取块写入本项目 fulltext_blocks 和可用时的 FTS5 trigram。MCP 按关键词返回 doc_id、page_no、block_no、label、content、source_pdf_sha256；对中文短词和 FTS 不可用时降级 LIKE。
7. **AI 长期记忆**：把机器解析路径、PDF 和解析哈希、样本页码追加到已存在 EV-*.md 的生成证据段之后，重复采集不覆写先前人工研究批注。需要逐篇核实工程公式、控制机理和实验结论时，再由 patent_literature_note 写入有来源位置的分析。
8. **跨项目隔离**：所有 PDF/解析数据位于项目自己的 knowledge/fulltext/。当前每个项目有独立 patents.sqlite3 与文献库，容器中持久化于 /data/projects/项目ID/cases/案例ID/knowledge/。不得把 PDF 放入 Git/GHCR 镜像或共用缓存。

## CLI 操作

研究资料先由 patent_research 或 literature harvest 真实检索并保存，再通过企业流程完成案卷外发审批。下方 project-dir 是具体的案卷路径；权限数据库必须是同项目的 patents.sqlite3：

    python -m mechanical_patent literature \
      --project-dir /data/projects/ENG-001/cases/PUMP-01 \
      fulltext-plan --doc-id EV-XXXXXXXXXXXX \
      --workflow-case-id PUMP-01 \
      --workspace-db /data/projects/ENG-001/patents.sqlite3 \
      --rights-actor "IP-reviewer" --rights-reference "IPR-2026-0001" \
      --rights-approved

确认来源域名和开放许可后，执行实际下载：

    python -m mechanical_patent literature \
      --project-dir /data/projects/ENG-001/cases/PUMP-01 \
      fulltext-process --doc-id EV-XXXXXXXXXXXX \
      --workflow-case-id PUMP-01 \
      --workspace-db /data/projects/ENG-001/patents.sqlite3 \
      --allow-download --allow-host repository.example.org \
      --download-only

有预装 Docling 模型资源时，继续离线解析；已经下载且校验通过的 PDF 不会重复下载：

    python -m mechanical_patent literature \
      --project-dir /data/projects/ENG-001/cases/PUMP-01 \
      fulltext-process --doc-id EV-XXXXXXXXXXXX \
      --workflow-case-id PUMP-01 \
      --workspace-db /data/projects/ENG-001/patents.sqlite3 \
      --allow-download --allow-host repository.example.org \
      --docling-artifacts /data/models/docling

查询：

    python -m mechanical_patent literature --project-dir /data/projects/ENG-001/cases/PUMP-01 fulltext-status --doc-id EV-XXXXXXXXXXXX
    python -m mechanical_patent literature --project-dir /data/projects/ENG-001/cases/PUMP-01 fulltext-search --query "NPSH"
    python -m mechanical_patent literature --project-dir /data/projects/ENG-001/cases/PUMP-01 fulltext-pending --limit 30

注：上面的 EV-XXXXXXXXXXXX 为格式示意，执行时须使用文献库实际返回的 EV-12位十六进制编号。

## MCP 只读接口

- patent_literature_fulltext_status(case_id,doc_id)：返回队列/下载/解析进度、哈希、错误、机器已抽取块数。
- patent_literature_fulltext_search(case_id,query,limit)：返回页码、文本块与 PDF SHA256，所有返回附 unverified review status。
- patent_literature_fulltext_pending(case_id,limit)：返回有界等待/失败任务列表；不返回 API Key 和任意文件读取能力。

MCP 不直接开放许可登记或下载行为：当前尚未实现可验证的企业 OIDC 身份以及版权审批签名；仅采用可核验权限的受控 CLI 完成。企业级远程写入需后续部署 OIDC/ABAC、签名/审批任务与受控 Worker，才可在 MCP 中放开敏感执行。

## 故障、恢复及可观测性

- 文件不完整/HTML 冒充 PDF：拒绝并保留错误及来源 URL，检查供应商许可与真实 PDF 地址。
- 外部 PDF 下载成功、Docling 失败：状态 downloaded，带原文哈希，可重试解析；绝不重新抓取相同合法 PDF。
- 单机重启、服务异常：本地 SQLite WAL 保存任务、租约、阶段、出处与文档内容，租约 30 分钟到期后可再次领取；超过尝试上限需人工复查。
- 元数据刷新：只更新生成著录区，技术人员批注和已形成的机器解析记录保留。
- 推荐指标：合法 OA 命中率、下载通过率、PDF hash 校验通过率、块数/页数、解析失败率、任务年龄、待人工核验文献数、单来源请求数和版权拒绝数。
- 真实 SLA：机器模型 OCR/表格/公式质量需要项目专业验收；此版本只通过离线合成测试，无真实机构许可、未进行上千篇样本的现场容量测试。Docker 默认镜像只安装 mcp，不预装重量级 Docling；批准模型权重、镜像资源上限和进程隔离后单独部署解析 Worker。

## 可吸收的开源方案

- OpenPapers MCP (MIT) — https://github.com/Kaago/openpapers-mcp 。用于核查 OpenAlex/Crossref/Unpaywall 元数据和 SSRF 安全下载设计；优先复用当前仓库已有的更严格固定 IP + TLS 下载器，避免重复引入不受控的远程执行服务。
- OpenAlex 官方 CLI — https://help.openalex.org/access/fulltext/ 。在大批量、许可明确的 OA 文献场景可作为可选 Provider，需专门校验内容许可和配额。
- Docling — https://docling-project.github.io/docling/ 。用于本地文档转换，允许离线权重；本仓库保留现有的 docling 可选依赖。
- GROBID — https://grobid.readthedocs.io/en/latest/Grobid-service/ 。作为未来引用解析和 TEI/公式校正的可选服务，不作为本次 Docling 默认替代。

## 验证与升级

CI 增加 test_literature_fulltext.py 统一测试：许可拦截、OA 来源、安全域名、原文哈希、无原文场景、失败恢复、页码搜索、SQLite 增量迁移、人工批注不覆盖和 MCP 读权限。保持独立项目数据库、旧 CLI、原有检索、专利反证及 LaTeX 业务功能不回退。

后续在生产前补齐：来源许可凭证的不可抵赖签名、实际账户联调、全量 PDF 下载测试、病毒隔离沙箱、集中速率/费用控制、事务 Outbox、分布式 Worker、PDF/图表质量基准、灾备回滚及版税许可审查。按数据权属需要设置内部访问控制、定期备份和删除/保留期策略。

## 页码级原文短引核对与研究记忆门禁（2026-11-19）

现有 FulltextPipeline 可直接验证机器解析页码：status=parsed 且 current fulltext_jobs.pdf_sha256 与 fulltext_blocks.source_pdf_sha256 一致，证据位置采用 p{page}:b{block_no}（例如 p3:b2），并确认文献位于当前案卷。缺页码、过期 PDF、无效块均明确拒绝。该校验基于当前结构化 PDF 解析结果，不能代替人工打开原文核验。

新增的工具：CLI 在 literature 子命令下运行 fulltext-quote --doc-id EV-12位十六进制编号 --anchor p3:b2 --verbatim "从原文抽取的短引"；MCP 使用 patent_literature_fulltext_quote(case_id, doc_id, anchor, verbatim)。返回 exact_match、quote_sha256、block_sha256、source_url、pdf_sha256、parse_sha256、full_text_verified=false 与 verification_level=parsed_text_match_only。

AI 通过 patent_literature_note 以 basis=full_text 写入研究批注时，source_positions 需要1至30个真实的页码/段落锚点，文献数据库会独立验证引用并向 Markdown 追加源 PDF 与解析版本 SHA256。较低层级的摘要级笔记不强求 PDF；不合格的全文证据需要补读实际原文。需留意 PDF 更新后旧笔记的适用性，未来 #52 继续实现引用失效后的自动复核队列。

此功能复用全文流水线现有的 fulltext_jobs、fulltext_blocks、fulltext_blocks_fts，无第二套数据表，避免与其他项目分支重叠。离线回归 test_fulltext_quote.py 覆盖未解析拒绝、真实匹配、错误页码、跨案卷、跨项目和 PDF 哈希变化。

## DOI 开放获取线索（2026-11-19）

资料库里的 DOI 可以经项目出站审批使用 literature oa-enrich 查找 Unpaywall 公共 OA URL/许可线索，保留跨平台提供方谱系。它仅更新机器元数据；仍须通过此文的 fulltext-plan 完成版权/人工授权核验，再经 fulltext-process 下载、解析和存档。来源许可冲突将阻断旧授权继续使用。

## 项目级 PDF 批次、预算与断点恢复（2026-11-19）

复用唯一的 `FulltextPipeline` 下载/版权状态机及 Docling 页码证据索引；`FullTextBatchRunner` 只提供多篇调度、项目独立 SQLite 检查点、失败隔离和重复执行恢复。新增 `fulltext_batches`、`fulltext_batch_items` 记录按清单哈希生成的 FTB 批次、文献序号、状态、次数、PDF SHA256 和截断错误信息，不修改已有机器解析及真人复核结论。

受控清单是 JSON 对象 `{"items":[{"doc_id":"实际EV编号","rights_actor":"许可审核人","rights_reference":"真实授权记录号","allowed_hosts":["publisher.example.org"],"parse":true}]}`。每篇必须核对公开许可、实际 PDF 候选 URL、下载主机和来源授权；`rights_actor` 仅作为审计信息，不能代替真实鉴权/人工审批。需要经项目审批的 CLI：

```bash
python -m mechanical_patent literature --project-dir /secure/projects/P1/cases/CASE01 fulltext-batch \
  --manifest /secure/approved-batch.json --workflow-case-id CASE01 \
  --workspace-db /secure/projects/P1/patents.sqlite3 \
  --rights-approved --allow-download --allow-search-exposure \
  --docling-artifacts /secure/docling-models --max-documents 100 \
  --max-seconds 900 --max-total-bytes 2147483648 --max-attempts 3
python -m mechanical_patent literature --project-dir /secure/projects/P1/cases/CASE01 fulltext-batch-status \
  --batch-id FTB-实际20位十六进制 --state failed --limit 100
```

同一份规范化清单返回确定性的 FTB 标识。断点恢复跳过与原文管线仍匹配的完成条目，常规解析重试复用已归档且哈希校验通过的 PDF。达到本批逐篇重试上限须重新审批后显式 `--refresh`；批次汇总区分失败总数、可重试数和已达本轮上限数。刷新重试不会重跑仍匹配的完成条目。

`--max-total-bytes` 统计本轮下载器成功返回的 PDF 字节，即使后续解析失败也计入；读取缓存不计为新下载，不等同于传输中断时的网络流量计费。`--max-seconds` 在两篇之间检查，不会强行取消已开始的单篇下载或解析。批次 complete/partial 不能证明全文技术结论已由人工核验。

状态查询每页最多 200 条，默认不筛选；可用 `--state pending|done|failed`，或将返回的 `next_cursor` 传给 `--cursor` 继续扫描同一筛选条件。`counts` 始终为整批计数，`matched_total` 为查询时符合筛选条件的条目数；`next_cursor=null` 表示没有下一页。执行中的条目状态可能变化，排查最终失败前可重新从第一页查询。MCP 只读工具 `patent_literature_fulltext_batch_status` 也支持 `state`、`cursor`，不开放批量远程下载。
