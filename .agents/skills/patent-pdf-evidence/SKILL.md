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


## PDF 授权取证与长文档解析（2026-11-19）

1. 为每篇论文核对 DOI 和来源所标注的 OA/许可；pdf_url 仅是候选，不允许凭一个链接直接认定可合法归档。
2. 在项目私有环境执行 `literature pdf-fetch`，提供 case_id、workflow DB、已批准域名、合法版权依据和明确授权；下载使用 DNS 钉扎 HTTPS、SHA256 和 PDF 格式/大小校验，失败保存故障而不触碰既有分析。
3. 配置经许可的本地 Docling artifacts，执行 `literature pdf-parse`；获得 JSON 页码/段落并自动更新单篇 Markdown 的机器区。全部输出保持 parsed_unverified。
4. 通过 `patent_paper_pdf_status`、`patent_paper_pdf_page` 或 CLI pdf-pages 定位原文，再按页写入机理、工况、公式、证伪实验及与专利权利要求的差异；每段结论携带实际页码和文件 SHA256。
5. 对于重新获取或换版本的 PDF，校验 SHA256；技术人员复核后再进入证据/发明审核阶段。文件不明、许可证无效、模型缺失、来源重定向或文件损坏时明确阻断。

具体接口见 docs/PAPER_FULLTEXT.md。网页链接或自动结构化转换均不能代替人工核验原始公开 PDF。
