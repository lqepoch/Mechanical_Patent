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
