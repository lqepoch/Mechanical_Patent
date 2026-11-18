"""Public-only engineering problem source catalog and evidence-first discovery loop.

A shared catalog contains *public* source metadata and hypotheses. Project cases,
confidential drawings, research queries and filing approvals stay in project SQLite.
No AI/LLM API is needed. Source promotion is deliberately absent from MCP.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html import unescape
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
from typing import Any, Callable, Iterator
from urllib import error, parse, request
import xml.etree.ElementTree as ET

from .core import PatentWorkflowError

_ROOT = Path(__file__).resolve().parent / "data"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,79}\Z")
_HTML = re.compile(r"<[^>]+>")
_KEYWORDS = ("消防", "救援", "应急", "灭火", "泡沫", "水泵", "fluid", "pump",
             "robot", "rescue", "aeronautic", "mechanical", "firefighting",
             "fluid", "hydraulic", "thermal", "safety", "emergency", "materials")
_ALLOWED_STAGES = {"hypothesis_only", "triage_pending", "research_pending", "human_reviewed"}
_MAX_RESPONSE = 1_000_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _utc_date(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except (TypeError, ValueError):
        raise PatentWorkflowError("日期必须为 ISO 8601 格式。")


def _url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise PatentWorkflowError("网址超长或类型无效。")
    parts = parse.urlsplit(value.strip())
    if parts.scheme.lower() != "https" or not parts.hostname or parts.username or parts.password:
        raise PatentWorkflowError("仅接受没有用户凭证的 HTTPS 公网网址。")
    if parts.port not in (None, 443):
        raise PatentWorkflowError("禁止自定义网络端口。")
    host = parts.hostname.lower().rstrip(".")
    if (not re.fullmatch(r"[a-z0-9.-]+", host) or "." not in host or
            ".." in host or host.endswith((".local", ".internal", ".localhost"))):
        raise PatentWorkflowError("不允许内网主机名或异常域名。")
    try:
        ipaddress.ip_address(host)
        raise PatentWorkflowError("禁止将 IP 地址当作外部公共研究来源。")
    except ValueError:
        pass
    query = parse.urlencode(sorted((k, v) for k, v in parse.parse_qsl(
        parts.query, keep_blank_values=True) if not k.lower().startswith("utm_")
        and k.lower() not in {"fbclid", "gclid"}))
    path = parts.path.rstrip("/") or "/"
    return parse.urlunsplit(("https", host, path, query, ""))


def _host(value: str) -> str:
    return parse.urlsplit(value).hostname or ""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _strip_html(value: str) -> str:
    return unescape(_HTML.sub(" ", value or "")).strip()[:1800]


def _published(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return _utc_date(value)


def _safe_fetch(source: dict[str, Any]) -> dict[str, Any]:
    """Conservative RSS GET; operator-approved URL only; no redirects, no private DNS."""
    url = _url(source["feed_url"])
    host = _host(url)
    allowed = _host(source["url"])
    # Only the established registered website or its owned subdomains.
    if not (host == allowed or host.endswith("." + allowed)):
        raise PatentWorkflowError("RSS 来源域名不属于已批准的平台。")
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise PatentWorkflowError("DNS 结果包含非全球可路由地址。")
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            raise PatentWorkflowError("RSS 访问发生重定向；需要人工重审目的地。")
    opener = request.build_opener(NoRedirect)
    headers = {"User-Agent": "MechanicalPatentProblemRadar/1.0 (public metadata)",
               "Accept": "application/atom+xml,application/rss+xml,application/xml,text/xml"}
    if source.get("etag"):
        headers["If-None-Match"] = source["etag"]
    if source.get("last_modified"):
        headers["If-Modified-Since"] = source["last_modified"]
    req = request.Request(url, headers=headers)
    try:
        with opener.open(req, timeout=12) as resp:
            if resp.status != 200:
                raise PatentWorkflowError("RSS HTTP 状态异常。")
            data = resp.read(_MAX_RESPONSE + 1)
            if len(data) > _MAX_RESPONSE:
                raise PatentWorkflowError("RSS 响应超出1MB上限。")
            return {"status": 200, "data": data, "etag": resp.headers.get("ETag", "")[:180],
                    "last_modified": resp.headers.get("Last-Modified", "")[:180]}
    except error.HTTPError as exc:
        if exc.code == 304:
            return {"status": 304, "data": b""}
        raise PatentWorkflowError(f"RSS HTTP {exc.code}，本轮保留原记录。") from exc


def _feed_entries(data: bytes) -> list[dict[str, str]]:
    if len(data) > _MAX_RESPONSE or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise PatentWorkflowError("RSS/Atom XML 不安全或超限。")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise PatentWorkflowError("RSS/Atom XML 解析失败。") from exc
    tag = root.tag.lower()
    items: list[dict[str, str]] = []
    if tag.endswith("rss") or tag.endswith("rdf"):
        nodes = root.findall(".//item")
        for node in nodes[:50]:
            def value(name: str) -> str:
                return (node.findtext(name) or "").strip()
            items.append({"title": value("title"), "url": value("link"),
                          "summary": _strip_html(value("description")),
                          "published_at": _published(value("pubDate"))})
    elif tag.endswith("feed"):
        ns = "{http://www.w3.org/2005/Atom}"
        for node in root.findall(ns + "entry")[:50]:
            link = next((x.get("href", "") for x in node.findall(ns + "link")
                         if x.get("rel", "alternate") == "alternate"), "")
            items.append({"title": node.findtext(ns + "title", default="").strip(),
                          "url": link, "summary": _strip_html(node.findtext(ns + "summary", default="")),
                          "published_at": _published(node.findtext(ns + "published", default="") or
                                                    node.findtext(ns + "updated", default=""))})
    else:
        raise PatentWorkflowError("仅接受 RSS 或 Atom，不支持普通 HTML 自动解析。")
    return [i for i in items if i["title"] and i["url"]]


class ProblemSourceRegistry:
    """Shared PUBLIC-source catalog, isolated from ProjectStorage databases."""

    def __init__(self, workspace_root: Path, *, seed_dir: Path | None = None):
        workspace_root = Path(workspace_root).expanduser()
        if workspace_root.is_symlink():
            raise PatentWorkflowError("公共平台库工作空间不能由符号链接替换。")
        workspace_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = workspace_root.resolve() / "public_source_catalog"
        if self.root.is_symlink():
            raise PatentWorkflowError("公共平台库目录不能为符号链接。")
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.path = self.root / "sources.sqlite3"
        for x in (self.path, self.root / "sources.sqlite3-wal", self.root / "sources.sqlite3-shm"):
            if x.is_symlink():
                raise PatentWorkflowError("公共平台库数据库路径不可为符号链接。")
        self.seed_dir = Path(seed_dir or _ROOT)
        self._initialize()
        self.seed()
        try:
            os.chmod(self.root, 0o700)
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    @contextmanager
    def connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(str(self.path), timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.execute("COMMIT")
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def _initialize(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
              CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL, region TEXT NOT NULL, mode TEXT NOT NULL,
                feed_url TEXT NOT NULL DEFAULT '', cadence_hours INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('approved','pending','rejected','disabled')),
                rights TEXT NOT NULL DEFAULT 'unknown', provenance TEXT NOT NULL,
                reviewer TEXT NOT NULL DEFAULT '', reviewed_at TEXT NOT NULL DEFAULT '',
                etag TEXT NOT NULL DEFAULT '', last_modified TEXT NOT NULL DEFAULT '',
                last_checked TEXT NOT NULL DEFAULT '', next_due TEXT NOT NULL DEFAULT '',
                lease_until TEXT NOT NULL DEFAULT '', errors INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
              );
              CREATE INDEX IF NOT EXISTS idx_source_due ON sources(status,mode,next_due);
              CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
                url TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL,
                published_at TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
                sha256 TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'triage_pending', relevant INTEGER NOT NULL DEFAULT 0,
                UNIQUE(source_id,url)
              );
              CREATE TABLE IF NOT EXISTS observation_revisions (
                observation_id TEXT NOT NULL REFERENCES observations(id),
                revision INTEGER NOT NULL, sha256 TEXT NOT NULL,
                title TEXT NOT NULL, summary TEXT NOT NULL, observed_at TEXT NOT NULL,
                PRIMARY KEY(observation_id, revision)
              );
              CREATE TABLE IF NOT EXISTS topics (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, domain TEXT NOT NULL,
                problem TEXT NOT NULL, hypothesis TEXT NOT NULL, falsification TEXT NOT NULL,
                origin TEXT NOT NULL, status TEXT NOT NULL, novelty_checked INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
              );
              CREATE TABLE IF NOT EXISTS research_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id TEXT NOT NULL REFERENCES topics(id), recorded_at TEXT NOT NULL,
                agent TEXT NOT NULL, findings TEXT NOT NULL, evidence_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'unverified_ai_assessment'
              );
              CREATE TABLE IF NOT EXISTS cycles (
                cycle_id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL, fetched INTEGER NOT NULL DEFAULT 0,
                added INTEGER NOT NULL DEFAULT 0, errors_json TEXT NOT NULL DEFAULT '[]'
              );
              CREATE TABLE IF NOT EXISTS audit (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, happened_at TEXT NOT NULL,
                action TEXT NOT NULL, entity_id TEXT NOT NULL, detail_json TEXT NOT NULL,
                prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL
              );
            """)

    @staticmethod
    def _event(db: sqlite3.Connection, action: str, identifier: str, detail: dict) -> None:
        row = db.execute("SELECT entry_hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        prev = row["entry_hash"] if row else "0" * 64
        happened = _now()
        payload = _json([happened, action, identifier, detail, prev])
        digest = sha256(payload.encode()).hexdigest()
        db.execute("INSERT INTO audit(happened_at,action,entity_id,detail_json,prev_hash,entry_hash)"
                   " VALUES(?,?,?,?,?,?)",
                   (happened, action, identifier, _json(detail), prev, digest))

    def audit_verify(self) -> dict:
        prev = "0" * 64
        with self.connect() as db:
            rows = db.execute("SELECT * FROM audit ORDER BY seq").fetchall()
        for row in rows:
            expected = sha256(_json([row["happened_at"], row["action"], row["entity_id"],
                                     json.loads(row["detail_json"]), prev]).encode()).hexdigest()
            if row["prev_hash"] != prev or row["entry_hash"] != expected:
                return {"valid": False, "broken_at": row["seq"], "events": len(rows)}
            prev = expected
        return {"valid": True, "events": len(rows), "tip_hash": prev,
                "limitation": "哈希链可检测普通篡改；生产级防管理员篡改需独立不可变存储与签名。"}

    def seed(self) -> dict:
        source_data = json.loads((self.seed_dir / "problem_sources.json").read_text(encoding="utf-8"))
        topic_data = json.loads((self.seed_dir / "fire_apparatus_topics.json").read_text(encoding="utf-8"))
        count_s = count_t = 0
        with self.connect(write=True) as db:
            for x in source_data["sources"]:
                if not _ID.fullmatch(x["id"]):
                    raise PatentWorkflowError("种子平台编号无效。")
                url = _url(x["url"])
                feed = _url(x["feed_url"]) if x.get("feed_url") else ""
                if feed and not (_host(feed) == _host(url) or
                                 _host(feed).endswith("." + _host(url))):
                    raise PatentWorkflowError("种子 RSS 与源域名不符。")
                result = db.execute("""INSERT OR IGNORE INTO sources
                    (id,name,url,category,region,mode,feed_url,cadence_hours,status,
                    rights,provenance,reviewer,reviewed_at,next_due,created_at)
                    VALUES(?,?,?,?,?,?,?,?, 'approved',?,?,?,?,?,?)""",
                    (x["id"], x["name"], url, x["category"], x["region"],
                     x["mode"], feed, int(x["cadence_hours"]),
                     x["rights"], "curated_repository_seed", "repository_maintainer",
                     x["seeded_on"], _now(), _now()))
                count_s += result.rowcount
            for x in topic_data["topics"]:
                if not _ID.fullmatch(x["id"]):
                    raise PatentWorkflowError("种子课题编号无效。")
                result = db.execute("""INSERT OR IGNORE INTO topics
                    (id,title,domain,problem,hypothesis,falsification,origin,status,novelty_checked,created_at)
                    VALUES(?,?,?,?,?,?,?,?,0,?)""",
                    (x["id"], x["title"], x["domain"], x["problem"], x["hypothesis"],
                     x["falsification"], x["origin"], "hypothesis_only", _now()))
                count_t += result.rowcount
            if count_s or count_t:
                self._event(db, "catalog_seed", "repository", {"sources_added": count_s,
                                                              "topics_added": count_t})
        return {"sources_added": count_s, "topics_added": count_t}

    def sources(self, status: str = "approved", limit: int = 100) -> list[dict]:
        if status not in ("approved", "pending", "disabled", "rejected", "all"):
            raise PatentWorkflowError("平台状态无效。")
        query = "SELECT * FROM sources"
        params: tuple = ()
        if status != "all":
            query += " WHERE status=?"
            params = (status,)
        query += " ORDER BY CASE status WHEN 'approved' THEN 0 ELSE 1 END,name LIMIT ?"
        with self.connect() as db:
            rows = db.execute(query, (*params, max(1, min(int(limit), 200)))).fetchall()
        return [dict(row) for row in rows]

    def topics(self, limit: int = 100) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM topics ORDER BY id LIMIT ?",
                              (max(1, min(int(limit), 200)),)).fetchall()
        return [dict(row) for row in rows]

    def propose(self, name: str, url: str, reason: str, *,
                discovered_from: str = "manual") -> dict:
        if not isinstance(name, str) or not 3 <= len(name.strip()) <= 160:
            raise PatentWorkflowError("请提供新平台的明确名称。")
        if not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 1200:
            raise PatentWorkflowError("请说明发现这个来源的技术价值和上下文。")
        norm = _url(url)
        ident = "DISC-" + sha256(norm.encode()).hexdigest()[:18].upper()
        provenance = (discovered_from or "manual")[:400]
        with self.connect(write=True) as db:
            existing = db.execute("SELECT id,status FROM sources WHERE url=?", (norm,)).fetchone()
            if existing:
                return {"source_id": existing["id"], "status": existing["status"],
                        "created": False, "message": "既有来源已复用"}
            db.execute("""INSERT INTO sources
                (id,name,url,category,region,mode,cadence_hours,status,rights,provenance,
                 next_due,created_at) VALUES(?,?,?,'candidate','UNKNOWN','manual',168,
                  'pending','unknown',?,?,?)""",
                (ident, name.strip(), norm, _json({"why": reason.strip(),
                 "discovered_from": provenance}), "", _now()))
            self._event(db, "source_proposed", ident, {"url": norm, "discovered_from": provenance})
        return {"source_id": ident, "status": "pending", "created": True,
                "requires_human_source_approval": True}

    def approve(self, source_id: str, *, reviewer: str, rights_reviewed: bool,
                mode: str = "manual", feed_url: str = "", cadence_hours: int = 168) -> dict:
        # CLI only. Never expose this method as an AI-callable MCP tool.
        if not rights_reviewed or not isinstance(reviewer, str) or len(reviewer.strip()) < 3:
            raise PatentWorkflowError("审批人需确认来源身份、版权、条款及合法访问方式。")
        if mode not in ("manual", "rss") or not 24 <= cadence_hours <= 8760:
            raise PatentWorkflowError("巡检方式/周期超出范围。")
        with self.connect(write=True) as db:
            row = db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
            if not row or row["status"] != "pending":
                raise PatentWorkflowError("只有待审核的候选平台允许批准。")
            feed = _url(feed_url) if mode == "rss" else ""
            if mode == "rss" and (not feed or _host(feed) != _host(row["url"])):
                raise PatentWorkflowError("RSS 必须与获批准平台保持完全相同主机。")
            db.execute("""UPDATE sources SET status='approved',mode=?,feed_url=?,
                         cadence_hours=?,reviewer=?,reviewed_at=?,rights='reviewed_by_operator',
                         next_due=? WHERE id=?""",
                       (mode,feed,cadence_hours,reviewer.strip(),_now(),_now(),source_id))
            self._event(db, "source_approved", source_id, {"reviewer": reviewer.strip(),
                        "rights_reviewed": True, "mode": mode})
        return {"source_id": source_id, "status": "approved",
                "warning": "本地操作者标识非身份认证；企业部署需要 OIDC 管理员审批。"}

    def observe(self, source_id: str, url: str, title: str, *,
                summary: str = "", published_at: str = "") -> dict:
        if not isinstance(title, str) or not 3 <= len(title.strip()) <= 500:
            raise PatentWorkflowError("公开观察记录标题为空或超长。")
        if not isinstance(summary, str) or len(summary) > 5000:
            raise PatentWorkflowError("公开摘要超过5000字符。")
        norm = _url(url)
        date = _utc_date(published_at)
        obs_id = "OBS-" + sha256(f"{source_id}|{norm}".encode()).hexdigest()[:20].upper()
        clean_title, clean_summary = title.strip(), _strip_html(summary)
        digest = sha256(_json([clean_title, clean_summary, date]).encode()).hexdigest()
        relevant = int(any(k in (clean_title + " " + clean_summary).lower() for k in _KEYWORDS))
        with self.connect(write=True) as db:
            source = db.execute("SELECT id,url,status FROM sources WHERE id=?", (source_id,)).fetchone()
            if not source or source["status"] != "approved":
                raise PatentWorkflowError("未批准来源禁止进入可信平台观察队列。")
            domain = _host(source["url"])
            if not (_host(norm) == domain or _host(norm).endswith("." + domain)):
                raise PatentWorkflowError("公开记录的链接超出来源域名，需登记新平台候选。")
            previous = db.execute("SELECT sha256,revision FROM observations WHERE id=?",
                                  (obs_id,)).fetchone()
            if previous and previous["sha256"] == digest:
                db.execute("UPDATE observations SET last_seen=? WHERE id=?", (_now(), obs_id))
                return {"observation_id": obs_id, "status": "unchanged", "relevant": bool(relevant)}
            revision = previous["revision"] + 1 if previous else 1
            db.execute("""INSERT INTO observations
                (id,source_id,url,title,summary,published_at,first_seen,last_seen,
                 sha256,revision,relevant,status)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,'triage_pending')
                ON CONFLICT(id) DO UPDATE SET title=excluded.title,summary=excluded.summary,
                published_at=excluded.published_at,last_seen=excluded.last_seen,
                sha256=excluded.sha256,revision=excluded.revision,
                relevant=excluded.relevant,status='triage_pending'""",
                (obs_id,source_id,norm,clean_title,clean_summary,date,_now(),_now(),
                 digest,revision,relevant))
            db.execute("""INSERT INTO observation_revisions
                (observation_id,revision,sha256,title,summary,observed_at) VALUES(?,?,?,?,?,?)""",
                (obs_id,revision,digest,clean_title,clean_summary,_now()))
            self._event(db,"observation_version",obs_id,{"source_id":source_id,
                        "sha256":digest,"revision":revision})
        return {"observation_id":obs_id,"status":"created" if not previous else "updated",
                "revision":revision,"relevant":bool(relevant),
                "verification":"metadata_only_unverified","novelty_assessed":False}

    def inbox(self, limit: int = 30) -> dict:
        limit = max(1,min(int(limit),100))
        with self.connect() as db:
            observation = [dict(r) for r in db.execute(
                "SELECT * FROM observations WHERE status='triage_pending' "
                "ORDER BY relevant DESC,last_seen DESC LIMIT ?",(limit,))]
            pending = [dict(r) for r in db.execute(
                "SELECT id,name,url,provenance,created_at FROM sources "
                "WHERE status='pending' ORDER BY created_at LIMIT ?",(limit,))]
            notes = [dict(r) for r in db.execute(
                "SELECT * FROM research_notes ORDER BY id DESC LIMIT ?",(limit,))]
        return {"new_observations":observation,"unapproved_source_candidates":pending,
                "unverified_research_notes":notes,
                "next_step":"AI 读取问题来源与已存课题，联动现有专利/论文/创新技能研究；人类单独审核结论。"}

    def plan(self, topic_id: str) -> dict:
        with self.connect() as db:
            topic = db.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
            observation = None if topic else db.execute(
                "SELECT * FROM observations WHERE id=?", (topic_id,)).fetchone()
        if not topic and not observation:
            raise PatentWorkflowError("课题或来源观察编号不存在。")
        title = topic["title"] if topic else observation["title"]
        return {"topic_id":topic_id,"title":title,"state":"research_plan_only",
                "stages":["恢复此主题已有文献 MD 与知识图谱","核对公告/故障/标准原文及发布日期",
                          "全球专利/论文双检索，保存覆盖国家、语言、日期和缺口",
                          "抽取力学与流体机理，TRIZ/FMEA/跨行业想法裂变",
                          "逐特征查新与反证，并设计能证伪的机械试验",
                          "按来源质量标注研究结论并提交工程师独立审核"],
                "mcp_tools":["patent_literature_search","patent_frontier_scan",
                             "patent_idea_plan","patent_index_search",
                             "patent_brief_audit"],
                "patent_novelty_certified":False,
                "experimental_validation_done":False,
                "outbound_search_requires_project_approval":True}


    def derive_topic(self, observation_id: str, problem: str, hypothesis: str,
                     falsification: str, domain: str = "mechanical") -> dict:
        """AI may register a research hypothesis; it cannot attest patent novelty."""
        for field, value in (("problem",problem),("hypothesis",hypothesis),
                             ("falsification",falsification),("domain",domain)):
            if not isinstance(value,str) or not 5 <= len(value.strip()) <= 1600:
                raise PatentWorkflowError(f"{field} 需要明确且有界的技术描述。")
        with self.connect(write=True) as db:
            observation=db.execute("SELECT * FROM observations WHERE id=?",
                                   (observation_id,)).fetchone()
            if not observation:
                raise PatentWorkflowError("新的课题须关联真实且已入库的来源观察记录。")
            topic_id="IDEA-"+sha256((observation_id+"|"+hypothesis.strip().casefold())
                                   .encode()).hexdigest()[:20].upper()
            result=db.execute("""INSERT OR IGNORE INTO topics
                (id,title,domain,problem,hypothesis,falsification,origin,status,novelty_checked,created_at)
                VALUES(?,?,?,?,?,?,?,'research_pending',0,?)""",
                (topic_id,observation["title"],domain.strip(),problem.strip(),
                 hypothesis.strip(),falsification.strip(),
                 "public_observation:"+observation_id,_now()))
            if result.rowcount:
                db.execute("UPDATE observations SET status='research_pending' WHERE id=?",
                           (observation_id,))
                self._event(db,"topic_derived",topic_id,{"observation_id":observation_id,
                           "status":"research_pending"})
        return {"topic_id":topic_id,"created":bool(result.rowcount),
                "status":"research_pending","novelty_checked":False,
                "engineering_validated":False}

    def record_research(self, topic_id: str, agent: str, findings: str,
                        evidence_urls: list[str], *, public_only: bool = False) -> dict:
        if not public_only:
            raise PatentWorkflowError("共享平台库仅可保存已获公开许可的信息。")
        if not isinstance(agent,str) or not 2<=len(agent.strip())<=120:
            raise PatentWorkflowError("需要分析执行者标签。")
        if not isinstance(findings,str) or not 10<=len(findings)<=10000:
            raise PatentWorkflowError("需要标明分析、反证和待验证条件。")
        if not isinstance(evidence_urls,list) or len(evidence_urls)>30:
            raise PatentWorkflowError("证据链接上限30条。")
        urls=[_url(u) for u in evidence_urls]
        with self.connect(write=True) as db:
            topic=db.execute("SELECT id FROM topics WHERE id=?",(topic_id,)).fetchone()
            if not topic:
                raise PatentWorkflowError("研究笔记必须绑定已经登记的课题。")
            row=db.execute("""INSERT INTO research_notes
                (topic_id,recorded_at,agent,findings,evidence_json,status)
                VALUES(?,?,?,?,?,'unverified_ai_assessment')""",
                (topic_id,_now(),agent.strip(),findings,_json(urls)))
            self._event(db,"research_note",topic_id,{"note_id":row.lastrowid,
                        "evidence_count":len(urls),"status":"unverified_ai_assessment"})
        return {"topic_id":topic_id,"note_id":row.lastrowid,"status":"unverified_ai_assessment",
                "not_a_patentability_or_engineering_certification":True}

    def cycle(self, *, allow_network: bool = False, max_sources: int = 5,
              fetcher: Callable[[dict],dict] | None = None) -> dict:
        """One bounded poll; run repeatedly from durable Docker/cron scheduler."""
        with self.connect(write=True) as db:
            eligible = [dict(r) for r in db.execute("""SELECT * FROM sources
                WHERE status='approved' AND mode='rss' AND (next_due='' OR next_due<=?)
                AND (lease_until='' OR lease_until<=?)
                ORDER BY next_due,id LIMIT ?""",
                (_now(),_now(),max(1,min(int(max_sources),20))))]
            lease=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(timespec="seconds")
            for x in eligible:
                db.execute("UPDATE sources SET lease_until=? WHERE id=?", (lease,x["id"]))
        if not allow_network:
            with self.connect(write=True) as db:
                for x in eligible:
                    db.execute("UPDATE sources SET lease_until='' WHERE id=?", (x["id"],))
            return {"status":"offline_preview","due_sources":[x["id"] for x in eligible],
                    "fetched":0,"added":0,"network_used":False,"next":"配置定时器调用 --allow-public-network"}
        fetched=added=0
        failures=[]
        for source in eligible:
            try:
                payload=(fetcher or _safe_fetch)(source)
                if payload["status"] == 304:
                    fetched += 1
                elif payload["status"] == 200:
                    body=payload["data"]
                    if not isinstance(body,bytes):
                        raise PatentWorkflowError("RSS 供应商返回类型无效。")
                    suggested=0
                    for entry in _feed_entries(body):
                        try:
                            target=_url(entry["url"])
                            origin_host=_host(source["url"])
                            if not (_host(target)==origin_host or
                                    _host(target).endswith("." + origin_host)):
                                if suggested<3:
                                    self.propose("RSS关联的外部平台："+_host(target),target,
                                        "已批准公开RSS中的外部引用，需人工核对发布者与长期监测价值。",
                                        discovered_from=source["id"])
                                    suggested+=1
                                continue
                            result=self.observe(source["id"],**entry)
                            if result["status"]=="created":
                                added+=1
                        except (PatentWorkflowError,TypeError,ValueError):
                            # An individual off-domain/invalid article never authorizes a new domain.
                            continue
                    fetched+=1
                else:
                    raise PatentWorkflowError("RSS 状态码不属于200/304。")
                with self.connect(write=True) as db:
                    db.execute("""UPDATE sources SET last_checked=?,next_due=?,lease_until='',
                        etag=?,last_modified=?,errors=0,last_error='' WHERE id=?""",
                        (_now(),(datetime.now(timezone.utc)+timedelta(hours=source["cadence_hours"]))
                         .isoformat(timespec="seconds"),payload.get("etag",source["etag"])[:180],
                         payload.get("last_modified",source["last_modified"])[:180],source["id"]))
            except Exception as exc:
                message=(type(exc).__name__ + ": " + str(exc))[:220]
                failures.append({"source_id":source["id"],"error":message})
                with self.connect(write=True) as db:
                    retries=min(source["errors"]+1,6)
                    next_retry=(datetime.now(timezone.utc)+timedelta(hours=min(2**retries,48)))
                    db.execute("""UPDATE sources SET errors=?,last_checked=?,last_error=?,
                        next_due=?,lease_until='' WHERE id=?""",
                        (retries,_now(),message,next_retry.isoformat(timespec="seconds"),source["id"]))
                    self._event(db,"source_poll_failed",source["id"],{"error":message,
                                "retry_after":next_retry.isoformat(timespec="seconds")})
        with self.connect(write=True) as db:
            db.execute("INSERT INTO cycles(started_at,finished_at,fetched,added,errors_json) VALUES(?,?,?,?,?)",
                       (_now(),_now(),fetched,added,_json(failures)))
        return {"status":"complete" if not failures else "partial_or_failed",
                "fetched":fetched,"added":added,"errors":failures,
                "network_used":True,"independent_validation_performed":False,
                "source_discovery":"candidate_platforms_must_be_proposed_and_approved"}


