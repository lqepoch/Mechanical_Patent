"""文献知识库 CLI：项目隔离、官方分页检索、离线批量导入和研究记忆恢复。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .core import Evidence, PatentWorkflowError
from .literature_memory import LiteratureMemoryStore


def add_literature_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("literature", help="项目级专利/论文长期记忆与千篇文献检索")
    parser.add_argument("--project-dir", required=True, type=Path,
                        help="单个研发项目的根目录；目录内部独立 SQLite 与 MD")
    subs = parser.add_subparsers(dest="literature_command", required=True)

    search = subs.add_parser("search", help="快速检索已保存的专利/论文/研究批注")
    search.add_argument("--query", required=True)
    search.add_argument("--kind", choices=["patent", "paper"])
    search.add_argument("--limit", type=int, default=20)

    read = subs.add_parser("read", help="按稳定证据编号读取整篇 Markdown 记忆")
    read.add_argument("--doc-id", required=True)

    subs.add_parser("stats", help="显示知识库规模及研究进度")
    pending = subs.add_parser("pending", help="列出未完成分析的文献队列")
    pending.add_argument("--limit", type=int, default=30)
    subs.add_parser("resume-read", help="读取项目研究恢复快照及SHA256")
    resume = subs.add_parser("resume-save", help="带并发保护地更新项目研究恢复快照")
    resume.add_argument("--input", required=True, type=Path)
    resume.add_argument("--expected-sha256", required=True)
    resume.add_argument("--analyst", required=True)

    imp = subs.add_parser("import", help="离线导入经过来源标识的专利/论文元数据")
    imp.add_argument("--input", required=True, type=Path)

    note = subs.add_parser("note", help="以 JSON 文件追加入库已检查过的研究分析")
    note.add_argument("--doc-id", required=True)
    note.add_argument("--analysis-file", required=True, type=Path)
    note.add_argument("--analyst", required=True)
    note.add_argument("--basis", required=True, choices=[
        "metadata", "abstract", "claims", "full_text",
    ])
    note.add_argument("--source-position", action="append", default=[])

    harvest = subs.add_parser("harvest", help="保密授权后按源分页检索并持续写入记忆")
    harvest.add_argument("--provider", action="append", required=True,
                         choices=["openalex", "crossref", "epo-ops"])
    harvest.add_argument("--query", action="append", required=True)
    harvest.add_argument("--workflow-case-id", required=True)
    harvest.add_argument("--workspace-db", required=True, type=Path)
    harvest.add_argument("--allow-search-exposure", action="store_true")
    harvest.add_argument("--max-documents", type=int, default=1000)
    harvest.add_argument("--page-size", type=int, default=100)
    harvest.add_argument("--max-pages", type=int, default=30)
    harvest.add_argument("--max-seconds", type=int, default=600)
    harvest.add_argument("--refresh", action="store_true")

    rights = subs.add_parser("fulltext-plan", help="经案卷权限与开放许可证审核登记 PDF 任务")
    rights.add_argument("--doc-id", required=True)
    rights.add_argument("--workflow-case-id", required=True)
    rights.add_argument("--workspace-db", required=True, type=Path)
    rights.add_argument("--rights-actor", required=True)
    rights.add_argument("--rights-reference", required=True)
    rights.add_argument("--rights-approved", action="store_true")

    download = subs.add_parser("fulltext-process", help="执行一次安全 PDF 获取及离线 Docling 解析")
    download.add_argument("--doc-id", required=True)
    download.add_argument("--workflow-case-id", required=True)
    download.add_argument("--workspace-db", required=True, type=Path)
    download.add_argument("--allow-download", action="store_true")
    download.add_argument("--allow-host", action="append", default=[], help="PDF 原始站点的精确域名白名单")
    download.add_argument("--max-bytes", type=int, default=40 * 1024 * 1024)
    download.add_argument("--docling-artifacts", type=Path,
                          help="经许可、事先下载好的离线 Docling 模型目录")
    download.add_argument("--download-only", action="store_true")

    status = subs.add_parser("fulltext-status", help="按文献编号查看原文获取/解析状态")
    status.add_argument("--doc-id", required=True)
    passages = subs.add_parser("fulltext-search", help="从已解析 PDF 中检索页码级技术证据")
    passages.add_argument("--query", required=True)
    passages.add_argument("--limit", type=int, default=20)
    pending_files = subs.add_parser("fulltext-pending", help="查看需要重试或继续解析的论文任务")
    pending_files.add_argument("--limit", type=int, default=30)

    batch = subs.add_parser("fulltext-batch", help="逐篇审批的全文批量处理，具备检查点和限额")
    batch.add_argument("--manifest", required=True, type=Path)
    batch.add_argument("--workflow-case-id", required=True)
    batch.add_argument("--workspace-db", required=True, type=Path)
    batch.add_argument("--rights-approved", action="store_true")
    batch.add_argument("--allow-download", action="store_true")
    batch.add_argument("--allow-search-exposure", action="store_true")
    batch.add_argument("--docling-artifacts", type=Path)
    batch.add_argument("--max-documents", type=int, default=100)
    batch.add_argument("--max-seconds", type=int, default=900)
    batch.add_argument("--max-total-bytes", type=int, default=2 * 1024 * 1024 * 1024)
    batch.add_argument("--max-attempts", type=int, default=3)
    batch.add_argument("--refresh", action="store_true")
    batch_status = subs.add_parser("fulltext-batch-status", help="查询项目全文批次检查点")
    batch_status.add_argument("--batch-id", required=True)
    batch_status.add_argument("--limit", type=int, default=100)


def _assert_fulltext_approval(args: argparse.Namespace) -> None:
    """项目目录与案卷外发审批必须同时匹配，防止跨项目权限借用。"""
    root = args.project_dir.expanduser().resolve()
    database = args.workspace_db.expanduser().resolve()
    if root.name != args.workflow_case_id or root.parent.name != "cases":
        raise PatentWorkflowError("全文任务必须限定在指定研发案卷的项目目录。")
    if database != root.parent.parent / "patents.sqlite3":
        raise PatentWorkflowError("全文任务的权限数据库必须与实际项目存储一致。")
    from .local_workspace import LocalPatentWorkspace
    workspace = LocalPatentWorkspace(database)
    if not workspace.can_egress(args.workflow_case_id):
        raise PatentWorkflowError("当前案卷未通过真实出站审批，禁止远程全文获取。")


def handle_literature(args: argparse.Namespace) -> int:
    memory = LiteratureMemoryStore(args.project_dir)
    command = args.literature_command
    if command == "search":
        result = {
            "records": memory.search(args.query, limit=args.limit, kind=args.kind),
            "scope": "single_project",
        }
    elif command == "read":
        result = memory.read(args.doc_id)
    elif command == "stats":
        result = memory.stats()
    elif command == "pending":
        result = {"pending": memory.pending_analysis(limit=args.limit)}
    elif command == "resume-read":
        result = memory.read_resume()
    elif command == "resume-save":
        result = memory.update_resume(
            args.input.read_text(encoding="utf-8"),
            expected_sha256=args.expected_sha256, analyst=args.analyst,
        )
    elif command == "import":
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        rows = payload.get("records", []) if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or len(rows) > 10000:
            raise PatentWorkflowError("每次仅允许导入不超过10000条结构化文献。")
        documents = [Evidence.from_dict(item, imported=True) for item in rows]
        result = {"ingested": memory.ingest_many(documents), "stats": memory.stats()}
    elif command == "note":
        payload = json.loads(args.analysis_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise PatentWorkflowError("分析文件应为 JSON 对象。")
        result = memory.write_analysis(
            args.doc_id, analyst=args.analyst, basis=args.basis,
            analysis=payload, source_positions=args.source_position,
        )
    elif command in {"fulltext-plan", "fulltext-process", "fulltext-status",
                     "fulltext-search", "fulltext-pending",
                     "fulltext-batch", "fulltext-batch-status"}:
        from .literature_fulltext import FulltextPipeline
        pipeline = FulltextPipeline(memory)
        if command == "fulltext-status":
            result = pipeline.status(args.doc_id)
        elif command == "fulltext-search":
            result = {"records": pipeline.search(args.query, limit=args.limit),
                      "review_status": "awaiting_original_pdf_review"}
        elif command == "fulltext-pending":
            result = {"jobs": pipeline.pending(limit=args.limit)}
        elif command == "fulltext-batch-status":
            from .literature_fulltext_batch import FullTextBatchRunner
            result = FullTextBatchRunner(pipeline).status(args.batch_id, limit=args.limit)
        elif command == "fulltext-batch":
            from .literature_fulltext_batch import FullTextBatchRunner
            _assert_fulltext_approval(args)
            if not (args.rights_approved and args.allow_download and args.allow_search_exposure):
                raise PatentWorkflowError("全文批次缺少明确的版权许可与外发执行批准。")
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            result = FullTextBatchRunner(pipeline).run(
                manifest, authorized=True, outbound_approved=True,
                artifacts=args.docling_artifacts, max_documents=args.max_documents,
                max_seconds=args.max_seconds, max_total_bytes=args.max_total_bytes,
                max_attempts=args.max_attempts, refresh=args.refresh,
            )
        else:
            _assert_fulltext_approval(args)
            if command == "fulltext-plan":
                result = pipeline.queue(
                    args.doc_id, rights_actor=args.rights_actor,
                    rights_reference=args.rights_reference, authorized=args.rights_approved,
                )
            else:
                result = pipeline.process(
                    args.doc_id, allowed_hosts=set(args.allow_host),
                    authorized=args.allow_download, artifacts=args.docling_artifacts,
                    max_bytes=args.max_bytes, parse=not args.download_only,
                )
    elif command == "harvest":
        if not args.allow_search_exposure:
            raise PatentWorkflowError("联网批量检索须明确允许外发检索词。")
        if len(args.query) > 8 or len(args.provider) > 3:
            raise PatentWorkflowError("单次最多8条查询词和3个数据源。")
        if args.project_dir.name != args.workflow_case_id:
            raise PatentWorkflowError("项目目录名称必须与工作流案卷编号一致。")
        from .local_workspace import LocalPatentWorkspace
        workspace = LocalPatentWorkspace(args.workspace_db)
        if not workspace.can_egress(args.workflow_case_id):
            raise PatentWorkflowError("工作流未批准当前案卷外部查询。")
        from .papers import CrossrefProvider, OpenAlexProvider
        from .providers import EPOOPSProvider
        from .literature_harvest import HarvestBudget, LiteratureHarvester
        budgets = HarvestBudget(
            max_documents=args.max_documents, page_size=args.page_size,
            max_pages=args.max_pages, max_seconds=args.max_seconds,
        )
        types = {
            "openalex": OpenAlexProvider, "crossref": CrossrefProvider,
            "epo-ops": EPOOPSProvider,
        }
        harvester = LiteratureHarvester(memory)
        jobs = []
        for source in dict.fromkeys(args.provider):
            provider = types[source]()
            for query in dict.fromkeys(args.query):
                jobs.append(harvester.harvest(
                    provider, query, budget=budgets, refresh=args.refresh,
                ))
        result = {"jobs": jobs, "stats": memory.stats(), "complete_global_search": False}
    else:
        raise PatentWorkflowError("未知文献操作。")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if command == "harvest" and any(x["status"] == "failed" for x in result["jobs"]):
        return 2
    if command == "fulltext-batch" and result["status"] != "complete":
        return 2
    return 0
