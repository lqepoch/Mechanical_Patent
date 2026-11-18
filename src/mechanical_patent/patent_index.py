"""项目内最新专利索引：上游实时请求、快照变化、失败与数据时效记录。

此处的“最新”表示本轮实际访问供应商，不能证明全球申请全部公开。
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Callable

from .core import Evidence, PatentWorkflowError, evidence_id, utc_now
from .local_workspace import LocalPatentWorkspace


def _digest(e: Evidence) -> str:
    fields = {k: v for k, v in e.to_dict().items() if k not in {"retrieved_at", "verified"}}
    return sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class PatentIndex:
    """每个 ProjectStorage 绑定的数据库内，按案卷保存变化与查询历史。"""

    def __init__(self, workspace: LocalPatentWorkspace):
        self.workspace = workspace
        with self.workspace.connect() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS patent_index_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL REFERENCES cases(case_id),
                query TEXT NOT NULL, provider TEXT NOT NULL,
                checked_at TEXT NOT NULL, status TEXT NOT NULL,
                result_count INTEGER NOT NULL, new_count INTEGER NOT NULL,
                changed_count INTEGER NOT NULL, error TEXT NOT NULL DEFAULT ''
              );
              CREATE INDEX IF NOT EXISTS idx_patent_checks
                ON patent_index_checks(case_id,id DESC);
              CREATE TABLE IF NOT EXISTS patent_index_current (
                case_id TEXT NOT NULL REFERENCES cases(case_id),
                evidence_id TEXT NOT NULL, publication TEXT NOT NULL,
                payload TEXT NOT NULL, content_hash TEXT NOT NULL,
                publication_date TEXT NOT NULL, source TEXT NOT NULL,
                first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
                PRIMARY KEY(case_id,evidence_id)
              );
              CREATE TABLE IF NOT EXISTS patent_index_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
                check_id INTEGER NOT NULL REFERENCES patent_index_checks(id),
                observed_at TEXT NOT NULL, payload TEXT NOT NULL,
                content_hash TEXT NOT NULL
              );
              CREATE INDEX IF NOT EXISTS idx_patent_history
                ON patent_index_versions(case_id,evidence_id,id DESC);
            """)

    def refresh(self, case_id: str, query: str, provider: str,
                fetch: Callable[[str, int], list[Evidence]], limit: int = 20) -> dict:
        self.workspace.status(case_id)
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200:
            raise PatentWorkflowError("专利检索词须为1至200字符。")
        if not isinstance(provider, str) or not 1 <= len(provider) <= 60:
            raise PatentWorkflowError("缺少数据源标识。")
        if not 1 <= limit <= 25:
            raise PatentWorkflowError("单次仅允许检索1至25件。")
        query = query.strip()
        timestamp = utc_now()
        try:
            rows = fetch(query, limit)
            if not isinstance(rows, list) or len(rows) > limit:
                raise PatentWorkflowError("供应商返回的专利记录数量或类型错误。")
            if any(not isinstance(e, Evidence) or e.kind != "patent" or not e.verified
                   for e in rows):
                raise PatentWorkflowError("含未经核验的文献，禁止标记为实时官方检索结果。")
        except Exception as exc:
            with self.workspace.connect(write=True) as db:
                db.execute("""INSERT INTO patent_index_checks
                    (case_id,query,provider,checked_at,status,result_count,new_count,changed_count,error)
                    VALUES(?,?,?,?,'failed',0,0,0,?)""",
                    (case_id,query,provider,timestamp,str(exc)[:500]))
            raise PatentWorkflowError("上游查询失败，历史索引保留、刷新失败已记账。") from exc

        new = changed = 0
        with self.workspace.connect(write=True) as db:
            cursor = db.execute("""INSERT INTO patent_index_checks
                (case_id,query,provider,checked_at,status,result_count,new_count,changed_count)
                VALUES(?,?,?,?,'success',?,0,0)""",
                (case_id,query,provider,timestamp,len(rows)))
            check_id = cursor.lastrowid
            for e in rows:
                identifier = evidence_id(e)
                digest = _digest(e)
                old = db.execute("""SELECT content_hash FROM patent_index_current
                    WHERE case_id=? AND evidence_id=?""",(case_id,identifier)).fetchone()
                payload = json.dumps(e.to_dict(),ensure_ascii=False,sort_keys=True)
                if old is None:
                    new += 1
                elif old["content_hash"] != digest:
                    changed += 1
                if old is None or old["content_hash"] != digest:
                    db.execute("""INSERT INTO patent_index_versions
                        (case_id,evidence_id,check_id,observed_at,payload,content_hash)
                        VALUES(?,?,?,?,?,?)""",
                        (case_id,identifier,check_id,timestamp,payload,digest))
                db.execute("""INSERT INTO patent_index_current
                    (case_id,evidence_id,publication,payload,content_hash,publication_date,
                     source,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(case_id,evidence_id) DO UPDATE SET
                    publication=excluded.publication, payload=excluded.payload,
                    content_hash=excluded.content_hash, publication_date=excluded.publication_date,
                    source=excluded.source, last_seen=excluded.last_seen""",
                    (case_id,identifier,e.publication,payload,digest,e.publication_date,
                     e.source,timestamp,timestamp))
            db.execute("""UPDATE patent_index_checks SET new_count=?,changed_count=? WHERE id=?""",
                       (new,changed,check_id))
        return {"case_id":case_id,"provider":provider,"query":query,"checked_at":timestamp,
                "returned":len(rows),"new":new,"changed":changed,
                "status":"provider_queried", "global_completeness":False,
                "warning":"检索限于本数据源/查询词；专利公开及供应商采集存在延迟。"}

    def search(self, case_id: str, term: str = "", limit: int = 40,
               max_age_hours: int = 6) -> dict:
        self.workspace.status(case_id)
        if not isinstance(term, str) or len(term) > 180 or not 1 <= limit <= 100:
            raise PatentWorkflowError("检索词或条数越界。")
        if not 1 <= max_age_hours <= 168:
            raise PatentWorkflowError("时效阈值应为1至168小时。")
        token = term.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")
        with self.workspace.connect() as db:
            docs = db.execute("""SELECT payload,first_seen,last_seen FROM patent_index_current
                WHERE case_id=? AND (publication LIKE ? ESCAPE '\' OR payload LIKE ? ESCAPE '\')
                ORDER BY last_seen DESC LIMIT ?""",
                (case_id,"%"+token+"%","%"+token+"%",limit)).fetchall()
            check = db.execute("""SELECT query,provider,checked_at,status,error FROM patent_index_checks
                WHERE case_id=? ORDER BY id DESC LIMIT 1""",(case_id,)).fetchone()
        elapsed = None
        if check:
            elapsed = (datetime.now(timezone.utc)-datetime.fromisoformat(check["checked_at"])).total_seconds()/3600
        recent = bool(check and check["status"]=="success" and elapsed is not None
                      and elapsed <= max_age_hours)
        return {"case_id":case_id,"records":[{"source":json.loads(r["payload"]),
                "first_seen":r["first_seen"],"last_seen":r["last_seen"]} for r in docs],
                "count":len(docs),"last_check":dict(check) if check else None,
                "freshness":"recent_provider_check" if recent else "stale_or_unchecked",
                "global_completeness":False}

    def history(self, case_id: str, publication: str, limit: int = 20) -> list[dict]:
        self.workspace.status(case_id)
        if not isinstance(publication,str) or not 1 <= len(publication) <= 50 or not 1 <= limit <= 100:
            raise PatentWorkflowError("公开号或历史数量无效。")
        with self.workspace.connect() as db:
            rows = db.execute("""SELECT v.observed_at,v.content_hash,v.payload,c.provider
                FROM patent_index_versions v
                JOIN patent_index_checks c ON c.id=v.check_id
                JOIN patent_index_current d ON d.case_id=v.case_id AND d.evidence_id=v.evidence_id
                WHERE v.case_id=? AND d.publication=?
                ORDER BY v.id DESC LIMIT ?""",(case_id,publication,limit)).fetchall()
        return [{"observed_at":r["observed_at"],"hash":r["content_hash"],
                 "provider":r["provider"],"record":json.loads(r["payload"])} for r in rows]
