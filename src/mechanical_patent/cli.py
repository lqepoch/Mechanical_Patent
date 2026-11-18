"""Single-command operator interface. Research never implies authorization to file."""
import argparse
from pathlib import Path
import sys
from uuid import uuid4

from .core import PatentWorkflowError
from .llm import JSONGateway
from .providers import EPOOPSProvider, ImportedPatentProvider
from .workflow import PatentResearch


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mechanical-patent")
    subs = parser.add_subparsers(dest="command", required=True)
    run = subs.add_parser("run", help="Search -> ideation -> challenge -> engineering -> drafting")
    run.add_argument("--direction", required=True, help="Technical direction / engineering problem")
    run.add_argument("--provider", choices=("epo-ops", "import"), default="epo-ops")
    run.add_argument("--import-json", type=Path, help="Offline corpus, not live verified prior art")
    run.add_argument("--case-dir", type=Path, help="New private folder; must not exist")
    run.add_argument("--max-ideas", type=int, default=5)
    run.add_argument("--model")
    run.add_argument("--llm-base-url")
    run.add_argument("--allow-external-llm", action="store_true")
    run.add_argument("--allow-search-exposure", action="store_true",
                     help="Approve sending sanitized search terms to an external patent provider")
    args = parser.parse_args(argv)
    try:
        if args.provider == "epo-ops":
            if not args.allow_search_exposure:
                raise PatentWorkflowError("Remote search may expose unpublished R&D terms; explicitly approve with --allow-search-exposure.")
            provider = EPOOPSProvider()
        else:
            if not args.import_json:
                raise PatentWorkflowError("--import-json is required with --provider import.")
            provider = ImportedPatentProvider(args.import_json)
        llm = JSONGateway(base_url=args.llm_base_url, model=args.model, allow_external=args.allow_external_llm)
        folder = args.case_dir or Path("cases") / ("case-" + uuid4().hex[:12])
        result = PatentResearch(provider, llm, folder, max_ideas=args.max_ideas).run(args.direction)
        print("Research dossier:", (folder / "DOSSIER.md").resolve())
        print("Result:", result["status"], "| filing_authorized=false")
        return 0 if result["status"] == "needs_human_review" else 2
    except (PatentWorkflowError, ValueError, FileExistsError, OSError) as exc:
        print("ERROR:", str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
