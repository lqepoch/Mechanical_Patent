# 论文 PDF 合法归档、Docling 页码证据和研究记忆

更新：2026-11-19。适用于 Mechanical_Patent 每项目独立 SQLite/MD 工作空间。

## 两段式安全处理

论文数据源返回 DOI、摘要、OA 信息及 PDF 候选链接。候选地址仅供核查；实际版权、许可证和长期归档权利另行审批。

阶段 A：项目工作流保密外发批准 + 具体操作授权 + 合法使用依据 rights_basis/rights_reference + HTTPS 域名白名单。复用现有 pdf_archive.download_pdf，安全下载并计算 SHA256，状态 downloaded。

阶段 B：在本地预置并获准使用的 Docling 模型目录内离线解析 PDF。验证原始 SHA256，抽取页码、段落和边框，存储逐页 JSON，状态 parsed_unverified。

标准 SQLite 文献库新增 pdf_url、paper_metadata_json 两个可追溯字段，兼容既有数据；跨平台的同一 DOI 保存多来源信息。独立 paper_fulltext 表登记法律依据、处理阶段、PDF 哈希、字节数、来源和解析路径、失败原因。每篇 Markdown 有独立机器解析区，历史研究人员批注保留。

## CLI 使用方法

在本机受控项目内操作，先通过原有 LocalPatentWorkspace 获得案卷当前轮的保密外发许可。下面使用 EV-XXXXXXXXXXXX 表示实际存在的文献编号。

查询 PDF 来源：

    python -m mechanical_patent literature --project-dir /private/cases/CASE-001 pdf-status --doc-id EV-XXXXXXXXXXXX

明确批准下载，填写合法版权依据和来源域名：

    python -m mechanical_patent literature \
      --project-dir /private/cases/CASE-001 pdf-fetch \
      --doc-id EV-XXXXXXXXXXXX \
      --allowed-host repository.example.org \
      --rights-basis open_license \
      --rights-reference "实际已核验的许可证据和位置" \
      --workflow-case-id CASE-001 --workspace-db /private/index.sqlite3 \
      --allow-search-exposure --authorized

本地离线结构化解析（需要事先准备模型文件）：

    python -m mechanical_patent literature \
      --project-dir /private/cases/CASE-001 pdf-parse \
      --doc-id EV-XXXXXXXXXXXX \
      --docling-artifacts /private/models/docling --authorized

读取页码证据：

    python -m mechanical_patent literature \
      --project-dir /private/cases/CASE-001 pdf-pages \
      --doc-id EV-XXXXXXXXXXXX --page 2 --limit 25

授权类型仅为 open_license、public_domain、rightsholder_permission，必须留可查证的 rights_reference。填写文字不能代替实际法律许可。

## 独立安全门禁

- 原始 URL 必须来自已入库的论文来源元数据，下载域名必须人工白名单批准。
- 使用已存在的公网 DNS 校验、IP 钉扎、SNI TLS 验证、不跟随重定向、PDF 头及大小限制。
- PDF 存于 knowledge/pdf_objects/<SHA256>.pdf，Docling 解析 JSON 存于 knowledge/pdf_extracted。
- 解析配置严格离线，默认禁用 OCR。无已授权本地模型目录则明确失败，原始 PDF 不会被删除。
- 项目存储互相隔离。跨项目任意路径读取、符号链接覆盖、文件哈希不匹配均阻断。
- PDF 权利、网站条款、模型权重许可证、企业保密要求需独立审查。

## MCP 只读工具

patent_paper_pdf_status(case_id, doc_id)：查询该项目的 PDF 和机器处理状态，不发起网络。

patent_paper_pdf_page(case_id, doc_id, page, limit)：查询逐页文本和 SHA256 来源，状态始终为 awaiting_original_pdf_review。

下载和 PDF 解析由本机受控 CLI 执行，避免缺少强身份校验的公共 MCP 直接发起具有版权及网络风险的操作。后续接入经认证的队列 worker 时保留相同服务层和合同。

## 状态和失败恢复

not_downloaded -> downloading -> downloaded -> parsing -> parsed_unverified。
异常会写入 download_failed 或 parse_failed；内容损坏会停止处理，已有 PDF 保留，修复后可继续。同一 PDF 哈希在重复调用时幂等处理，不因断线丢失已经取得的证据。

parsed_unverified 表示机器识别并建索引。论文实际实验数据、公式、结构机理仍须人工打开原始 PDF 核对，之后使用已有 patent_literature_note 标注页码和分析依据。自动处理不会把原文标为已通过专业核验。

当前仍属于单项目受控任务能力。真正多实例企业部署还需共享配额限速、队列、SLA、权限网关、备份恢复演练和长期版权保留策略。

## 官方参考（2026-11-19）

- Docling：https://docling-project.github.io/docling/reference/document_converter/
- Docling MIT 代码许可：https://github.com/docling-project/docling
- OpenAlex：https://help.openalex.org/api/paging/
- Unpaywall DOI API：https://unpaywall.org/api
- Semantic Scholar：https://api.semanticscholar.org/api-docs
