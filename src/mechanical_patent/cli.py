"""Native-agent CLI. Search and validate documents; the current AI writes the patent."""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys
from uuid import uuid4

from .core import PatentWorkflowError
from .papers import CrossrefProvider, OpenAlexProvider
from .providers import EPOOPSProvider, ImportedPatentProvider
from .workflow import PatentResearch, validate_case
from .workspace_cli import add_workspace_parser, handle_workspace


def _add_research_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--direction", required=True, help="User's engineering problem; kept in private dossier")
    command.add_argument("--case-dir", type=Path, help="New output folder; existing folders cannot be overwritten")
    command.add_argument("--workspace-db", type=Path, default=None,
                         help="索引数据库路径；缺省为案卷父目录/index.sqlite3")
    command.add_argument("--patent-provider", choices=["auto", "epo-ops", "import", "none"], default="auto")
    command.add_argument("--import-json", type=Path, help="Imported records for offline research; always unverified")
    command.add_argument("--paper-provider", action="append", choices=["openalex", "crossref", "import", "none"],
                         help="Repeatable; default OpenAlex+Crossref after explicit search approval")
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
    args = parser.parse_args(argv)

    try:
        if args.command == "workspace":
            return handle_workspace(args)
        if args.command == "validate":
            result = validate_case(args.case_dir)
            print("Quality gate:", result["status"])
            for issue in result["issues"]:
                print("BLOCKER:", issue)
            print("Filing authorized: false")
            return 0 if not result["issues"] else 2

        remote_requested = bool(
            args.patent_provider == "epo-ops"
            or (args.patent_provider == "auto" and os.getenv("EPO_OPS_CLIENT_ID") and os.getenv("EPO_OPS_CLIENT_SECRET"))
            or any(x in {"openalex", "crossref"} for x in (args.paper_provider or []))
            or (args.paper_provider is None and bool(args.paper_query))
        )
        if remote_requested and not args.allow_search_exposure:
            raise PatentWorkflowError("Remote search requires --allow-search-exposure after secrecy review.")
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
            paper_modes = ["openalex", "crossref"] if args.allow_search_exposure else []
        if any(x in {"openalex", "crossref"} for x in paper_modes) and not args.allow_search_exposure:
            raise PatentWorkflowError("Paper API queries require --allow-search-exposure.")
        paper_providers = []
        for mode in dict.fromkeys(paper_modes):
            if mode == "openalex":
                paper_providers.append(OpenAlexProvider())
            elif mode == "crossref":
                paper_providers.append(CrossrefProvider())
            elif mode == "import":
                file = args.paper_import_json or args.import_json
                if not file:
                    raise PatentWorkflowError("--paper-import-json required for imported papers")
                paper_providers.append(ImportedPatentProvider(file))
        web_docs, web_errors = [], []
        if args.web_url:
            if not args.allow_web_exposure:
                raise PatentWorkflowError("Crawl4AI access requires --allow-web-exposure.")
            from .web_crawler import Crawl4AIGateway
            gateway = Crawl4AIGateway(set(args.web_allow_domain))
            web_docs, web_errors = asyncio.run(gateway.collect(args.web_url))

        folder = args.case_dir or Path("cases") / ("case-" + uuid4().hex[:12])
        result = PatentResearch(
            patent_provider, paper_providers, folder,
            supplemental_sources=[doc.to_evidence() for doc in web_docs],
            web_documents=web_docs, web_errors=web_errors,
        ).run(args.direction, args.patent_query, args.paper_query, limit=max(1, min(args.limit, 25)))
        from .local_workspace import LocalPatentWorkspace
        database = args.workspace_db or (folder.parent / "index.sqlite3")
        indexed = LocalPatentWorkspace(database).import_case(folder)
        print("本地文献索引:", database.resolve())
        print("已登记索引:", indexed["indexed"])
        print("AI research handoff:", (folder / "AGENT_NEXT_STEPS.md").resolve())
        print("Patents with retrieved claims:", result["patent_claims_available"])
        print("Scholarly papers:", result["papers_discovered"])
        print("Next: use this chat's AI to investigate, invent, challenge, and write the application.")
        print("Filing authorized: false")
        return 0
    except (PatentWorkflowError, ValueError, FileExistsError, OSError) as exc:
        print("ERROR:", str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
