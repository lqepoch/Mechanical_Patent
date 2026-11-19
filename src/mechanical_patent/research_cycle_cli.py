"""企业案卷科研循环命令，所有结果保存在当前项目的 SQLite 中。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .project_storage import ProjectStorage
from .research_cycle import ResearchCycle


def add_research_cycle_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("cycle", help="项目级多 Agent 科研循环（独立审查/验证/产出）")
    parser.add_argument("--project-id", required=True, help="已创建的项目隔离 ID")
    parser.add_argument("--storage-root", type=Path, default=Path("private_patent_workspace"))
    subs = parser.add_subparsers(dest="cycle_command", required=True)

    create = subs.add_parser("create", help="为当前项目已有案卷创建新科研循环")
    create.add_argument("--case-id", required=True)
    create.add_argument("--cycle-id")

    status = subs.add_parser("status", help="查看各智能体任务和依赖")
    status.add_argument("--cycle-id", required=True)

    claim = subs.add_parser("claim", help="原子领取一个可运行任务")
    claim.add_argument("--cycle-id", required=True)
    claim.add_argument("--role", required=True)
    claim.add_argument("--actor", required=True)
    claim.add_argument("--lease-seconds", type=int, default=1800)

    finish = subs.add_parser("finish", help="提交 JSON 结果并执行研究质量门禁")
    finish.add_argument("--task-id", required=True, type=int)
    finish.add_argument("--actor", required=True)
    finish.add_argument("--result-file", required=True, type=Path)

    fail = subs.add_parser("fail", help="标记失败，可恢复重试")
    fail.add_argument("--task-id", required=True, type=int)
    fail.add_argument("--actor", required=True)
    fail.add_argument("--reason", required=True)
    fail.add_argument("--no-retry", action="store_true")

    iterate = subs.add_parser("iterate", help="独立裁决要求重新研究时创建下一轮")
    iterate.add_argument("--cycle-id", required=True)
    iterate.add_argument("--actor", required=True)
    iterate.add_argument("--rationale", required=True)

    audit = subs.add_parser("audit", help="核查追加事件 SHA256 链")
    audit.add_argument("--cycle-id", required=True)


def handle_research_cycle(args: argparse.Namespace) -> int:
    lab = ResearchCycle(ProjectStorage(args.storage_root, args.project_id))
    command = args.cycle_command
    if command == "create":
        response = lab.create(args.case_id, cycle_id=args.cycle_id)
    elif command == "status":
        response = lab.status(args.cycle_id)
    elif command == "claim":
        response = lab.claim(args.cycle_id, args.role, args.actor, args.lease_seconds)
        response = response or {"status": "当前无可领取任务"}
    elif command == "finish":
        content = json.loads(args.result_file.read_text(encoding="utf-8"))
        response = lab.finish(args.task_id, args.actor, content)
    elif command == "fail":
        response = lab.fail(args.task_id, args.actor, args.reason,
                            retryable=not args.no_retry)
    elif command == "iterate":
        response = lab.iterate(args.cycle_id, args.actor, args.rationale)
    else:
        response = lab.verify_audit(args.cycle_id)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0
