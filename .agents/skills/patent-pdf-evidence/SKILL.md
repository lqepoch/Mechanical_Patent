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


## 可核查全文证据链（2026-11-19）

用户研究中若已获取授权的 PDF，先读取 docs/FULLTEXT_EVIDENCE.md。只有实际落在当前案卷 knowledge/inbox 下的 PDF/Docling JSON 才能被引入原文全文索引。绑定时系统验证两个文件和 PDF 实际 SHA256 相等，保存每个段落的页码、block、段落内容 SHA256 和来源 PDF SHA256；版本更新单独归档，并标注需要重新核查旧引用。

MCP 调用 patent_literature_fulltext_ingest(case_id,doc_id,pdf_filename,parsed_filename,authorized=true) 后，用 patent_literature_passages 查询真实原文段落，使用 patent_literature_quote 按 p2:b7 精确比对短引。AI 只有在 source_positions 对应目前解析版本真实存在时，才可使用 patent_literature_note 的 full_text 等级；该等级代表 AI 基于已解析全文开展分析，仍未获得人类原始 PDF 核验。遇扫描 PDF 无文本、跨页表格失真、无页码或来源哈希变化，标记未核实并转人工/实体原文核查。