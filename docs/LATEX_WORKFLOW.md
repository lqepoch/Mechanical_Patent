# LaTeX 研究论文主源：AI 分章节写作、引用、修订和导出

论文初稿保存在当前项目的 cases/<case_id>/manuscripts/<paper_id>/，拥有 main.tex、sections/*.tex、references.bib、versions/ 与 exports/。每一章节的修改保留原始源文件、内容哈希、SQLite manuscript_versions 历史。

开源方案：
- Pandoc https://pandoc.org/MANUAL.html：LaTeX→DOCX、HTML、Markdown，支持 BibTeX 与 citeproc。
- Tectonic https://github.com/tectonic-typesetting/tectonic：XeTeX 系排版与 PDF 编译。
- LaTeX Workshop https://github.com/James-Yu/LaTeX-Workshop：VS Code 原生 LaTeX 编辑支持。
- latexmk https://ctan.org/pkg/latexmk：传统 TeX Live 构建路径。

MCP 工具：
- patent_manuscript_create：创建项目内论文与章节。
- patent_manuscript_read、patent_manuscript_edit：只读取或修改登记章节/参考文献。
- patent_manuscript_revisions：查看实际版本、哈希。
- patent_manuscript_export：使用 Pandoc 实际输出 DOCX、HTML、Markdown。

论文最小章节：摘要、引言、现有技术、技术方案、工程理论、结果讨论、适用边界、结论。引文依据真实 DOI、公开号与法律公开日期，仿真和实验数据未经运行均应明确注明待验证。正文由当前 Codex/ChatGPT 直接生成，无需额外模型服务。

安全：TeX 可能有读写文件和扩展执行能力。公网 MCP 进程禁止原始 TeX/PDF 编译；Tectonic --untrusted 不能单独实现文件系统隔离。真正 PDF 编译需在无网、低权限、无企业秘密挂载的隔离容器中执行，TeX 包和字体可事先缓存；对不可信宏做准入检查。

LaTeX 作为研发论文与计算论证的主源；递交中国发明专利时须通过中文专利撰写及附图技能生成国家局规范的申请文件，不能把泛用 Pandoc Word 当作法定文件验收。

安全参考：https://github.com/advisories/GHSA-x3q2-h9hx-4r4j
