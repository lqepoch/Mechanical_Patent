"""Native-agent CLI. Search and validate documents; the current AI writes the patent."""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys
import sqlite3
from uuid import uuid4

from .core import PatentWorkflowError
from .paper_sources import (SEARCH_SOURCES, UnpaywallEnricher, build_paper_providers, paper_source_catalog)
from .providers import EPOOPSProvider, ImportedPatentProvider
from .workflow import PatentResearch, validate_case
from .workspace_cli import add_workspace_parser, handle_workspace


def _add_research_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--direction", required=True, help="User's engineering problem; kept in private dossier")
    command.add_argument("--case-dir", type=Path, help="New output folder; existing folders cannot be overwritten")
    command.add_argument("--workspace-db", type=Path, default=None,
                         help="索引数据库路径；缺省为案卷父目录/index.sqlite3")
    command.add_argument("--workflow-case-id",
                         help="挂载到已有任务队列案卷；联网前强制验证当前轮次的保密审批")
    command.add_argument("--patent-provider", choices=["auto", "epo-ops", "import", "none"], default="auto")
    command.add_argument("--import-json", type=Path, help="Imported records for offline research; always unverified")
    command.add_argument("--paper-provider", action="append", choices=[*SEARCH_SOURCES, "all", "import", "none"],
                         help="可重复；默认 OpenAlex+Crossref+Semantic Scholar；all 包含已授权的商业源")
    command.add_argument("--allow-paid-paper-apis", action="store_true",
                         help="额外批准使用已获合同许可的 CORE/Lens 数据源")
    command.add_argument("--enrich-unpaywall", action="store_true",
                         help="通过 DOI 查找合法开放获取的 PDF 位置")
    command.add_argument("--unpaywall-limit", type=int, default=20,
                         help="Unpaywall 每轮查询上限 0-100")
    command.add_argument("--paper-import-json", type=Path, help="Optional imported unverified scholarly corpus")
    command.add_argument("--patent-query", action="append", default=[], help="Repeat 1-8 times; AI derives safe terms")
    command.add_argument("--paper-query", action="append", default=[], help="Repeat 1-8 times; AI derives safe terms")
    command.add_argument("--limit", type=int, default=10, help="Max results per provider per query (1-25)")
    command.add_argument("--allow-search-exposure", action="store_true",
                         help="Allow specified search terms to leave this machine to authorized APIs")
    command.add_argument("--web-url", action="append", default=[], help="Permitted public HTML page for Crawl4AI")
    command.add_argument("--web-allow-domain", action="append", default=[], help="Explicit Crawl4AI domain allowlist")
    command.add_argument("--allow-web-exposure", action="store_true", help="Allow policy-checked HTML page fetching")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mechanical-patent")
    sub = parser.add_subparsers(dest="command", required=True)
    _add_research_arguments(sub.add_parser("research", help="Acquire patent + paper evidence for the current AI"))
    _add_research_arguments(sub.add_parser("run", help="Alias of 'research'; no LLM API required"))
    validate = sub.add_parser("validate", help="Check AI-written evidence-linked application draft")
    validate.add_argument("--case-dir", required=True, type=Path)
    add_workspace_parser(sub)
    benchmark = sub.add_parser("benchmark", help="按授权标注集评测专利检索排序、同族召回率")
    benchmark.add_argument("--gold", required=True, type=Path)
    benchmark.add_argument("--results", required=True, type=Path)
    benchmark.add_argument("--rights", required=True, type=Path)
    benchmark.add_argument("--output", required=True, type=Path)
    extract = sub.add_parser("parse-pdf", help="本地离线 Docling PDF 解析和页码出处记录")
    extract.add_argument("--input", required=True, type=Path)
    extract.add_argument("--output", required=True, type=Path)
    extract.add_argument("--source-url", default="")
    extract.add_argument("--docling-artifacts", type=Path)
    extract.add_argument("--authorized", action="store_true")
    bridge = sub.add_parser("mcp-import", help="导入有授权的行业专利 MCP 结构化返回，待核实原始文献")
    bridge.add_argument("--input", required=True, type=Path)
    bridge.add_argument("--output", required=True, type=Path)
    citations = sub.add_parser("citations", help="公开 DOI 的 OpenCitations 一跳参考与被引关系，保存进已有研发案卷")
    citations.add_argument("--doi", action="append", required=True, help="种子论文 DOI，可重复最多 8 次")
    citations.add_argument("--case-dir", required=True, type=Path)
    citations.add_argument("--direction", choices=["references", "citations", "both"], default="both")
    citations.add_argument("--max-links", type=int, default=25)
    citations.add_argument("--allow-search-exposure", action="store_true")
    citations.add_argument("--workflow-case-id", help="需要工作流保密批准的现有案卷编号")
    citations.add_argument("--workspace-db", type=Path, help="工作流数据库路径")
    sub.add_parser("paper-sources", help="列出全部论文数据源、平台用途及本机凭证配置")
    args = parser.parse_args(argv)

    try:
        if args.command == "paper-sources":
            import json
            print(json.dumps(paper_source_catalog(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "citations":
            if not args.allow_search_exposure:
                raise PatentWorkflowError("外部 DOI 引证查询需要明确的 --allow-search-exposure 审批。")
            if args.workflow_case_id:
                from .local_workspace import LocalPatentWorkspace
                database = args.workspace_db or (args.case_dir.parent / "index.sqlite3")
                workspace = LocalPatentWorkspace(database)
                intake_path = args.case_dir / "00_intake.json"
                if not intake_path.is_file():
                    raise PatentWorkflowError("找不到对应的研究案卷。")
                import json
                intake = json.loads(intake_path.read_text(encoding="utf-8"))
                if intake.get("case_id") != args.workflow_case_id:
                    raise PatentWorkflowError("研发案卷编号与工作流授权的项目不一致。")
                if not workspace.can_egress(args.workflow_case_id):
                    raise PatentWorkflowError("该研发案卷尚未通过外部检索保密审批。")
            from .case_citations import update_case_citations
            result = update_case_citations(
                args.case_dir, args.doi,
                direction=args.direction, max_links=args.max_links,
            )
            print("学术引证检索状态:", result["status"])
            print("累计引用关系:", result["total_edges"])
            print("发现待进一步验证的 DOI:", result["next_doi_candidates"])
            print("数据质量限制与接口错误数:", len(result["query_errors"]))
            print("申请提交授权: false")
            return 0 if not result["query_errors"] else 2
        if args.command == "mcp-import":
            from .mcp_bridge import import_mcp_json
            result = import_mcp_json(args.input, args.output)
            print("外部专利证据入库条目:", result["records"])
            print("证据核验状态:", result["status"])
            print("来源记录 SHA-256:", result["payload_sha256"])
            return 0
        if args.command == "benchmark":
            from .benchmarks import run_benchmark
            result = run_benchmark(args.gold, args.results, args.rights, args.output)
            print("评测样本数:", result["case_count"])
            print("排序召回指标:", result["metrics"])
            print("评测报告保存至:", args.output)
            return 0
        if args.command == "parse-pdf":
            from .pdf_extraction import parse_local_pdf
            result = parse_local_pdf(
                args.input, args.output, authorized=args.authorized,
                source_url=args.source_url, artifacts=args.docling_artifacts,
            )
            print("PDF 离线解析状态:", result["status"])
            print("页码段落数:", result["blocks"])
            print("SHA-256:", result["sha256"])
            return 0
        if args.command == "workspace":
            return handle_workspace(args)
        if args.command == "validate":
            result = validate_case(args.case_dir)
            print("Quality gate:", result["status"])
            for issue in result["issues"]:
                print("BLOCKER:", issue)
            print("Filing authorized: false")
            return 0 if not result["issues"] else 2

        folder = args.case_dir or Path("cases") / ("case-" + uuid4().hex[:12])
        database = args.workspace_db or (folder.parent / "index.sqlite3")
        from .local_workspace import LocalPatentWorkspace
        workspace = LocalPatentWorkspace(database)
        remote_requested = bool(
            args.patent_provider == "epo-ops"
            or (args.patent_provider == "auto" and os.getenv("EPO_OPS_CLIENT_ID") and os.getenv("EPO_OPS_CLIENT_SECRET"))
            or any(x not in {"import", "none"} for x in (args.paper_provider or []))
            or (args.paper_provider is None and bool(args.paper_query))
            or args.enrich_unpaywall
        )
        if remote_requested and not args.allow_search_exposure:
            raise PatentWorkflowError("Remote search requires --allow-search-exposure after secrecy review.")
        if args.workflow_case_id and (remote_requested or args.web_url):
            if not workspace.can_egress(args.workflow_case_id):
                raise PatentWorkflowError(
                    "当前案卷未通过本轮保密审批，无法调用外部专利、论文或网页数据源。"
                )
        if args.patent_provider == "import":
            if not args.import_json:
                raise PatentWorkflowError("--import-json required when selecting import patent provider")
            patent_provider = ImportedPatentProvider(args.import_json)
        elif args.patent_provider == "epo-ops":
            patent_provider = EPOOPSProvider()
        elif args.patent_provider == "auto" and args.allow_search_exposure and os.getenv("EPO_OPS_CLIENT_ID") and os.getenv("EPO_OPS_CLIENT_SECRET"):
            patent_provider = EPOOPSProvider()
        else:
            patent_provider = None

        paper_modes = args.paper_provider
        if paper_modes is None:
            paper_modes = ["openalex", "crossref", "semantic-scholar"] if args.allow_search_exposure else []
        if any(x not in {"import", "none"} for x in paper_modes) and not args.allow_search_exposure:
            raise PatentWorkflowError("Paper API queries require --allow-search-exposure.")
        remote_paper_modes = [x for x in paper_modes if x not in {"import", "none"}]
        paper_providers, paper_warnings = (
            build_paper_providers(remote_paper_modes, allow_paid=args.allow_paid_paper_apis)
            if remote_paper_modes else ([], [])
        )
        if "import" in paper_modes:
            file = args.paper_import_json or args.import_json
            if not file:
                raise PatentWorkflowError("--paper-import-json required for imported papers")
            paper_providers.append(ImportedPatentProvider(file))
        if not 0 <= args.unpaywall_limit <= 100:
            raise PatentWorkflowError("--unpaywall-limit 须在 0-100 之间。")
        enricher = UnpaywallEnricher() if args.enrich_unpaywall else None
        web_docs, web_errors = [], []
        if args.web_url:
            if not args.allow_web_exposure:
                raise PatentWorkflowError("Crawl4AI access requires --allow-web-exposure.")
            from .web_crawler import Crawl4AIGateway
            gateway = Crawl4AIGateway(set(args.web_allow_domain))
            web_docs, web_errors = asyncio.run(gateway.collect(args.web_url))

        result = PatentResearch(
            patent_provider, paper_providers, folder,
            supplemental_sources=[doc.to_evidence() for doc in web_docs],
            web_documents=web_docs, web_errors=web_errors,
            paper_enricher=enricher, enrichment_limit=args.unpaywall_limit,
            paper_source_warnings=paper_warnings,
        ).run(args.direction, args.patent_query, args.paper_query,
              limit=max(1, min(args.limit, 25)), case_id=args.workflow_case_id)
        indexed = workspace.import_case(folder)
        print("本地文献索引:", database.resolve())
        print("已登记索引:", indexed["indexed"])
        print("AI research handoff:", (folder / "AGENT_NEXT_STEPS.md").resolve())
        print("Patents with retrieved claims:", result["patent_claims_available"])
        print("Scholarly papers:", result["papers_discovered"])
        print("Next: use this chat's AI to investigate, invent, challenge, and write the application.")
        print("Filing authorized: false")
        return 0
    except (PatentWorkflowError, ValueError, FileExistsError, OSError, sqlite3.Error) as exc:
        print("ERROR:", str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
