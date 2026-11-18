"""文献知识库 CLI：项目隔离、官方分页检索、离线批量导入和研究记忆恢复。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .core import Evidence, PatentWorkflowError
from .literature_memory import LiteratureMemoryStore
from .literature_fulltext import LiteratureFullText, RIGHTS_BASES


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

    local = subs.add_parser("fulltext-import", help="经资料授权导入项目内合法持有的 PDF")
    local.add_argument("--doc-id", required=True)
    local.add_argument("--input", type=Path, required=True)
    local.add_argument("--rights-basis", required=True, choices=sorted(RIGHTS_BASES))
    local.add_argument("--rights-reference", required=True)
    local.add_argument("--source-url", default="")
    local.add_argument("--authorized", action="store_true")

    fetch = subs.add_parser("fulltext-fetch", help="安全获取已发现的公开论文 PDF 候选")
    fetch.add_argument("--doc-id", required=True)
    fetch.add_argument("--rights-basis", required=True, choices=sorted(RIGHTS_BASES))
    fetch.add_argument("--rights-reference", required=True)
    fetch.add_argument("--allowed-host", action="append", required=True)
    fetch.add_argument("--authorized", action="store_true")
    fetch.add_argument("--allow-search-exposure", action="store_true")
    fetch.add_argument("--workflow-case-id", required=True)
    fetch.add_argument("--workspace-db", type=Path, required=True)
    fetch.add_argument("--max-bytes", type=int, default=40 * 1024 * 1024)

    convert = subs.add_parser("fulltext-parse", help="使用离线 Docling 对已归档 PDF 建立页码索引")
    convert.add_argument("--doc-id", required=True)
    convert.add_argument("--docling-artifacts", type=Path, required=True)
    convert.add_argument("--max-pages", type=int, default=200)
    convert.add_argument("--authorized", action="store_true")

    state = subs.add_parser("fulltext-status", help="读取已有论文 PDF/全文解析状态")
    state.add_argument("--doc-id", required=True)
    lookup = subs.add_parser("fulltext-search", help="按项目全文段落索引检索文字与页码")
    lookup.add_argument("--query", required=True)
    lookup.add_argument("--doc-id")
    lookup.add_argument("--limit", type=int, default=20)
    page = subs.add_parser("fulltext-page", help="读取指定 PDF 页面对应的原文段落")
    page.add_argument("--doc-id", required=True)
    page.add_argument("--page", required=True, type=int)
    page.add_argument("--limit", type=int, default=100)


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
    elif command in {
        "fulltext-import", "fulltext-fetch", "fulltext-parse",
        "fulltext-status", "fulltext-search", "fulltext-page",
    }:
        pipeline = LiteratureFullText(memory)
        if command == "fulltext-import":
            result = pipeline.import_local(
                args.doc_id, args.input, authorized=args.authorized,
                rights_basis=args.rights_basis, rights_reference=args.rights_reference,
                source_url=args.source_url,
            )
        elif command == "fulltext-fetch":
            if not args.allow_search_exposure or args.project_dir.name != args.workflow_case_id:
                raise PatentWorkflowError("下载论文必须明确外发授权且项目目录与案卷匹配。")
            from .local_workspace import LocalPatentWorkspace
            workspace = LocalPatentWorkspace(args.workspace_db)
            result = pipeline.fetch(
                args.doc_id, allowed_hosts=set(args.allowed_host),
                authorized=args.authorized, rights_basis=args.rights_basis,
                rights_reference=args.rights_reference,
                outbound_approved=workspace.can_egress(args.workflow_case_id),
                max_bytes=args.max_bytes,
            )
        elif command == "fulltext-parse":
            result = pipeline.parse(
                args.doc_id, authorized=args.authorized,
                artifacts=args.docling_artifacts, max_pages=args.max_pages,
            )
        elif command == "fulltext-status":
            result = pipeline.status(args.doc_id)
        elif command == "fulltext-search":
            result = {"hits": pipeline.search(args.query, doc_id=args.doc_id, limit=args.limit),
                      "review_status": "awaiting_original_pdf_review"}
        else:
            result = pipeline.page(args.doc_id, args.page, limit=args.limit)
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
    return 0 if not (
        command == "harvest" and any(x["status"] == "failed" for x in result["jobs"])
    ) else 2
