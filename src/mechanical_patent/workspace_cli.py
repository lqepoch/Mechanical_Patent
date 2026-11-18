"""工作流和本地文献库的简体中文命令入口。

ChatGPT/Codex 直接承担 AI 推理；此模块只管理事务性任务、证据核验、
技术方向、原始 PDF 链接和在获得明确授权后的本地 PDF 归档。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .audit import verify_audit_chain
from .local_workspace import LocalPatentWorkspace
from .pdf_archive import archive_patent


def add_workspace_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("workspace", help="企业案卷工作流及本地专利资料库（简体中文）")
    parser.add_argument("--db", type=Path, default=None,
                        help="旧版显式单案卷 SQLite 路径；新项目使用 --project-id")
    parser.add_argument("--project-id", help="绑定项目的隔离 SQLite")
    parser.add_argument("--storage-root", type=Path, default=Path("private_patent_workspace"),
                        help="每个 project_id 有自己的 SQLite 文件")
    subs = parser.add_subparsers(dest="workspace_command", required=True)

    create = subs.add_parser("create", help="创建包含任务依赖的发明研究案卷")
    create.add_argument("--case-id", required=True)
    create.add_argument("--direction", required=True)
    create.add_argument("--confidentiality", default="秘密", choices=["公开", "内部", "秘密", "受控"])

    ingest = subs.add_parser("import", help="将已有专利和论文研究案卷加入本地索引")
    ingest.add_argument("--case-dir", required=True, type=Path)

    status = subs.add_parser("status", help="查看当前轮次全部智能体任务及文献核验状态")
    status.add_argument("--case-id", required=True)

    claim = subs.add_parser("claim", help="按角色领取一个满足依赖的任务")
    claim.add_argument("--case-id", required=True)
    claim.add_argument("--role", required=True)
    claim.add_argument("--actor", required=True)
    claim.add_argument("--lease-seconds", type=int, default=1800)

    finish = subs.add_parser("finish", help="提交任务结构化结果、推进下游工作流")
    finish.add_argument("--task-id", required=True, type=int)
    finish.add_argument("--actor", required=True)
    finish.add_argument("--result-file", required=True, type=Path)

    heartbeat = subs.add_parser("heartbeat", help="执行长时任务时续约租约")
    heartbeat.add_argument("--task-id", required=True, type=int)
    heartbeat.add_argument("--actor", required=True)
    heartbeat.add_argument("--lease-seconds", type=int, default=1800)

    failed = subs.add_parser("fail", help="记录任务失败、回退至队列或进入人工阻断")
    failed.add_argument("--task-id", required=True, type=int)
    failed.add_argument("--actor", required=True)
    failed.add_argument("--reason", required=True)
    failed.add_argument("--no-retry", action="store_true")

    revise = subs.add_parser("revise", help="经方向评审后开启新一轮研究，保留旧轮次")
    revise.add_argument("--case-id", required=True)
    revise.add_argument("--actor", required=True)
    revise.add_argument("--direction", required=True)
    revise.add_argument("--rationale", required=True)

    search = subs.add_parser("search", help="在本地专利/论文元数据中快速检索")
    search.add_argument("--query", required=True)
    search.add_argument("--case-id")
    search.add_argument("--limit", type=int, default=30)

    review = subs.add_parser("review", help="记录独立文献核验与公开 PDF 链接")
    review.add_argument("--case-id", required=True)
    review.add_argument("--doc-id", required=True)
    review.add_argument("--actor", required=True)
    decision = review.add_mutually_exclusive_group(required=True)
    decision.add_argument("--accept", action="store_true")
    decision.add_argument("--reject", action="store_true")
    review.add_argument("--rationale", required=True)
    review.add_argument("--pdf-url", help="经人工核对的公开原文 PDF HTTPS 链接")

    source = subs.add_parser("source", help="展示公开 PDF 原始链接与本地归档索引")
    source.add_argument("--case-id", required=True)
    source.add_argument("--doc-id", required=True)

    archive = subs.add_parser("archive", help="在有明确授权时归档原始公开 PDF")
    archive.add_argument("--case-id", required=True)
    archive.add_argument("--doc-id", required=True)
    archive.add_argument("--pdf-dir", required=True, type=Path)
    archive.add_argument("--allow-domain", action="append", required=True)
    archive.add_argument("--authorized", action="store_true")

    audit = subs.add_parser("audit", help="核对本地案卷事件哈希链")
    audit.add_argument("--case-dir", required=True, type=Path)


def handle_workspace(args: argparse.Namespace) -> int:
    command = args.workspace_command
    if command == "audit":
        result = verify_audit_chain(args.case_dir)
    else:
        if args.project_id:
            from .project_storage import ProjectStorage
            project = ProjectStorage(args.storage_root,args.project_id)
            if args.db is not None and args.db.resolve()!=project.db_path.resolve():
                raise ValueError("项目模式禁止访问其他数据库。")
            workspace = project.workspace
        elif args.db:
            workspace = LocalPatentWorkspace(args.db)
        else:
            raise ValueError("必须提供 --project-id（新项目）或显式 --db（旧库兼容模式）。")
        if command == "create":
            result = workspace.create_case(
                args.case_id, args.direction, confidentiality=args.confidentiality
            )
        elif command == "import":
            result = workspace.import_case(args.case_dir)
        elif command == "status":
            result = workspace.status(args.case_id)
        elif command == "claim":
            result = workspace.claim(
                args.case_id, role=args.role, actor=args.actor,
                lease_seconds=args.lease_seconds
            ) or {"status": "当前无可领取任务"}
        elif command == "finish":
            data = json.loads(args.result_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("任务结果文件必须为 JSON 对象。")
            result = workspace.finish(args.task_id, actor=args.actor, result=data)
        elif command == "heartbeat":
            result = workspace.heartbeat(
                args.task_id, actor=args.actor, lease_seconds=args.lease_seconds
            )
        elif command == "fail":
            result = workspace.fail(
                args.task_id, actor=args.actor,
                reason=args.reason, retryable=not args.no_retry
            )
        elif command == "revise":
            number = workspace.next_revision(
                args.case_id, actor=args.actor,
                new_direction=args.direction, rationale=args.rationale
            )
            result = {"case_id": args.case_id, "revision": number, "status": "已开始新一轮研发"}
        elif command == "search":
            result = {
                "query": args.query,
                "records": workspace.search_documents(
                    args.query, case_id=args.case_id, limit=args.limit
                ),
            }
        elif command == "review":
            result = workspace.review_document(
                args.case_id, args.doc_id, actor=args.actor,
                accepted=args.accept, rationale=args.rationale,
                public_pdf_url=args.pdf_url,
            )
        elif command == "source":
            result = workspace.pdf_source(args.case_id, args.doc_id)
        elif command == "archive":
            result = archive_patent(
                workspace, case_id=args.case_id, doc_id=args.doc_id,
                storage_dir=args.pdf_dir, allowed_hosts=set(args.allow_domain),
                authorized=args.authorized,
            )
        else:
            raise ValueError("未知的案卷操作。")
    # 标准输出可能被终端或 CI 长期留存，因此不得输出未公开发明、
    # 内部检索方向、人员身份、完整审查理由或本地秘密路径。
    # 完整结构化结果始终在受控 SQLite 中，CLI 仅发布白名单字段。
    if command in {"create", "status"}:
        safe = {
            "case_id": result["case_id"], "revision": result["revision"],
            "status": result["status"],
            "tasks": [
                {"id": task["id"], "step": task["step"], "status": task["status"],
                 "attempts": task["attempts"]}
                for task in result["tasks"]
            ],
            "source_reviews": result["source_reviews"],
        }
    elif command == "claim":
        safe = {
            key: result[key] for key in
            ("task_id", "case_id", "revision", "step", "role", "lease_expires", "status")
            if key in result
        }
    elif command == "search":
        safe = {
            "match_count": len(result["records"]),
            "records": [
                {"case_id": row["case_id"], "doc_id": row["doc_id"],
                 "publication": row["publication"], "title": row["title"],
                 "kind": row["kind"], "verification_status": row["verification_status"]}
                for row in result["records"]
            ],
        }
    elif command == "source":
        safe = {
            "doc_id": result["doc_id"], "publication": result["publication"],
            "public_pdf_url": result["public_pdf_url"],
            "source_url": result["source_url"],
            "verification_status": result["verification_status"],
        }
    elif command == "archive":
        safe = {"case_id": result["case_id"], "doc_id": result["doc_id"],
                "sha256": result["sha256"], "bytes": result["bytes"],
                "status": "已归档（完整路径保留在数据库）"}
    elif command == "review":
        safe = {"doc_id": result["doc_id"],
                "verification_status": result["verification_status"]}
    elif command == "import":
        safe = {"case_id": result["case_id"], "indexed": result["indexed"]}
    elif command == "audit":
        safe = {"valid": result["valid"], "count": result["count"],
                "head_sha256": result["head_sha256"], "errors": result["errors"]}
    else:
        safe = {
            "case_id": result.get("case_id"), "task_id": result.get("task_id"),
            "step": result.get("step"), "revision": result.get("revision"),
            "status": result.get("status"), "attempts": result.get("attempts"),
        }
        safe = {key: value for key, value in safe.items() if value is not None}
    print(json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if (command != "audit" or result["valid"]) else 2
