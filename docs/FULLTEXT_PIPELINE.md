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
