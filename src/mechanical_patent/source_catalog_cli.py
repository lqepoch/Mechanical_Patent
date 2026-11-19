"""Local admin/operator CLI for the public problem source catalog."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import PatentWorkflowError
from .problem_sources import ProblemSourceRegistry


def add_source_catalog_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("source-catalog",
        help="公共研发课题平台目录，候选来源隔离，增量监测与证据研究队列")
    p.add_argument("action", choices=("sources","topics","inbox","propose",
        "approve","observe","derive","plan","note","cycle","audit","taxonomy","analogies"))
    p.add_argument("--storage-root", type=Path, default=Path("private_patent_workspace"))
    p.add_argument("--status", default="approved")
    p.add_argument("--industry", default="", help="跨行业检索行业标签，例如 robotics、marine")
    p.add_argument("--mechanism", default="", help="共享物理机理标签，例如 fluid、fatigue")
    p.add_argument("--industry-tag", action="append", default=None,
                   help="新增平台或研究假说的行业标签，可多次指定")
    p.add_argument("--mechanism-tag", action="append", default=None,
                   help="新增平台或研究假说的物理机理，可多次指定")
    p.add_argument("--source-id", default="")
    p.add_argument("--observation-id", default="")
    p.add_argument("--topic-id", default="")
    p.add_argument("--name", default="")
    p.add_argument("--url", default="")
    p.add_argument("--reason", default="")
    p.add_argument("--discovered-from", default="manual")
    p.add_argument("--reviewer", default="")
    p.add_argument("--rights-reviewed", action="store_true")
    p.add_argument("--mode", choices=("manual","rss"), default="manual")
    p.add_argument("--feed-url", default="")
    p.add_argument("--cadence-hours", type=int, default=168)
    p.add_argument("--title", default="")
    p.add_argument("--summary", default="")
    p.add_argument("--published-at", default="")
    p.add_argument("--problem", default="")
    p.add_argument("--hypothesis", default="")
    p.add_argument("--falsification", default="")
    p.add_argument("--domain", default="mechanical")
    p.add_argument("--agent", default="")
    p.add_argument("--findings", default="")
    p.add_argument("--evidence-url", action="append", default=[])
    p.add_argument("--public-only", action="store_true")
    p.add_argument("--allow-public-network", action="store_true",
                   help="明确授权本次仅访问人工批准的公开 RSS 来源")
    p.add_argument("--max-sources", type=int, default=5)
    p.add_argument("--limit", type=int, default=60)


def handle_source_catalog(args: argparse.Namespace) -> int:
    registry = ProblemSourceRegistry(args.storage_root)
    action = args.action
    if action == "sources":
        data = {"sources":registry.sources(args.status,args.limit,args.industry,args.mechanism)}
    elif action == "topics":
        data = {"topics":registry.topics(args.limit,args.industry,args.mechanism)}
    elif action == "taxonomy":
        data = registry.taxonomy()
    elif action == "analogies":
        data = registry.analogies(args.industry,args.mechanism,args.limit)
    elif action == "inbox":
        data = registry.inbox(args.limit)
    elif action == "propose":
        data = registry.propose(args.name,args.url,args.reason,
                                discovered_from=args.discovered_from,
                                industry_tags=args.industry_tag,mechanism_tags=args.mechanism_tag)
    elif action == "approve":
        data = registry.approve(args.source_id,reviewer=args.reviewer,
               rights_reviewed=args.rights_reviewed,mode=args.mode,
               feed_url=args.feed_url,cadence_hours=args.cadence_hours)
    elif action == "observe":
        data = registry.observe(args.source_id,args.url,args.title,
                    summary=args.summary,published_at=args.published_at)
    elif action == "derive":
        data = registry.derive_topic(args.observation_id,args.problem,
                    args.hypothesis,args.falsification,args.domain,
                    args.industry_tag,args.mechanism_tag)
    elif action == "plan":
        data = registry.plan(args.topic_id)
    elif action == "note":
        data = registry.record_research(args.topic_id,args.agent,args.findings,
                    args.evidence_url,public_only=args.public_only)
    elif action == "cycle":
        data = registry.cycle(allow_network=args.allow_public_network,
                              max_sources=args.max_sources)
    elif action == "audit":
        data = registry.audit_verify()
    else:
        raise PatentWorkflowError("未知的课题来源目录动作。")
    print(json.dumps(data,ensure_ascii=False,indent=2))
    return 0 if action!="cycle" or data["status"]!="partial_or_failed" else 2
