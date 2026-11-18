"""项目边界：每项目独立 SQLite、目录与证据，禁止跨项目共享索引。

不把项目编号当成数据库表过滤字段。每个项目使用独立数据库文件，
独立 MCP 进程只绑定一个 project_id；身份认证由生产网关负责。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import sqlite3

from .core import PatentWorkflowError
from .local_workspace import LocalPatentWorkspace

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")


def validate_project_id(project_id: str) -> str:
    if not isinstance(project_id, str) or not _ID.fullmatch(project_id):
        raise PatentWorkflowError("项目 ID 仅允许字母数字、下划线、连字符，最多80字符。")
    return project_id


class ProjectStorage:
    """每个项目独立 :root/projects/<project_id>/patents.sqlite3。"""

    def __init__(self, workspace_root: Path, project_id: str):
        self.project_id = validate_project_id(project_id)
        root = Path(workspace_root).expanduser()
        if root.is_symlink():
            raise PatentWorkflowError("工作区根目录不能为符号链接。")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.workspace_root = root.resolve()
        parent = self.workspace_root / "projects"
        if parent.is_symlink():
            raise PatentWorkflowError("项目目录不能由符号链接替换。")
        parent.mkdir(mode=0o700, exist_ok=True)
        self.root = parent / self.project_id
        if self.root.is_symlink():
            raise PatentWorkflowError("项目数据目录为符号链接，拒绝访问。")
        self.root.mkdir(mode=0o700, exist_ok=True)
        if self.root.resolve().parent != parent.resolve():
            raise PatentWorkflowError("项目存储位置异常。")
        for target in (self.root / "patents.sqlite3", self.root / "patents.sqlite3-wal",
                       self.root / "patents.sqlite3-shm"):
            if target.is_symlink():
                raise PatentWorkflowError("项目数据库文件或 WAL 为符号链接，拒绝访问。")
        self.db_path = self.root / "patents.sqlite3"
        self.workspace = LocalPatentWorkspace(self.db_path)
        self._bind_identity()
        try:
            os.chmod(self.root, 0o700)
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass  # Windows 文件 ACL 需由企业部署层设置。

    def _bind_identity(self) -> None:
        with self.workspace.connect(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS project_identity (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                project_id TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )""")
            row = db.execute("SELECT project_id FROM project_identity WHERE singleton=1").fetchone()
            if row is not None and row["project_id"] != self.project_id:
                raise PatentWorkflowError("数据库的项目身份与 MCP 启动项目不一致。")
            if row is None:
                db.execute("INSERT INTO project_identity VALUES(1, ?, 1, ?)",
                           (self.project_id, datetime.now(timezone.utc).isoformat()))

    def describe(self) -> dict:
        """只返回当前项目，不暴露其他项目名称或数据库路径。"""
        with self.workspace.connect() as db:
            row = db.execute("SELECT project_id, schema_version FROM project_identity").fetchone()
            cases = db.execute("SELECT COUNT(*) AS n FROM cases").fetchone()["n"]
        return {"project_id": row["project_id"], "schema_version": row["schema_version"],
                "case_count": cases, "isolation": "dedicated_sqlite_database",
                "cross_project_access": False}

    def run_dir(self, case_id: str, run_id: str) -> Path:
        return self.root / "cases" / case_id / "runs" / run_id


def migrate_legacy_database(workspace_root: Path, project_id: str,
                            legacy_db: Path, *, approved: bool = False) -> dict:
    """人工显式迁移：SQLite backup，保留旧 DB；禁止自动搬迁或静默共享。"""
    if not approved:
        raise PatentWorkflowError("迁移旧索引必须显式授权，并确认其中数据只属于此项目。")
    source = Path(legacy_db).expanduser().resolve(strict=True)
    if source.is_symlink() or not source.is_file():
        raise PatentWorkflowError("旧数据库必须是普通文件。")
    # 防止意外把跨项目共享旧数据库注入一个项目，应由管理员单独拆分后导入。
    with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as conn:
        projects = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project_identity'"
        )]
        if not projects:
            raise PatentWorkflowError("旧库缺少可确认项目所有权的 project_identity，请先人工拆分。")
        row = conn.execute("SELECT project_id FROM project_identity WHERE singleton=1").fetchone()
        if not row or row[0] != project_id:
            raise PatentWorkflowError("旧库项目身份与迁移目标不符。")
    dest = ProjectStorage(workspace_root, project_id)
    with dest.workspace.connect() as db:
        cases = db.execute("SELECT COUNT(*) AS n FROM cases").fetchone()["n"]
    if cases:
        raise PatentWorkflowError("目标库已有案卷，阻止覆盖；使用受控合并迁移流程。")
    # 当前实现禁止覆盖既有目标数据库；后续补充独立受控 migration 工具。
    raise PatentWorkflowError("历史案卷迁移须有逐案归属、备份及核验；请使用单独迁移工具。")
