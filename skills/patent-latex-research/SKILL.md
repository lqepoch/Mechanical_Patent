---
name: patent-latex-research
description: "让 AI 使用 LaTeX 分章节撰写机械专利研发论文、技术理论计算和前沿论证，以 BibTeX 保存真实引用，保留历史修订并用 Pandoc 导出。"
user-invocable: true
---

# LaTeX 论文写作技能

1. 阅读 docs/LATEX_WORKFLOW.md。研究论文或技术论证初稿一律保留 LaTeX 主源。
2. 通过 patent_manuscript_create 创建同一项目的 main.tex、sections 和 references.bib。
3. patent_manuscript_read 读取目标章节；patent_manuscript_edit 修改并写入版本数据库，保留旧版本。
4. 文献引用须有真实 DOI/原文或公开号；公式写明定义、单位和工况，实验数据必须有真实来源。
5. BibTeX 引文与项目专利索引分别保存真实来源、阅读/核验状态。
6. 使用 patent_manuscript_export 导出 DOCX、HTML、Markdown；PDF 使用独立离线低权限 TeX 沙箱，公网 MCP 服务拒绝直接 TeX 编译。
7. 正式中国专利申请必须转交专利撰写与专利附图技能核查法定书式及权要支持。

产出：可追溯 LaTeX 源稿、参考文献、历史编辑记录和实际导出的格式文件。
