---
name: patent-pdf-evidence
description: "优先打开真实公开专利 PDF 在线原文进行核查；当具备明确授权及本地副本时，可选使用 Docling 提取论文/专利 PDF 的章节、段落、页码和坐标，保留 SHA-256 与人工核验待办。"
user-invocable: true
---

# 专利与论文原始 PDF 证据定位技能

## 使用边界

用户希望检索结果保存在本地索引，具体技术原文通过真实公开 PDF 在线查看。PDF 的在线原始链接应始终保留；只有网站许可和资料使用授权允许时才额外下载本地 PDF。

## 工作流程

1. 从合法专利/论文数据源获得真实公布号或 DOI、原始文献 URL、可核验的公开 PDF 地址。
2. 按项目本地索引保存公开日期、来源、原始链接、可获取全文状态、检索条件和核验状态。
3. 阅读原文时优先联网打开 PDF，校核结构/附图、权利要求与论文方法，人工证据保留页码、段落和原句，不用摘要代替全文。
4. 符合资料授权时，本地归档可使用 workspace archive，保存 SHA-256 和真实来源 URL。
5. 对许可归档且已准备离线解析模型资源的本地 PDF，可以使用 Docling 进行结构化解析。Docling 不替代人类核对原文，也不自动外发或下载模型资源。
6. 建立 page/block/原文出处，不得引用模型补全的不存在段落、公式或数据表。

## 本地命令

先执行：python -m pip install -e '.[pdf]'，准备经过许可审查的本地模型资源目录。

    python -m mechanical_patent parse-pdf --input patent_library/原始专利.pdf --output cases/原始证据页码.json --source-url https://真实公开PDF地址 --docling-artifacts 本地模型目录 --authorized

## 输出

PDF 文件哈希、原始在线链接、解析器版本、页码、原文段落、可得文字坐标和待核对状态。若 PDF 加密、无可读文本、使用权限不足、模型依赖缺失或解析失败，立即标记为人工核对；不得把空白文字当成不存在技术。

## 论文 PDF 的授权采集与全文证据索引（2026-11-19）

1. 检索只发现 DOI/摘要/PDF 候选，AI 必须记录来源、版权条件和是否已读原文。未经真实批准的 PDF 既不可下载，也不可将全文推断记作已核验。
2. 调用 literature fulltext-import 或 fulltext-fetch：仅在合法许可、资料使用授权和必要网络外发审批通过后执行；下载还要求明确的站点白名单。源 PDF 按 SHA256 内容寻址保存在单项目隔离目录。
3. 模型资源在本地预置且批准后，执行 literature fulltext-parse 使用离线 Docling 提取页码、label、bbox 和原文块；解析后 status=parsed_unreviewed。原始文件哈希用于避免 AI 伪造、错用旧版本原文。
4. 调用 literature fulltext-search / fulltext-page，或 MCP patent_literature_fulltext_search / patent_literature_fulltext_page 按 DOI 证据编号检索精准段落；再由研究者打开原始 PDF 完成文字、公式、图表和工况核对。
5. 长上下文中，正式持久记忆仍存入 LiteratureMemoryStore 的每篇 Markdown、统一数据库和研究恢复文件；多次检索和重分析保留人工批注；不得把摘要/解析文本视为已证明的创造性、法律结论或仿真值。
6. 若 PDF 不可达、付费访问、无授权许可证、Docling 依赖缺失或页码匹配失败，保留原始元数据和错误信息并返回给工作流；不得跳过审批或覆盖上一轮已完成的研究证据。

结构、CLI、MCP、许可门禁与恢复机制参见 docs/FULLTEXT_PIPELINE.md。
