# 全文证据链：Docling PDF → 页码段落 → SQLite → 引用验证

更新日期：2026-11-19。实现：src/mechanical_patent/literature_evidence.py。

本功能连接原有专利/论文 Markdown 记忆与每案卷 SQLite；只有已获合法许可、已实际持有的本地 PDF 才能导入。服务自身禁止自动抓取网页、绕开付费墙或下载 Docling 模型权重。

## 目录与数据模型

    private_patent_workspace/projects/{project_id}/patents.sqlite3
    private_patent_workspace/projects/{project_id}/cases/{case_id}/knowledge/
      literature.sqlite3
      documents/patents/EV-*.md
      documents/papers/EV-*.md
      inbox/document.pdf
      inbox/document.json
      fulltext/EV-.../source-{pdf_sha256}.pdf
      fulltext/EV-.../docling-{parsed_sha256}.json

解析 JSON 使用现有 parse_local_pdf 生成的契约：parser=docling、parser_version、source_pdf_sha256、source_url、review_status=awaiting_original_pdf_review、blocks 数组。每个 block 必须有唯一正整数序号、可选正整数页码、实际提取文本及可选 bbox。

SQLite fulltext_sources 记录当前 PDF/解析版本的哈希、来源和核验等级，fulltext_blocks 保存可索引段落，fulltext_revisions 保存各版本归档位置。可用时创建 FTS5 trigram 全文索引；短词和不含 FTS5 的环境回退受控 LIKE。

## CLI 执行示例

先在对应案卷文献库登记 DOI/公开号，再将经过权限/版权审批的 PDF 与 Docling 解析 JSON 放在该案卷 knowledge/inbox 下。

    python -m mechanical_patent literature --project-dir private_patent_workspace/projects/PM80/cases/C01 ingest-pdf --doc-id EV-123456789ABC --pdf private_patent_workspace/projects/PM80/cases/C01/knowledge/inbox/source.pdf --parsed-json private_patent_workspace/projects/PM80/cases/C01/knowledge/inbox/source.json --authorized

也可以省略 --parsed-json，改用 --docling-artifacts 指定已安装的离线 Docling 模型目录，程序先调用现有 parse_local_pdf 解析，然后核验并入库。

    python -m mechanical_patent literature --project-dir private_patent_workspace/projects/PM80/cases/C01 passages --query "排气支路" --limit 20

    python -m mechanical_patent literature --project-dir private_patent_workspace/projects/PM80/cases/C01 quote --doc-id EV-123456789ABC --anchor p2:b7 --verbatim "原文短引"

    python -m mechanical_patent literature --project-dir private_patent_workspace/projects/PM80/cases/C01 fulltext-status --doc-id EV-123456789ABC

上述 EV 编号只是格式示例，实际以已有案卷返回的证据编号为准。

## MCP 契约

- patent_literature_fulltext_ingest：限定当前案卷 knowledge/inbox 下无路径分隔符的 PDF/JSON 文件名，必须 authorized=true。
- patent_literature_passages：查出每篇文献的段落、页码、p{page}:b{block} 锚点、PDF SHA256、段落哈希及来源 URL。
- patent_literature_quote：逐字核对短引在当前解析块中是否存在，仅返回 parsed_text_match_only 层级。
- patent_literature_fulltext_status：显示已有 PDF 解析版本、哈希与待人工核验状态。
- patent_literature_search：在原元数据/Markdown 搜索结果之外补 matched_passages。
- patent_literature_note 以 basis=full_text 提交时，source_positions 必须为当前解析中确有的 p2:b7 等页码:段落定位；无具体原文需降级 basis=metadata、abstract 或 claims。

## 关键安全约束

1. 解析 JSON 的 source_pdf_sha256 必须等于打开的源 PDF 的实际 SHA256，原始文件和解析 JSON 都必须位于当前案卷路径。
2. 禁止跨项目路径、目录穿越、符号链接、超额 PDF/JSON、无效或重复 block、无效页码、无穷坐标。
3. 只有已有 EV- 文献才可绑定原文；原始 PDF 和解析版本用文件内容哈希归档。更新源 PDF 需要重新核查旧版引用，stale_previous_notes 会提示可能失效的记忆。
4. Docling 机器提取仅用于搜索和定位，不能作为原始公开文本的独立人工核验。论文实验值、专利权要和图纸结构均须回到实际 PDF 核对。
5. 项目私有 SQLite 与原始 PDF 均需备份、加密及恢复演练。MCP 的生产远程调用仍需 OIDC/ABAC、审计和 HTTP 受控网关；CLI 本地文件限制不代替多用户身份授权。

## 正式验收与开源复用

离线自动化 CI：从模拟 PDF / 可替换 Docling 适配器生成 JSON，经 SHA256 绑定、页码全文查询、精确短引、版本归档、跨案卷拒绝与 AI 研究记忆引用门禁。复杂扫描 PDF、表格、坐标及真实科研文献的人工黄金集检验仍属于 Issue #17 的后续验收。Docling 当前已有离线解析入口；GROBID 官方 /api/processFulltextDocument TEI 参考文献识别可以作为下一子模块，需对其源码和模型许可单独核查。PaperQA2 的引用核验方法可以借鉴，但不引入其默认 LLM/embedding 依赖。

参考：
- https://github.com/docling-project/docling
- https://grobid.readthedocs.io/en/latest/Grobid-service/
- https://www.sqlite.org/fts5.html
