"""企业级案卷事件账本的本地实现（可验篡改，非可信时间戳或数字签名）。

生产环境应由数据库事务、访问控制、WORM 存储、签名和项目权限接管。
此处提供可复用的事件契约、顺序校验、单写入者互斥与异常处理。
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Iterator
from uuid import uuid4

from .core import PatentWorkflowError, utc_now

STAGES = (
    "任务接收", "保密审查", "专利检索", "论文检索", "技术分析",
    "发明构思", "反证检索", "工程论证", "工程技术方案", "申请撰写",
    "质量审核", "技术签核", "知识产权签核", "人工提交决策",
)

ROLES = frozenset({"研究人员", "机械工程师", "专利专业人员", "项目负责人", "管理员", "系统"})


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: dict[str, Any]) -> str:
    return sha256(_canonical(value)).hexdigest()


@contextmanager
def _exclusive_writer(directory: Path) -> Iterator[None]:
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".写入锁"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise PatentWorkflowError("案卷事件正被其他进程写入，请检查并发操作或遗留锁。") from exc
    try:
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
        yield
    finally:
        try:
            lock.unlink(missing_ok=True)
        except OSError:
            pass


def verify_audit_chain(case_dir: Path) -> dict[str, Any]:
    """核对连续序号、前一事件哈希和事件内容，不声明防管理员改写。"""
    directory = Path(case_dir) / "events"
    if not directory.is_dir():
        return {"valid": True, "count": 0, "head_sha256": "0" * 64, "errors": []}
    files = sorted(directory.glob("*.json"))
    previous = "0" * 64
    errors: list[str] = []
    for index, path in enumerate(files, start=1):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("事件 JSON 应为对象")
            expected = data.get("event_sha256")
            unsigned = {k: v for k, v in data.items() if k != "event_sha256"}
            if data.get("sequence") != index or path.name != f"{index:06d}.json":
                errors.append(f"事件序号不连续：{path.name}")
            if data.get("previous_sha256") != previous:
                errors.append(f"前序哈希不匹配：{path.name}")
            if expected != _hash(unsigned):
                errors.append(f"事件内容哈希不匹配：{path.name}")
            previous = str(expected or "")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"事件无法读取：{path.name}，{exc}")
            previous = ""
    return {
        "valid": not errors, "count": len(files), "head_sha256": previous,
        "errors": errors,
        "limitation": "本地哈希链仅能检测部分非授权修改；生产级审计还需可信存证、权限隔离和备份。",
    }


def append_audit_event(
    case_dir: Path, *, stage: str, action: str,
    actor: str, role: str, payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """以最小本地互斥追加审计事件；用户身份仍须由外部 IAM 校验。"""
    if stage not in STAGES:
        raise PatentWorkflowError(f"非法案卷阶段：{stage}")
    if role not in ROLES:
        raise PatentWorkflowError(f"非法审计角色：{role}")
    if not isinstance(actor, str) or not 1 <= len(actor) <= 120 or not actor.strip():
        raise PatentWorkflowError("审计角色执行人标识不能为空。")
    if not isinstance(action, str) or not 1 <= len(action) <= 120:
        raise PatentWorkflowError("审计操作名不合格。")
    payload = payload or {}
    if not isinstance(payload, dict):
        raise PatentWorkflowError("审计负载须为结构化对象。")
    directory = Path(case_dir) / "events"
    with _exclusive_writer(directory):
        prior = verify_audit_chain(case_dir)
        if not prior["valid"]:
            raise PatentWorkflowError("历史审计链校验失败，已禁止继续追加。")
        number = prior["count"] + 1
        event = {
            "sequence": number, "event_id": uuid4().hex, "recorded_at": utc_now(),
            "stage": stage, "action": action, "actor": actor, "role": role,
            "payload_sha256": _hash(payload), "previous_sha256": prior["head_sha256"],
            "payload": payload,
            "note": "执行人身份与审批授权需要由企业身份平台独立核实。",
        }
        event["event_sha256"] = _hash(event)
        target = directory / f"{number:06d}.json"
        try:
            with target.open("x", encoding="utf-8") as file:
                json.dump(event, file, ensure_ascii=False, indent=2, sort_keys=True)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
        except FileExistsError as exc:
            raise PatentWorkflowError("审计事件序号冲突，请核对并发执行。") from exc
        return event
