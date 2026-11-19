---
name: patent-fulltext-processing
description: "审批论文开放许可、项目出站权限与 PDF 安全获取，使用离线 Docling 解析文献并建立带 SHA256、页码和可恢复状态的项目级技术证据索引。"
user-invocable: true
---

# 科研论文合法全文流水线

## 使用场景
用户要求批量获取合法公开论文 PDF、抽取机理/方程、建立逐篇文献记忆、让 MCP 按原始页码查询科研依据时，读取本技能和 docs/FULLTEXT_PIPELINE.md。

## 安全与许可门禁
- 每个具体案例必须已经通过真实保密外发审批；内部保密 CAD/BOM 和未公开交底绝不可外送。
- 只允许供应商明确提供 `is_open_access=true`、存在安全 HTTPS PDF 地址且许可证属于 CC0/CC BY/CC BY-SA/公有领域白名单的论文进行自动化归档。其他情况记录缺口，进行人工版权核验或另行申请授权。
- CLI 需要每篇逐条批准、真实许可记录编号和精确域名 allowlist；审批人字符串只供审计，不构成企业身份验证。远程 AI MCP 暂仅可读查询，不能办理许可审批或任意下载。
- 使用项目内已集成的 pinned HTTPS/SNI TLS、公网 IP 固定、PDF magic 与 SHA256 验证；不得重定向/绕过付费墙。
- 解析必须使用预置离线 Docling 模型资源，不自动联网下载权重。

## 执行步骤
1. 检索本项目 knowledge/INDEX.md 与单篇 EV-*.md，查看来源元数据、公开许可、PDF URL 和已有关联证据。
2. 核对论文原始 DOI/许可证与审查记录，完成 `literature ... fulltext-plan`；不达条件立即报告拒绝原因。
3. 在授权 CLI 中执行 `literature ... fulltext-process`，若只归档 PDF 使用 `--download-only`；需要解析时加 `--docling-artifacts`。
4. 获取 `fulltext-status` 与项目文献记忆，确认原始 PDF SHA256、离线解析哈希、机器提取页码块及未人工复核标记。
5. 调用 MCP `patent_literature_fulltext_search` 结合 `patent_literature_read` 对技术事实逐项定位；仅人工打开原始 PDF 核验后，才在 `patent_literature_note` 中标记有依据的全文分析。
6. 重新检索或上下文压缩后按 `knowledge/RESEARCH_RESUME.md` 与每篇 MD 恢复记忆。原文失效或解析失败从状态队列恢复，达到重试上限提交人工审查。

## 输出
PDF 候选 URL、许可证/审查来源、SHA256、解析器版本、解析 JSON、段落/页码级可检索证据、任务状态及失败日志、原单篇 Markdown 机器解析附录。现有科学论文或专利的法律结论不得由机器解析状态直接推出。

## 生产级边界
需额外部署真实 OIDC/ABAC、签名版权审批、统一配额/预算、资源隔离及内容安全扫描方可向企业全面开放下载服务。Docling 的页码/表格/公式定位准确率依靠人工和真实 PDF 金标准集合验收。

## 当前原文页码与短引审查门禁（2026-11-19）

- 合规完成本案卷 fulltext-process 后，从 patent_literature_fulltext_search 获取 doc_id、page_no、block_no 和 source_pdf_sha256，使用 p{page}:b{block}（例如 p3:b2）标注研究引用。
- 调用 patent_literature_fulltext_quote(case_id,doc_id,anchor,verbatim) 逐字检查短引是否存在于当前解析版本，返回 exact_match、PDF SHA256、解析 SHA256 和 parsed_text_match_only。解析文本命中仍须打开原始 PDF 检查错字、公式、表格和图纸。
- patent_literature_note(basis=full_text) 必须携带1–30个实际存在的 source_positions；程序拒绝错误页码、缺失段落、其他案卷或已更换 PDF 的失效引用。每个 Markdown 研究批注自动记录 PDF 与解析版本 SHA256。
- 沿用现有 FulltextPipeline、fulltext_jobs、fulltext_blocks 和 FTS5，禁止创建重复的同名全文索引表。接口详见 docs/FULLTEXT_PIPELINE.md。

## 统一全文管线与 DOI OA 候选补全（2026-11-19）

目前唯一的原文获取、审核和解析执行器是 FulltextPipeline；禁止引入第二套并行下载状态机。外部论文 DOI 通过经批准的 literature oa-enrich 查询 Unpaywall，只更新 OA 候选 URL 与许可线索。随后核查最新公开许可，人工登记 fulltext-plan 并通过受限 fulltext-process 获取 PDF，保存 SHA256/页码/许可审计，所有机器解析保持待核验状态。不同供应商许可证冲突时封锁旧授权；旧研究 MD 必须保持可恢复。详见 docs/FULLTEXT_PIPELINE.md。

## 项目级全文批次与断点恢复（2026-11-19）
对于上百篇需要 PDF 解析的研究，优先使用唯一的 FulltextPipeline 与 FullTextBatchRunner，避免建立第二套版权审批或原文索引。先经可信工作流完成当前 case_id 的外发审批，为 manifest.items 每篇提供稳定 doc_id、真实 rights_actor/rights_reference、已审查的 allowed_hosts、parse；审批人字符串仅作审计，不能替代外部身份验证。
仅由授权本地 CLI 运行 literature fulltext-batch，要求 --workflow-case-id、--workspace-db、--rights-approved、--allow-download、--allow-search-exposure，严格限定 max_documents/max_seconds/max_total_bytes/max_attempts 和离线 Docling 资源。相同清单生成确定性 FTB 批次号，单项目 SQLite 保存每篇完成/失败/重试检查点。超限、付费墙、许可不明、非 PDF 或下载失败必须隔离；达到重试上限需重新授权后 --refresh。
使用 fulltext-batch-status 或只读 MCP patent_literature_fulltext_batch_status 查询进度，不触发网络或下载。任何机器解析结果仍为未审核证据，全文技术结论必须校验原始 PDF、页码及 SHA256。结构和故障恢复详见 docs/FULLTEXT_PIPELINE.md。
