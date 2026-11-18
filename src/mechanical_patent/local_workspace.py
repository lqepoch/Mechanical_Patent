"""本地专利资料索引与多角色案卷工作流。

当前 AI (ChatGPT/Codex) 负责每项任务的研究与撰写。这里的数据库仅
持久化任务、原文位置、核验结论、检索批次与交接，不调用模型服务。

本地 SQLite 是可离线运行的工具实现。正式多租户部署使用 PostgreSQL
并通过企业 IAM、RLS 和受控文件存储保障权限。
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterator

from .core import Evidence, PatentWorkflowError, evidence_id, utc_now

# 每条任务在数据库中保存，依赖未完成的任务无法被其他 Agent 抢占。
WORKFLOW_STEPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("保密审批", "保密与权限智能体", ()),
    ("专利检索", "全球专利检索智能体", ("保密审批",)),
    ("论文检索", "学术论文检索智能体", ("保密审批",)),
    ("证据核验", "证据核验智能体", ("专利检索", "论文检索")),
    ("方向评审", "技术方向评审智能体", ("证据核验",)),
    ("多路线创新", "多路线创新智能体", ("方向评审",)),
    ("专利论文反证", "现有技术反证智能体", ("多路线创新",)),
    ("工程论证", "机械工程论证智能体", ("专利论文反证",)),
    ("申请撰写", "中文发明专利撰写智能体", ("工程论证",)),
    ("独立质检", "专利质量复核智能体", ("申请撰写",)),
    ("工程审核", "机械工程师", ("独立质检",)),
    ("专利审核", "专利专业人员", ("工程审核",)),
)
STEPS = {name: {"role": role, "depends_on": deps} for name, role, deps in WORKFLOW_STEPS}
STATUS = frozenset({"待领取", "运行中", "已完成", "失败", "已阻断"})
REVIEW_STATUS = frozenset({"待核验", "已核验", "已驳回"})
DOC_KINDS = frozenset({"patent", "paper"})
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _date(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _token(value: str, *, field: str, maximum: int = 160) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise PatentWorkflowError(f"{field} 不能为空，长度不得超过 {maximum}。")
    return value.strip()


class LocalPatentWorkspace:
    """本地索引：单写入者事务、任务租约与可恢复多轮次案卷。"""

    def __init__(self, index_path: Path):
        self.path = Path(index_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.path), timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 15000")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.execute("COMMIT")
        except Exception:
            if write and conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def _init(self) -> None:
        # SQLite executescript() performs implicit transaction management.
        # Run schema installation outside the write transaction, then use
        # BEGIN IMMEDIATE for every ordinary state mutation.
        with self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cases (
                  case_id TEXT PRIMARY KEY, direction TEXT NOT NULL,
                  revision INTEGER NOT NULL DEFAULT 1,
                  status TEXT NOT NULL DEFAULT '研究中',
                  confidentiality TEXT NOT NULL DEFAULT '秘密',
                  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
                  revision INTEGER NOT NULL, step TEXT NOT NULL,
                  required_role TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT '待领取',
                  assigned_to TEXT, lease_expires TEXT,
                  attempts INTEGER NOT NULL DEFAULT 0,
                  result_json TEXT, created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(case_id, revision, step)
                );
                CREATE TABLE IF NOT EXISTS task_dependencies (
                  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                  prerequisite_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                  PRIMARY KEY(task_id, prerequisite_id)
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_status
                  ON tasks(case_id, revision, status, step);
                CREATE TABLE IF NOT EXISTS documents (
                  case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
                  doc_id TEXT NOT NULL, kind TEXT NOT NULL,
                  publication TEXT NOT NULL, title TEXT NOT NULL,
                  abstract TEXT NOT NULL DEFAULT '',
                  source TEXT NOT NULL, source_url TEXT NOT NULL,
                  public_pdf_url TEXT NOT NULL DEFAULT '',
                  publication_date TEXT NOT NULL DEFAULT '',
                  jurisdiction TEXT NOT NULL DEFAULT '',
                  metadata_verified INTEGER NOT NULL DEFAULT 0,
                  verification_status TEXT NOT NULL DEFAULT '待核验',
                  verification_note TEXT NOT NULL DEFAULT '',
                  verified_by TEXT NOT NULL DEFAULT '',
                  verified_at TEXT,
                  local_pdf_path TEXT NOT NULL DEFAULT '',
                  pdf_sha256 TEXT NOT NULL DEFAULT '',
                  indexed_at TEXT NOT NULL,
                  PRIMARY KEY(case_id, doc_id)
                );
                CREATE INDEX IF NOT EXISTS idx_documents_publication
                  ON documents(publication);
                CREATE INDEX IF NOT EXISTS idx_documents_title
                  ON documents(title);
                CREATE INDEX IF NOT EXISTS idx_documents_review
                  ON documents(case_id, kind, verification_status);
                CREATE TABLE IF NOT EXISTS direction_decisions (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  case_id TEXT NOT NULL REFERENCES cases(case_id),
                  revision INTEGER NOT NULL, decision TEXT NOT NULL,
                  rationale TEXT NOT NULL, evidence_ids_json TEXT NOT NULL,
                  reviewed_by TEXT NOT NULL, created_at TEXT NOT NULL,
                  UNIQUE(case_id, revision)
                );
                CREATE TABLE IF NOT EXISTS task_log (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  case_id TEXT NOT NULL,
                  revision INTEGER NOT NULL,
                  step TEXT NOT NULL,
                  actor TEXT NOT NULL,
                  event TEXT NOT NULL,
                  payload_json TEXT NOT NULL DEFAULT '{}',
                  recorded_at TEXT NOT NULL
                );
            """)

    def create_case(self, case_id: str, direction: str, *, confidentiality: str = "秘密") -> dict[str, Any]:
        case_id = _token(case_id, field="案卷编号", maximum=120)
        direction = _token(direction, field="技术方向", maximum=4000)
        if confidentiality not in {"公开", "内部", "秘密", "受控"}:
            raise PatentWorkflowError("非法的保密级别。")
        now = utc_now()
        with self.connect(write=True) as db:
            db.execute(
                "INSERT INTO cases(case_id,direction,confidentiality,created_at,updated_at) VALUES(?,?,?,?,?)",
                (case_id, direction, confidentiality, now, now),
            )
            self._insert_round(db, case_id, 1)
            self._log(db, case_id, 1, "任务接收", "系统", "创建案卷", {"confidentiality": confidentiality})
        return self.status(case_id)

    @staticmethod
    def _log(db: sqlite3.Connection, case_id: str, revision: int, step: str,
             actor: str, event: str, payload: dict[str, Any]) -> None:
        db.execute(
            "INSERT INTO task_log(case_id,revision,step,actor,event,payload_json,recorded_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (case_id, revision, step, actor, event, _json(payload), utc_now()),
        )

    @staticmethod
    def _insert_round(db: sqlite3.Connection, case_id: str, revision: int) -> None:
        now = utc_now()
        ids = {}
        for step, role, _ in WORKFLOW_STEPS:
            cursor = db.execute(
                "INSERT INTO tasks(case_id,revision,step,required_role,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (case_id, revision, step, role, now, now),
            )
            ids[step] = int(cursor.lastrowid)
        for step, _, deps in WORKFLOW_STEPS:
            for dep in deps:
                db.execute(
                    "INSERT INTO task_dependencies(task_id, prerequisite_id) VALUES (?,?)",
                    (ids[step], ids[dep]),
                )

    def status(self, case_id: str) -> dict[str, Any]:
        with self.connect() as db:
            case = db.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
            if case is None:
                raise PatentWorkflowError("案卷不存在。")
            tasks = db.execute(
                "SELECT id,step,required_role,status,assigned_to,lease_expires,attempts "
                "FROM tasks WHERE case_id=? AND revision=? ORDER BY id",
                (case_id, case["revision"]),
            ).fetchall()
            totals = db.execute(
                "SELECT kind,verification_status,COUNT(*) AS total FROM documents "
                "WHERE case_id=? GROUP BY kind,verification_status", (case_id,),
            ).fetchall()
            return {
                "case_id": case_id, "direction": case["direction"],
                "revision": case["revision"], "status": case["status"],
                "confidentiality": case["confidentiality"],
                "tasks": [dict(r) for r in tasks],
                "source_reviews": [dict(r) for r in totals],
            }

    def claim(self, case_id: str, *, role: str, actor: str,
              lease_seconds: int = 1800) -> dict[str, Any] | None:
        role = _token(role, field="智能体角色")
        actor = _token(actor, field="执行人")
        if not 60 <= lease_seconds <= 7200:
            raise PatentWorkflowError("任务租约须为 60 至 7200 秒。")
        now = utc_now()
        until = (_utc() + timedelta(seconds=lease_seconds)).isoformat(timespec="seconds")
        with self.connect(write=True) as db:
            case = db.execute("SELECT revision,status FROM cases WHERE case_id=?", (case_id,)).fetchone()
            if case is None:
                raise PatentWorkflowError("案卷不存在。")
            if case["status"] != "研究中":
                raise PatentWorkflowError("案卷已调整方向或终止，当前轮次暂停领取任务。")
            revision = int(case["revision"])
            db.execute(
                "UPDATE tasks SET status='待领取',assigned_to=NULL,lease_expires=NULL, "
                "updated_at=? WHERE case_id=? AND revision=? AND status='运行中' "
                "AND lease_expires < ? AND attempts < 3",
                (now, case_id, revision, now),
            )
            db.execute(
                "UPDATE tasks SET status='已阻断', updated_at=? "
                "WHERE case_id=? AND revision=? AND status='运行中' "
                "AND lease_expires < ? AND attempts >= 3",
                (now, case_id, revision, now),
            )
            row = db.execute(
                "SELECT t.* FROM tasks t "
                "WHERE t.case_id=? AND t.revision=? AND t.status='待领取' "
                "AND t.required_role=? AND NOT EXISTS ("
                " SELECT 1 FROM task_dependencies d JOIN tasks previous "
                " ON previous.id=d.prerequisite_id "
                " WHERE d.task_id=t.id AND previous.status!='已完成') "
                "ORDER BY t.id LIMIT 1",
                (case_id, revision, role),
            ).fetchone()
            if row is None:
                return None
            db.execute(
                "UPDATE tasks SET status='运行中',assigned_to=?,lease_expires=?, "
                "attempts=attempts+1, updated_at=? WHERE id=?",
                (actor, until, now, row["id"]),
            )
            self._log(db, case_id, revision, row["step"], actor, "领取任务",
                      {"task_id": row["id"], "lease_expires": until})
            return {
                "task_id": int(row["id"]), "case_id": case_id, "revision": revision,
                "step": row["step"], "role": role, "actor": actor, "lease_expires": until,
            }

    def finish(self, task_id: int, *, actor: str, result: dict[str, Any]) -> dict[str, Any]:
        actor = _token(actor, field="执行人")
        if not isinstance(result, dict):
            raise PatentWorkflowError("任务结果须为 JSON 对象。")
        now = utc_now()
        with self.connect(write=True) as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None or row["status"] != "运行中" or row["assigned_to"] != actor:
                raise PatentWorkflowError("任务不存在、尚未领取或执行人与租约不匹配。")
            case_record = db.execute(
                "SELECT revision,status FROM cases WHERE case_id=?", (row["case_id"],)
            ).fetchone()
            if case_record is None or case_record["status"] != "研究中" or int(case_record["revision"]) != int(row["revision"]):
                raise PatentWorkflowError("案卷当前轮次已改变，无法提交旧任务结果。")
            if row["lease_expires"] and _date(row["lease_expires"]) < _utc():
                raise PatentWorkflowError("任务租约已过期，请重新领取。")
            case_id = row["case_id"]
            step = row["step"]
            revision = int(row["revision"])
            if step == "保密审批" and result.get("outbound_approved") not in {True, False}:
                raise PatentWorkflowError("保密审批必须明确是否允许技术检索词外发。")
            if step == "证据核验":
                pending = db.execute(
                    "SELECT COUNT(*) FROM documents WHERE case_id=? "
                    "AND verification_status='待核验'", (case_id,),
                ).fetchone()[0]
                if pending:
                    raise PatentWorkflowError(f"仍有 {pending} 篇文献未独立核验，不能完成证据核验阶段。")
                sources = {
                    row["kind"]: row["total"]
                    for row in db.execute(
                        "SELECT kind,COUNT(*) AS total FROM documents WHERE case_id=? "
                        "AND verification_status='已核验' GROUP BY kind", (case_id,)
                    ).fetchall()
                }
                if (not sources.get("patent") or not sources.get("paper")) and not result.get("gap_waiver"):
                    raise PatentWorkflowError(
                        "专利与论文双源核验证据不足；必须补齐数据或记录具体缺口例外。"
                    )
                if not result.get("coverage_report"):
                    raise PatentWorkflowError("缺少检索覆盖范围、失败数据源与文献缺口说明。")
                if result.get("gap_waiver") and not str(result.get("gap_rationale", "")).strip():
                    raise PatentWorkflowError("双源检索缺口例外必须有明确理由。")
            if step == "方向评审":
                self._direction_gate(db, case_id, revision, actor, result)
            if step == "工程审核" and not result.get("engineering_review"):
                raise PatentWorkflowError("真实工程审核记录不能为空。")
            if step == "专利审核" and not result.get("patent_review"):
                raise PatentWorkflowError("真实专利专业审核记录不能为空。")
            db.execute(
                "UPDATE tasks SET status='已完成', result_json=?, lease_expires=NULL, updated_at=? "
                "WHERE id=?", (_json(result), now, task_id),
            )
            self._log(db, case_id, revision, step, actor, "完成任务",
                      {"task_id": task_id, "summary": str(result.get("summary", ""))[:200]})
            return {"task_id": task_id, "step": step, "status": "已完成", "case_id": case_id}

    def _direction_gate(self, db: sqlite3.Connection, case_id: str,
                        revision: int, actor: str, data: dict[str, Any]) -> None:
        decision = data.get("decision")
        rationale = data.get("rationale")
        ids = data.get("evidence_ids")
        if decision not in {"继续", "改换方向", "终止"}:
            raise PatentWorkflowError("方向评审需要明确继续、改换方向或终止。")
        if not isinstance(rationale, str) or len(rationale.strip()) < 10:
            raise PatentWorkflowError("技术方向结论必须有至少十个字的理由。")
        if not isinstance(ids, list):
            raise PatentWorkflowError("方向评审需明确所依据的文献编号列表。")
        if decision == "继续" and not ids and not data.get("gap_waiver"):
            raise PatentWorkflowError("继续研发需要已核验文献，或说明真实缺口并标记 gap_waiver。")
        if ids:
            placeholders = ",".join("?" for _ in ids)
            rows = db.execute(
                "SELECT doc_id FROM documents WHERE case_id=? "
                f"AND verification_status='已核验' AND doc_id IN ({placeholders})",
                (case_id, *ids),
            ).fetchall()
            if len(ids) != len(set(ids)) or len(rows) != len(set(ids)):
                raise PatentWorkflowError("方向依据存在重复、未入库或未完成核验的文献编号。")
        db.execute(
            "INSERT INTO direction_decisions(case_id,revision,decision,rationale,evidence_ids_json,reviewed_by,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (case_id, revision, decision, rationale, _json(ids), actor, utc_now()),
        )
        if decision != "继续":
            db.execute(
                "UPDATE cases SET status=?, updated_at=? WHERE case_id=?",
                ("方向调整中" if decision == "改换方向" else "已终止", utc_now(), case_id),
            )

    def next_revision(self, case_id: str, *, actor: str, new_direction: str,
                      rationale: str) -> int:
        actor = _token(actor, field="执行人")
        direction = _token(new_direction, field="修订后技术方向", maximum=4000)
        if len(rationale.strip()) < 10:
            raise PatentWorkflowError("方向调整须记录充分的理由。")
        with self.connect(write=True) as db:
            case = db.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
            if case is None:
                raise PatentWorkflowError("案卷不存在。")
            decision = db.execute(
                "SELECT decision FROM direction_decisions WHERE case_id=? AND revision=?",
                (case_id, case["revision"]),
            ).fetchone()
            if decision is None or decision["decision"] != "改换方向":
                raise PatentWorkflowError("上一轮必须经过方向评审并判定改换方向。")
            revision = int(case["revision"]) + 1
            db.execute(
                "UPDATE cases SET revision=?, direction=?,status='研究中',updated_at=? WHERE case_id=?",
                (revision, direction, utc_now(), case_id),
            )
            self._insert_round(db, case_id, revision)
            self._log(db, case_id, revision, "方向评审", actor, "启动新的研发轮次",
                      {"rationale": rationale, "previous_revision": revision - 1})
            return revision

    def upsert_document(self, case_id: str, document: Evidence, *,
                        public_pdf_url: str = "") -> str:
        if document.kind not in DOC_KINDS:
            raise PatentWorkflowError("本地索引只存放正式专利或学术论文元数据。")
        doc_id = evidence_id(document)
        with self.connect(write=True) as db:
            if not db.execute("SELECT 1 FROM cases WHERE case_id=?", (case_id,)).fetchone():
                raise PatentWorkflowError("请先创建案卷。")
            existing = db.execute(
                "SELECT verification_status, public_pdf_url FROM documents "
                "WHERE case_id=? AND doc_id=?", (case_id, doc_id),
            ).fetchone()
            # 检索新版本不应隐式推翻已人工核验的结论或删除本地 PDF。
            pdf = public_pdf_url or (existing["public_pdf_url"] if existing else "")
            db.execute(
                "INSERT INTO documents(case_id,doc_id,kind,publication,title,abstract,"
                "source,source_url,public_pdf_url,publication_date,jurisdiction,metadata_verified,indexed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(case_id,doc_id) DO UPDATE SET "
                "title=excluded.title,abstract=excluded.abstract,source=excluded.source,"
                "source_url=excluded.source_url,public_pdf_url=excluded.public_pdf_url,"
                "publication_date=excluded.publication_date,jurisdiction=excluded.jurisdiction,"
                "metadata_verified=excluded.metadata_verified,indexed_at=excluded.indexed_at",
                (case_id, doc_id, document.kind, document.publication, document.title,
                 document.abstract[:12000], document.source, document.url, pdf,
                 document.publication_date, document.jurisdiction,
                 int(document.verified), utc_now()),
            )
        return doc_id

    def import_case(self, case_dir: Path) -> dict[str, Any]:
        """索引已有案卷 JSON；不因此认定文献内容真实。"""
        folder = Path(case_dir)
        intake = json.loads((folder / "00_intake.json").read_text(encoding="utf-8"))
        case_id = str(intake.get("case_id") or folder.name)
        with self.connect() as db:
            exists = db.execute("SELECT 1 FROM cases WHERE case_id=?", (case_id,)).fetchone()
        if exists is None:
            self.create_case(case_id, str(intake["direction"]))
        counts = {"patent": 0, "paper": 0}
        for name, kind in (("02_patents.json", "patent"), ("03_papers.json", "paper")):
            file = folder / name
            if not file.is_file():
                continue
            rows = json.loads(file.read_text(encoding="utf-8")).get("records", [])
            for raw in rows:
                # Case artifacts can be edited externally and are not an
                # authenticated database response; import as unverified data.
                record = Evidence.from_dict(raw, imported=True)
                if record.kind == kind:
                    self.upsert_document(case_id, record)
                    counts[kind] += 1
        return {"case_id": case_id, "indexed": counts, "database": str(self.path)}

    def review_document(self, case_id: str, doc_id: str, *, actor: str,
                        accepted: bool, rationale: str,
                        public_pdf_url: str | None = None) -> dict[str, Any]:
        actor = _token(actor, field="核验人")
        if len(rationale.strip()) < 8:
            raise PatentWorkflowError("原始文献核验必须填写具体证据或疑点。")
        with self.connect(write=True) as db:
            row = db.execute(
                "SELECT * FROM documents WHERE case_id=? AND doc_id=?", (case_id, doc_id)
            ).fetchone()
            if row is None:
                raise PatentWorkflowError("不存在该案卷的文献记录。")
            # Provider-verified metadata and a human source review are separate states.
            # A reviewer may independently verify an imported record against the original
            # public page/PDF; this must never quietly upgrade metadata_verified.
            if accepted and not (row["source_url"] or public_pdf_url):
                raise PatentWorkflowError("缺少可打开的原始文献来源，无法核验。")
            pdf = row["public_pdf_url"]
            if public_pdf_url is not None:
                from urllib.parse import urlsplit
                parts = urlsplit(public_pdf_url)
                if public_pdf_url and (parts.scheme != "https" or not parts.hostname):
                    raise PatentWorkflowError("PDF 原始链接须为真实 HTTPS 地址。")
                pdf = public_pdf_url
            status = "已核验" if accepted else "已驳回"
            db.execute(
                "UPDATE documents SET verification_status=?,verification_note=?,"
                "verified_by=?,verified_at=?,public_pdf_url=? WHERE case_id=? AND doc_id=?",
                (status, rationale, actor, utc_now(), pdf, case_id, doc_id),
            )
            revision = db.execute(
                "SELECT revision FROM cases WHERE case_id=?", (case_id,)
            ).fetchone()["revision"]
            self._log(db, case_id, revision, "证据核验", actor, "审阅原始文献",
                      {"doc_id": doc_id, "status": status, "rationale": rationale[:200]})
            return {"doc_id": doc_id, "verification_status": status, "pdf_url": pdf}

    def search_documents(self, query: str, *, case_id: str | None = None,
                         limit: int = 30) -> list[dict[str, Any]]:
        """中文/英文简单元数据索引；语义向量检索另由 PostgreSQL 项目实现。"""
        if not isinstance(query, str) or not query.strip():
            raise PatentWorkflowError("检索词不能为空。")
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = "%" + escaped + "%"
        sql = (
            "SELECT case_id,doc_id,kind,publication,title,source,source_url,"
            "public_pdf_url,publication_date,verification_status,"
            "local_pdf_path,pdf_sha256 FROM documents "
            "WHERE (title LIKE ? ESCAPE '\\' OR publication LIKE ? ESCAPE '\\' "
            "OR abstract LIKE ? ESCAPE '\\')"
        )
        params: list[Any] = [like, like, like]
        if case_id:
            sql += " AND case_id=?"
            params.append(case_id)
        sql += " ORDER BY indexed_at DESC, publication LIMIT ?"
        params.append(max(1, min(int(limit), 200)))
        with self.connect() as db:
            return [dict(x) for x in db.execute(sql, params).fetchall()]

    def pdf_source(self, case_id: str, doc_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT case_id,doc_id,kind,publication,title,source_url,"
                "public_pdf_url,local_pdf_path,pdf_sha256,verification_status "
                "FROM documents WHERE case_id=? AND doc_id=?", (case_id, doc_id),
            ).fetchone()
            if row is None:
                raise PatentWorkflowError("索引中没有指定专利。")
            return dict(row)

    def link_local_pdf(self, case_id: str, doc_id: str, *,
                       local_path: Path, digest: str, public_url: str) -> None:
        path = Path(local_path).resolve()
        if not path.is_file() or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise PatentWorkflowError("PDF 文件或 SHA256 无效。")
        with self.connect(write=True) as db:
            row = db.execute(
                "SELECT kind FROM documents WHERE case_id=? AND doc_id=?", (case_id, doc_id),
            ).fetchone()
            if row is None or row["kind"] != "patent":
                raise PatentWorkflowError("只能将专利 PDF 关联到真实专利索引条目。")
            db.execute(
                "UPDATE documents SET local_pdf_path=?,pdf_sha256=?,public_pdf_url=? "
                "WHERE case_id=? AND doc_id=?",
                (str(path), digest, public_url, case_id, doc_id),
            )
            revision = db.execute(
                "SELECT revision FROM cases WHERE case_id=?", (case_id,),
            ).fetchone()["revision"]
            self._log(db, case_id, revision, "专利检索", "系统", "归档公开专利PDF",
                      {"doc_id": doc_id, "sha256": digest, "path": str(path)})

    def list_tasks(self, case_id: str) -> list[dict[str, Any]]:
        return self.status(case_id)["tasks"]
