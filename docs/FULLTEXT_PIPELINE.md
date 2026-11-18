# 论文 PDF 全文证据流水线（2026-11-19）

## 已实现范围

已有多平台论文适配器负责 OpenAlex、Crossref、Semantic Scholar、arXiv 等的元数据、DOI、作者和 PDF 候选发现。科研长期记忆的 canonical 数据源为每项目独立的 LiteratureMemoryStore，分别保存稳定 Markdown、SQLite 著录/FTS5、AI 和研究者批注。本次新增 LiteratureFullText，将获准的论文 PDF 原文与项目级证据索引直接关联。

1. 在项目中取得论文 DOI、文献标识和候选 pdf_url。
2. 合规审核人员核实网站条款、出版许可和项目安全策略，记录 rights_basis、rights_reference，外部网络访问另有工作流出站审批。
3. 本地已有 PDF 使用 fulltext-import，网络来源只能使用该论文已登记的候选 PDF URL 且必须显式配置域名白名单。
4. 经 SHA256 内容寻址存储至每项目的 knowledge/fulltext/pdfs；单文件限制 40 MiB。
5. 离线 Docling 从本地 PDF 提取段落、页码、label 和 bbox，并记录原始 PDF 哈希。
6. 单项目 SQLite 中 fulltext_documents/fulltext_blocks/fulltext_fts 提供状态、源许可、页码级段落检索。所有解析结果默认标记 parsed_unreviewed（未核验原始 PDF）。
7. 重复获取同哈希文档保持幂等；论文新版本 PDF 替换旧哈希时旧全文块索引失效，而人工研究笔记依然保留。

## CLI 命令

项目内查找单篇论文的证据编号：

    python -m mechanical_patent literature --project-dir /secure/CASE_ID search --query cavitation --kind paper

如果已经合法持有原始 PDF：

    python -m mechanical_patent literature --project-dir /secure/CASE_ID fulltext-import \
      --doc-id EV-123456789ABC --input /approved/papers/source.pdf \
      --rights-basis cc-by --rights-reference https://creativecommons.org/licenses/by/4.0/ --authorized

如元数据中有合法可归档的 PDF URL，完成远程审批后：

    python -m mechanical_patent literature --project-dir /secure/CASE_ID fulltext-fetch \
      --doc-id EV-123456789ABC \
      --rights-basis written-permission --rights-reference INTERNAL-COPY-AUTH-001 \
      --allowed-host repository.example.edu \
      --workflow-case-id CASE_ID --workspace-db /secure/project/index.sqlite3 \
      --allow-search-exposure --authorized

已经在本地准备经许可的 Docling 模型资源后：

    python -m mechanical_patent literature --project-dir /secure/CASE_ID fulltext-parse \
      --doc-id EV-123456789ABC --docling-artifacts /approved/models/docling \
      --max-pages 200 --authorized

状态与原文段落检索：

    python -m mechanical_patent literature --project-dir /secure/CASE_ID fulltext-status --doc-id EV-123456789ABC
    python -m mechanical_patent literature --project-dir /secure/CASE_ID fulltext-search --query "NPSH" --limit 20
    python -m mechanical_patent literature --project-dir /secure/CASE_ID fulltext-page --doc-id EV-123456789ABC --page 3

MCP 只读工具：patent_literature_fulltext_status / patent_literature_fulltext_search / patent_literature_fulltext_page。获取、导入与解析只能由有权限的宿主本地 CLI 操作，不开放任意路径读取或无授权数据下载的 MCP 方法。

## 版本化证据和故障恢复

- fulltext_documents 保存 doc_id、pdf_sha256、pdf_relpath、source_url、rights_basis、rights_reference、state、parser_version、parsed_relpath、block_count、page_count、last_error、更新时间。
- fulltext_blocks 保存文献编号、原文件 SHA、block、page、label、正文及可用坐标。FTS5/trigram 不可用时使用有界 LIKE 查询。
- 重新分析既有 PDF 可以重建段落索引。原始 PDF 只读按哈希存储；在解析失败时保留原文、人工批注及重试能力。
- remote fetch 复用既有 pdf_archive.download_pdf：TLS 主机名核验、公网 DNS 地址固定连接、不跟随跳转、明确来源域名白名单、文件大小和 PDF magic 校验。还应由生产网络策略、病毒扫描、供应商许可管理补强。
- 开放网页可阅读/付费数据库可检索均不等于允许复制/归档/二次分发，必须核实许可证及机构合同；不能规避付费墙、登录或禁止自动化条款。
- full_text_verified 默认 false，直到获授权人员逐页复核原始 PDF。解析出的公式和实验结论也需专业人工审核。
- Docker 部署时应把项目 knowledge 目录和 SQLite 放在挂载卷，进行定期备份及恢复演练，不将版权资料放入 GHCR 镜像。

## 下一步

面向千篇及以上论文的任务队列、分布式限流、费用预测、自动批量 PDF 合规判断及 GROBID TEI 解析为后续阶段；来源支持、配额与商业许可均需实际账号联调，不能因存在适配器就宣称全部具备生产服务 SLA。

## 官方技术依据

- https://help.openalex.org/access/fulltext/
- https://help.openalex.org/data/works/attributes/
- https://unpaywall.org/api
- https://docling-project.github.io/docling/reference/document_converter/
- https://grobid.readthedocs.io/en/latest/Coordinates-in-PDF/

## 批次执行、断点恢复和预算（2026-11-19）

获准论文清单 JSON 格式（每篇独立许可条件）：

    {
      "items": [
        {
          "doc_id": "EV-123456789ABC",
          "source": "local",
          "input": "/approved/papers/article.pdf",
          "rights_basis": "cc-by",
          "rights_reference": "https://creativecommons.org/licenses/by/4.0/",
          "parse": true
        }
      ]
    }

执行与恢复：

    python -m mechanical_patent literature --project-dir /secure/CASE_ID fulltext-batch       --manifest /approved/manifest.json --authorized       --docling-artifacts /approved/models/docling --max-documents 100       --max-total-bytes 2147483648 --max-seconds 900 --max-attempts 3

输出批次 FTB-编号。后续可再次运行相同清单以自动跳过已完成文献，重试失败条目；达到失败次数上限需经审核后使用 --refresh。批次状态通过 fulltext-batch-status --batch-id FTB-... 查询，MCP 亦提供 patent_literature_fulltext_batch_status。

联网单篇须使用 source=remote 与 allowed_hosts:[域名]，且 CLI 需要 --allow-search-exposure、--workflow-case-id 和 --workspace-db；同一批次内有远程记录时必须审批当前案卷，审批后才进入原 PDF 下载器。

批处理记录只包含 manifest SHA256、文献编号、完成状态、尝试次数、原 PDF 哈希、错误摘要和更新时间；不得上传包含内部审批或原文路径的清单。当前单个 CLI 进程负责执行，支持可恢复检查点，跨节点多 worker 的分布式租约与背压仍待后续正式运行环境实现。
