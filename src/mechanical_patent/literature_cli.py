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
