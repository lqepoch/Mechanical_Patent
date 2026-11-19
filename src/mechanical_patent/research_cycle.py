"""项目隔离的多 Agent 科研循环：任务租约、证据约束、反证、迭代与成果分流。

运行时不调用模型。当前 AI 宿主执行各角色工作；本层只负责可恢复调度、
结构化结果、证据引用和不可由模型绕过的确定性门禁。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from uuid import uuid4

from .core import PatentWorkflowError, utc_now
from .project_storage import ProjectStorage

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_ATTEMPTS = 3
_STEPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("课题发现", "课题发现智能体", ()),
    ("专利检索", "专利检索智能体", ("课题发现",)),
    ("论文检索", "论文检索智能体", ("课题发现",)),
    ("证据整合", "证据核验智能体", ("专利检索", "论文检索")),
    ("构思生成", "发明构思智能体", ("证据整合",)),
    ("反证检索", "独立反证智能体", ("构思生成",)),
    ("独立裁决", "科研审查智能体", ("反证检索",)),
    ("技术验证", "理论与实验智能体", ("独立裁决",)),
    ("成果分流", "成果管理智能体", ("技术验证",)),
    ("持续监测", "情报监测智能体", ("成果分流",)),
)
ROLES = {name: role for name, role, _ in _STEPS}
DEPS = {name: deps for name, _, deps in _STEPS}
_ALLOWED_ROUTES = {"technical_brief", "paper_draft", "patent_candidate", "new_research"}


def _required(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise PatentWorkflowError(f"{field} 必须为非空文本且长度不超过4000。")
    return value.strip()


def _items(value: Any, field: str, *, minimum: int = 0, maximum: int = 100) -> list:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise PatentWorkflowError(f"{field} 必须为列表，数量在 {minimum}–{maximum} 之间。")
    return value


def _encoded(data: Any) -> str:
    try:
        result = json.dumps(data, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PatentWorkflowError("研究任务结果需要可序列化的有限 JSON。") from exc
    if len(result.encode("utf-8")) > 131072:
        raise PatentWorkflowError("单任务结果不能超过128KiB；大型数据存入私有对象存储并引用哈希。")
    return result


class ResearchCycle:
    """针对单一 ProjectStorage 的研究编排；跨项目没有读写入口。"""

    def __init__(self, project: ProjectStorage):
        self.project = project
        self.db = project.workspace
        with self.db.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS research_cycles (
                    cycle_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(case_id),
                    case_revision INTEGER NOT NULL,
                    iteration INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cycle_id TEXT NOT NULL REFERENCES research_cycles(cycle_id),
                    iteration INTEGER NOT NULL,
                    step TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT '待领取',
                    actor TEXT, lease_until TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT, result_sha256 TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(cycle_id, iteration, step)
                );
                CREATE INDEX IF NOT EXISTS idx_research_tasks
                    ON research_tasks(cycle_id, iteration, status);
                CREATE TABLE IF NOT EXISTS research_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    cycle_id TEXT NOT NULL REFERENCES research_cycles(cycle_id),
                    iteration INTEGER NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    previous_sha256 TEXT NOT NULL,
                    event_sha256 TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_research_events
                    ON research_events(cycle_id, seq);
            """)

    def _cycle(self, conn: sqlite3.Connection, cycle_id: str) -> sqlite3.Row:
        if not isinstance(cycle_id, str) or not _ID.fullmatch(cycle_id):
            raise PatentWorkflowError("研究循环编号非法。")
        record = conn.execute(
            "SELECT * FROM research_cycles WHERE cycle_id=?", (cycle_id,)
        ).fetchone()
        if record is None:
            raise PatentWorkflowError("当前项目内不存在该科研循环。")
        return record

    @staticmethod
    def _event(conn: sqlite3.Connection, cycle: sqlite3.Row, actor: str,
               action: str, payload: dict[str, Any]) -> None:
        previous = conn.execute(
            "SELECT event_sha256 FROM research_events WHERE cycle_id=? ORDER BY seq DESC LIMIT 1",
            (cycle["cycle_id"],),
        ).fetchone()
        prev = previous["event_sha256"] if previous else "0" * 64
        now = utc_now()
        content = _encoded({"cycle_id": cycle["cycle_id"], "iteration": cycle["iteration"],
                            "actor": actor, "action": action, "payload": payload, "at": now})
        digest = sha256((prev + content).encode("utf-8")).hexdigest()
        conn.execute(
            "INSERT INTO research_events(cycle_id,iteration,actor,action,payload_json,"
            "occurred_at,previous_sha256,event_sha256) VALUES(?,?,?,?,?,?,?,?)",
            (cycle["cycle_id"], cycle["iteration"], actor, action, content, now, prev, digest),
        )

    @staticmethod
    def _insert_jobs(conn: sqlite3.Connection, cycle_id: str, iteration: int) -> None:
        for name, role, _ in _STEPS:
            conn.execute(
                "INSERT INTO research_tasks(cycle_id,iteration,step,role,updated_at)"
                " VALUES(?,?,?,?,?)", (cycle_id, iteration, name, role, utc_now()),
            )

    def create(self, case_id: str, *, cycle_id: str | None = None) -> dict[str, Any]:
        if not isinstance(case_id, str) or not _ID.fullmatch(case_id):
            raise PatentWorkflowError("案卷编号非法。")
        cycle_id = cycle_id or "RC-" + uuid4().hex[:20]
        if not _ID.fullmatch(cycle_id):
            raise PatentWorkflowError("研究循环编号非法。")
        with self.db.connect(write=True) as conn:
            case = conn.execute("SELECT revision FROM cases WHERE case_id=?", (case_id,)).fetchone()
            if case is None:
                raise PatentWorkflowError("必须先在当前项目创建案卷并落实保密分级。")
            now = utc_now()
            conn.execute(
                "INSERT INTO research_cycles VALUES(?,?,?,?,?,?,?)",
                (cycle_id, case_id, case["revision"], 1, "进行中", now, now),
            )
            self._insert_jobs(conn, cycle_id, 1)
            cycle = self._cycle(conn, cycle_id)
            self._event(conn, cycle, "系统", "创建科研循环", {"case_id": case_id})
        return self.status(cycle_id)

    def status(self, cycle_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            cycle = self._cycle(conn, cycle_id)
            rows = conn.execute(
                "SELECT id,step,role,status,attempts,lease_until FROM research_tasks "
                "WHERE cycle_id=? AND iteration=? ORDER BY id",
                (cycle_id, cycle["iteration"]),
            ).fetchall()
            done = {r["step"] for r in rows if r["status"] == "已完成"}
            tasks = [{**dict(r), "ready": (
                r["status"] == "待领取" and cycle["status"] == "进行中"
                and all(d in done for d in DEPS[r["step"]])
            )} for r in rows]
            return {
                "project_id": self.project.project_id,
                "cycle_id": cycle_id, "case_id": cycle["case_id"],
                "iteration": cycle["iteration"], "status": cycle["status"],
                "tasks": tasks, "ready_steps": [t["step"] for t in tasks if t["ready"]],
                "filing_authorized": False, "human_validation": "required",
            }

    def claim(self, cycle_id: str, role: str, actor: str,
              lease_seconds: int = 1800) -> dict[str, Any] | None:
        _required(actor, "执行人")
        if not 30 <= lease_seconds <= 7200:
            raise PatentWorkflowError("租约必须在30至7200秒之间。")
        with self.db.connect(write=True) as conn:
            cycle = self._cycle(conn, cycle_id)
            if cycle["status"] != "进行中":
                return None
            current = conn.execute(
                "SELECT revision FROM cases WHERE case_id=?", (cycle["case_id"],)
            ).fetchone()
            if current["revision"] != cycle["case_revision"]:
                raise PatentWorkflowError("案卷已变更 revision；请创建新的科研循环。")
            rows = conn.execute(
                "SELECT * FROM research_tasks WHERE cycle_id=? AND iteration=? ORDER BY id",
                (cycle_id, cycle["iteration"]),
            ).fetchall()
            done = {r["step"] for r in rows if r["status"] == "已完成"}
            now = datetime.now(timezone.utc)
            for row in rows:
                if row["role"] != role:
                    continue
                if row["status"] == "运行中":
                    if row["lease_until"] and datetime.fromisoformat(row["lease_until"]) > now:
                        continue
                    if row["attempts"] >= _MAX_ATTEMPTS:
                        conn.execute("UPDATE research_tasks SET status='已阻断' WHERE id=?", (row["id"],))
                        conn.execute("UPDATE research_cycles SET status='已阻断' WHERE cycle_id=?", (cycle_id,))
                        self._event(conn, cycle, "系统", "任务租约耗尽", {"step": row["step"]})
                        return None
                elif row["status"] != "待领取":
                    continue
                if not all(name in done for name in DEPS[row["step"]]):
                    continue
                expire = (now + timedelta(seconds=lease_seconds)).isoformat()
                conn.execute(
                    "UPDATE research_tasks SET status='运行中', actor=?, attempts=attempts+1,"
                    "lease_until=?, updated_at=? WHERE id=?",
                    (actor.strip(), expire, utc_now(), row["id"]),
                )
                self._event(conn, cycle, actor.strip(), "领取科研任务",
                            {"task_id": row["id"], "step": row["step"]})
                return {"task_id": row["id"], "step": row["step"], "role": role,
                        "cycle_id": cycle_id, "iteration": cycle["iteration"],
                        "lease_until": expire, "outbound_approved":
                        self.db.can_egress(cycle["case_id"])}
        return None

    @staticmethod
    def _result(conn: sqlite3.Connection, cycle_id: str, iteration: int,
                step: str) -> dict[str, Any]:
        row = conn.execute(
            "SELECT result_json FROM research_tasks WHERE cycle_id=? AND iteration=? AND step=?",
            (cycle_id, iteration, step),
        ).fetchone()
        if row is None or not row["result_json"]:
            raise PatentWorkflowError(f"缺少前序阶段：{step}")
        return json.loads(row["result_json"])

    @staticmethod
    def _verified_ids(conn: sqlite3.Connection, case_id: str,
                      ids: list[Any]) -> None:
        for item in ids:
            if not isinstance(item, str) or not item.startswith("EV-"):
                raise PatentWorkflowError("证据必须使用当前案卷真实 EV- 编号。")
            row = conn.execute(
                "SELECT verification_status FROM documents WHERE case_id=? AND doc_id=?",
                (case_id, item),
            ).fetchone()
            if row is None or row["verification_status"] != "已核验":
                raise PatentWorkflowError(f"证据 {item} 尚未通过当前案卷的资料核验。")

    def _artifact(self, value: Any) -> None:
        if not isinstance(value, dict):
            raise PatentWorkflowError("验证附件需要相对路径和 SHA256。")
        rel = _required(value.get("path"), "附件路径")
        expected = value.get("sha256")
        if not isinstance(expected, str) or not _SHA.fullmatch(expected):
            raise PatentWorkflowError("验证附件 SHA256 无效。")
        path = self.project.root / rel
        root = self.project.root.resolve()
        if Path(rel).is_absolute() or not path.resolve().is_relative_to(root):
            raise PatentWorkflowError("验证附件越过项目私有存储边界。")
        if any(p.is_symlink() for p in [path, *path.parents] if p != root and root in p.parents):
            raise PatentWorkflowError("验证附件路径不可经符号链接读取。")
        if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            raise PatentWorkflowError("验证附件不存在或超过20MiB上限。")
        if sha256(path.read_bytes()).hexdigest() != expected:
            raise PatentWorkflowError("验证附件哈希不匹配。")

    def _check(self, conn: sqlite3.Connection, cycle: sqlite3.Row,
               step: str, actor: str, result: dict[str, Any]) -> str | None:
        case_id, iteration, cycle_id = cycle["case_id"], cycle["iteration"], cycle["cycle_id"]
        if step == "课题发现":
            _required(result.get("problem"), "研究问题")
            _required(result.get("measurable_goal"), "可量化研究目标")
        elif step in {"专利检索", "论文检索"}:
            _required(result.get("coverage_report"), "真实检索覆盖报告")
            remote = result.get("remote_used", False)
            if not isinstance(remote, bool):
                raise PatentWorkflowError("remote_used 必须为布尔值。")
            if remote and not self.db.can_egress(case_id):
                raise PatentWorkflowError("真实远程检索前必须完成该轮保密审批。")
        elif step == "证据整合":
            ids = _items(result.get("evidence_ids"), "证据编号", minimum=1)
            self._verified_ids(conn, case_id, ids)
            _required(result.get("limitations"), "文献证据局限")
        elif step == "构思生成":
            records = _items(result.get("hypotheses"), "候选假设", minimum=2, maximum=50)
            keys = set()
            for row in records:
                if not isinstance(row, dict):
                    raise PatentWorkflowError("候选假设结构非法。")
                key = _required(row.get("id"), "候选编号")
                if not _ID.fullmatch(key) or key in keys:
                    raise PatentWorkflowError("候选编号非法或重复。")
                keys.add(key)
                _required(row.get("mechanism"), "候选工作原理")
                _required(row.get("enabling_details"), "实现结构或算法")
                _items(row.get("falsification_tests"), "可证伪试验", minimum=1)
                self._verified_ids(conn, case_id,
                                   _items(row.get("evidence_ids"), "候选来源", minimum=1))
        elif step == "反证检索":
            keys = {r["id"] for r in self._result(conn, cycle_id, iteration,
                                                  "构思生成")["hypotheses"]}
            challenges = _items(result.get("challenges"), "反证意见", minimum=len(keys))
            if {r.get("hypothesis_id") for r in challenges if isinstance(r, dict)} != keys:
                raise PatentWorkflowError("必须逐项覆盖全部候选且不得重复。")
            if len(challenges) != len(keys):
                raise PatentWorkflowError("反证意见不能重复。")
            for item in challenges:
                _required(item.get("risk"), "现有技术或工程反例")
                self._verified_ids(conn, case_id,
                                   _items(item.get("evidence_ids"), "反证文献编号"))
        elif step == "独立裁决":
            for other_step in ("构思生成", "反证检索"):
                creator = conn.execute(
                    "SELECT actor FROM research_tasks WHERE cycle_id=? AND iteration=? AND step=?",
                    (cycle_id, iteration, other_step),
                ).fetchone()
                if creator is not None and creator["actor"] == actor:
                    raise PatentWorkflowError("独立裁决不能由本轮构思或反证执行人完成。")
            choice = result.get("decision")
            if choice not in {"advance", "iterate", "stop"}:
                raise PatentWorkflowError("裁决只能为 advance、iterate 或 stop。")
            _required(result.get("rationale"), "裁决理由")
            keys = {r["id"] for r in self._result(conn, cycle_id, iteration,
                                                  "构思生成")["hypotheses"]}
            selected = _items(result.get("selected_ids"), "选定候选编号",
                              minimum=1 if choice == "advance" else 0)
            if len(selected) != len(set(selected)) or not set(selected) <= keys:
                raise PatentWorkflowError("选定候选必须属于当前轮构思。")
            return {"iterate": "待迭代", "stop": "已终止"}.get(choice)
        elif step == "技术验证":
            selected = set(self._result(conn, cycle_id, iteration,
                                        "独立裁决")["selected_ids"])
            values = _items(result.get("assessments"), "技术验证记录", minimum=len(selected))
            if len(values) != len(selected) or {v.get("hypothesis_id") for v in values
                                               if isinstance(v, dict)} != selected:
                raise PatentWorkflowError("必须逐项说明所有选中候选的验证程度。")
            for item in values:
                level = item.get("level")
                if level not in {"L0", "L1", "L2", "L3", "L4", "L5"}:
                    raise PatentWorkflowError("验证级别必须为 L0-L5。")
                _required(item.get("method"), "验证方法")
                _required(item.get("limitations"), "验证局限")
                artifacts = _items(item.get("artifacts"), "可追溯验证附件")
                if level in {"L2", "L3", "L4", "L5"} and not artifacts:
                    raise PatentWorkflowError("计算、仿真与实验结论需要真实落盘附件。")
                for artifact in artifacts:
                    self._artifact(artifact)
        elif step == "成果分流":
            selected = set(self._result(conn, cycle_id, iteration,
                                        "独立裁决")["selected_ids"])
            routes = _items(result.get("routes"), "研究成果路线", minimum=1)
            for item in routes:
                if (not isinstance(item, dict) or
                    item.get("target") not in _ALLOWED_ROUTES or
                    item.get("hypothesis_id") not in selected):
                    raise PatentWorkflowError("成果路线只允许选中候选的技术方案、论文草稿、专利候选和后续研究。")
            if result.get("filing_authorized") or result.get("published"):
                raise PatentWorkflowError("科研成果分流不能直接授权递交或宣布发表。")
        elif step == "持续监测":
            _items(result.get("followups"), "后续监测任务", maximum=50)
            return "已完成"
        return None

    def finish(self, task_id: int, actor: str, result: dict[str, Any]) -> dict[str, Any]:
        _required(actor, "执行人")
        if not isinstance(result, dict):
            raise PatentWorkflowError("研究任务结果必须是 JSON 对象。")
        encoded = _encoded(result)
        with self.db.connect(write=True) as conn:
            task = conn.execute("SELECT * FROM research_tasks WHERE id=?", (task_id,)).fetchone()
            if task is None:
                raise PatentWorkflowError("不存在该任务。")
            cycle = self._cycle(conn, task["cycle_id"])
            if cycle["status"] != "进行中" or task["iteration"] != cycle["iteration"]:
                raise PatentWorkflowError("科研循环不在当前活动轮次。")
            if task["status"] != "运行中" or task["actor"] != actor:
                raise PatentWorkflowError("仅当前租约持有人可提交任务结果。")
            if (not task["lease_until"] or
                datetime.fromisoformat(task["lease_until"]) <= datetime.now(timezone.utc)):
                raise PatentWorkflowError("任务租约已过期，请重新领取。")
            new_status = self._check(conn, cycle, task["step"], actor, result)
            now = utc_now()
            conn.execute(
                "UPDATE research_tasks SET status='已完成', result_json=?, result_sha256=?,"
                "lease_until=NULL, updated_at=? WHERE id=?",
                (encoded, sha256(encoded.encode("utf-8")).hexdigest(), now, task_id),
            )
            if new_status:
                conn.execute(
                    "UPDATE research_cycles SET status=?, updated_at=? WHERE cycle_id=?",
                    (new_status, now, cycle["cycle_id"]),
                )
                if new_status in {"待迭代", "已终止"}:
                    conn.execute(
                        "UPDATE research_tasks SET status='已阻断', updated_at=? "
                        "WHERE cycle_id=? AND iteration=? AND status='待领取'",
                        (now, cycle["cycle_id"], cycle["iteration"]),
                    )
            self._event(conn, cycle, actor, "完成科研任务",
                        {"task_id": task_id, "step": task["step"],
                         "result_sha256": sha256(encoded.encode("utf-8")).hexdigest(),
                         "cycle_status": new_status or "进行中"})
        return self.status(cycle["cycle_id"])

    def fail(self, task_id: int, actor: str, reason: str,
             *, retryable: bool = True) -> dict[str, Any]:
        _required(reason, "失败原因")
        with self.db.connect(write=True) as conn:
            task = conn.execute("SELECT * FROM research_tasks WHERE id=?", (task_id,)).fetchone()
            if task is None or task["actor"] != actor or task["status"] != "运行中":
                raise PatentWorkflowError("只有任务领取人可以上报失败。")
            cycle = self._cycle(conn, task["cycle_id"])
            status = "待领取" if retryable and task["attempts"] < _MAX_ATTEMPTS else "已阻断"
            conn.execute(
                "UPDATE research_tasks SET status=?, lease_until=NULL,updated_at=? WHERE id=?",
                (status, utc_now(), task_id),
            )
            if status == "已阻断":
                conn.execute("UPDATE research_cycles SET status='已阻断' WHERE cycle_id=?",
                             (cycle["cycle_id"],))
            self._event(conn, cycle, actor, "任务执行失败",
                        {"step": task["step"], "reason": reason, "retryable": status == "待领取"})
        return self.status(cycle["cycle_id"])

    def iterate(self, cycle_id: str, actor: str, rationale: str) -> dict[str, Any]:
        _required(actor, "执行人")
        _required(rationale, "迭代理由")
        with self.db.connect(write=True) as conn:
            cycle = self._cycle(conn, cycle_id)
            if cycle["status"] != "待迭代":
                raise PatentWorkflowError("仅独立裁决要求迭代后才能开启新一轮。")
            current = conn.execute(
                "SELECT revision FROM cases WHERE case_id=?", (cycle["case_id"],)
            ).fetchone()
            if current["revision"] != cycle["case_revision"]:
                raise PatentWorkflowError("原案卷 revision 已变化，需要新建科研循环。")
            next_number = cycle["iteration"] + 1
            if next_number > 20:
                raise PatentWorkflowError("超过20轮迭代上限，需人工归档并重新立项。")
            conn.execute(
                "UPDATE research_cycles SET iteration=?, status='进行中', updated_at=? "
                "WHERE cycle_id=?", (next_number, utc_now(), cycle_id),
            )
            self._insert_jobs(conn, cycle_id, next_number)
            self._event(conn, self._cycle(conn, cycle_id), actor,
                        "根据反证意见重启研发", {"rationale": rationale})
        return self.status(cycle_id)

    def verify_audit(self, cycle_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            self._cycle(conn, cycle_id)
            events = conn.execute(
                "SELECT * FROM research_events WHERE cycle_id=? ORDER BY seq", (cycle_id,)
            ).fetchall()
            prev = "0" * 64
            for row in events:
                actual = sha256((prev + row["payload_json"]).encode("utf-8")).hexdigest()
                if row["previous_sha256"] != prev or row["event_sha256"] != actual:
                    return {"cycle_id": cycle_id, "valid": False, "checked_events": len(events)}
                prev = actual
            return {"cycle_id": cycle_id, "valid": bool(events),
                    "checked_events": len(events), "head_sha256": prev}


def register_research_cycle_tools(server: Any, service: Any) -> None:
    """在已有 MCP v2 服务中注册研发循环能力，无第二套模型或队列。"""
    lab = ResearchCycle(service.project)

    @server.tool()
    def patent_cycle_create(case_id: str) -> dict[str, Any]:
        """为当前项目已有案卷建立多 Agent 科研循环和十项可恢复任务。"""
        return lab.create(case_id)

    @server.tool()
    def patent_cycle_status(cycle_id: str) -> dict[str, Any]:
        """查看任务依赖、可领取任务及当前迭代轮次，不暴露内部任务正文。"""
        return lab.status(cycle_id)

    @server.tool()
    def patent_cycle_claim(cycle_id: str, role: str, actor: str,
                           lease_seconds: int = 1800) -> dict[str, Any]:
        """领取已满足依赖的任务；执行身份必须由外部网关校验。"""
        return lab.claim(cycle_id, role, actor, lease_seconds) or {"status": "当前无可领取任务"}

    @server.tool()
    def patent_cycle_finish(task_id: int, actor: str,
                            result: dict[str, Any]) -> dict[str, Any]:
        """提交真实任务记录、检查来源与独立性；不会调用模型或自动递交专利。"""
        return lab.finish(task_id, actor, result)

    @server.tool()
    def patent_cycle_fail(task_id: int, actor: str, reason: str,
                          retryable: bool = True) -> dict[str, Any]:
        """记录失败并按预算重试或进入阻断。"""
        return lab.fail(task_id, actor, reason, retryable=retryable)

    @server.tool()
    def patent_cycle_iterate(cycle_id: str, actor: str,
                             rationale: str) -> dict[str, Any]:
        """独立裁决要求重做时生成下一轮任务，保留旧轮次完整结果。"""
        return lab.iterate(cycle_id, actor, rationale)

    @server.tool()
    def patent_cycle_audit(cycle_id: str) -> dict[str, Any]:
        """检查本循环本地追加事件的 SHA256 链。"""
        return lab.verify_audit(cycle_id)
