"""当期前沿雷达：OpenAlex 真实公开论文发现与已公开专利变种任务。

用户输入最新专利名称或公开号，先核对已有证据，再生成需要 AI
执行的多路线问题；技术内容本身不得凭空制造。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from urllib import parse, request, error
from uuid import uuid4

from .core import Evidence, PatentWorkflowError, evidence_id, utc_now
from .project_storage import ProjectStorage

VARIANT_OPERATORS = (
    ("拓扑变换", "改变主要机械连接、流道或传动路径，并推导守恒约束"),
    ("机理替代", "以另一种物理机理解决相同工程问题，列出可制造的构件"),
    ("结构—控制协同", "将结构被动作用与控制主动反馈建立不可简单拆开的协同"),
    ("逆向工况", "在高海拔、极低温、冲击、冗余安全等边界工况中重构"),
    ("跨领域迁移", "检索非消防领域的流体、航空、医疗或化工机理再做适配"),
    ("失效链反转", "从单点失效和不确定性反推容错与自诊断技术方案"),
    ("减件与可维护性", "去除传统中间部件并解释技术效果、接口及可维修性"),
    ("正交组合", "跨独立技术轴交叉两个候选，证明功能耦合而非简单拼接"),
)


class FrontierRadar:
    def __init__(self, project: ProjectStorage,
                 fetch_json=None):
        self.project=project
        self.workspace=project.workspace
        self.fetch_json=fetch_json or self._request_json
        with self.workspace.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS frontier_scans (
                  scan_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id),
                  created_at TEXT NOT NULL, from_date TEXT NOT NULL, to_date TEXT NOT NULL,
                  status TEXT NOT NULL, topics_json TEXT NOT NULL, error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS frontier_observations (
                  scan_id TEXT NOT NULL REFERENCES frontier_scans(scan_id),
                  source_id TEXT NOT NULL, topic TEXT NOT NULL, publication_date TEXT NOT NULL,
                  title TEXT NOT NULL, doi TEXT NOT NULL, url TEXT NOT NULL,
                  observed_at TEXT NOT NULL, source_type TEXT NOT NULL,
                  primary_topic TEXT NOT NULL, status TEXT NOT NULL,
                  PRIMARY KEY(scan_id,source_id,topic)
                );
            """)

    @staticmethod
    def _request_json(url: str) -> dict:
        headers={"User-Agent":"Mechanical-Patent-Research/0.2 (public research discovery)",
                 "Accept":"application/json"}
        with request.urlopen(request.Request(url,headers=headers),timeout=25) as response:
            if response.status!=200:
                raise PatentWorkflowError("学术前沿数据请求失败。")
            raw=response.read(2_000_001)
        if len(raw)>2_000_000:
            raise PatentWorkflowError("供应商返回超大数据包。")
        return json.loads(raw)

    def scan(self,case_id:str,topics:list[str],days:int=90,per_topic:int=8)->dict:
        self.workspace.status(case_id)
        if not self.workspace.can_egress(case_id):
            raise PatentWorkflowError("前沿检索会外发研究关键词，当前轮未经保密审批。")
        if not isinstance(topics,list) or not 1<=len(topics)<=6:
            raise PatentWorkflowError("前沿主题必须包含1-6项。")
        if any(not isinstance(t,str) or not 2<=len(t.strip())<=150 for t in topics):
            raise PatentWorkflowError("前沿主题文字超限。")
        if not 7<=days<=730 or not 1<=per_topic<=25:
            raise PatentWorkflowError("时间窗口7-730天，每项1-25篇。")
        now=datetime.now(timezone.utc)
        from_date=(now-timedelta(days=days)).date().isoformat()
        to_date=now.date().isoformat()
        scan_id="RADAR-"+uuid4().hex[:16].upper()
        with self.workspace.connect(write=True) as db:
            db.execute("""INSERT INTO frontier_scans
                (scan_id,case_id,created_at,from_date,to_date,status,topics_json)
                VALUES(?,?,?,?,?,'running',?)""",
                (scan_id,case_id,utc_now(),from_date,to_date,json.dumps(topics,ensure_ascii=False)))
        observations=[]
        failures=[]
        for topic in dict.fromkeys(t.strip() for t in topics):
            params={
                "search":topic,
                "filter":f"from_publication_date:{from_date},to_publication_date:{to_date}",
                "sort":"publication_date:desc",
                "per_page":str(per_topic),
                "select":"id,title,publication_date,doi,primary_topic,open_access",
            }
            key=os.getenv("OPENALEX_API_KEY","").strip()
            if key:
                params["api_key"]=key
            url="https://api.openalex.org/works?"+parse.urlencode(params)
            try:
                response=self.fetch_json(url)
                result=response.get("results",[])
                if not isinstance(result,list):
                    raise PatentWorkflowError("OpenAlex 响应类型异常。")
                for item in result[:per_topic]:
                    title=item.get("title") or ""
                    day=item.get("publication_date") or ""
                    source=item.get("id") or ""
                    if not title or not source.startswith("https://openalex.org/"):
                        continue
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",day) or not from_date<=day<=to_date:
                        continue
                    doi=item.get("doi") or ""
                    point=item.get("primary_topic") or {}
                    observation={
                        "scan_id":scan_id,"topic":topic,"title":title[:500],
                        "source_id":source.rsplit("/",1)[-1],
                        "url":source,"doi":doi,
                        "publication_date":day,"observed_at":utc_now(),
                        "source_type":"paper_metadata",
                        "primary_topic":point.get("display_name","") if isinstance(point,dict) else "",
                        "status":"metadata_only_requires_full_text_verification",
                    }
                    observations.append(observation)
            except Exception as exc:
                failures.append({"topic":topic,"error":str(exc)[:250]})
        with self.workspace.connect(write=True) as db:
            for row in observations:
                db.execute("""INSERT OR IGNORE INTO frontier_observations
                    (scan_id,source_id,topic,publication_date,title,doi,url,observed_at,
                     source_type,primary_topic,status)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    tuple(row[x] for x in ("scan_id","source_id","topic","publication_date",
                        "title","doi","url","observed_at","source_type","primary_topic","status")))
            db.execute("""UPDATE frontier_scans SET status=?,error=? WHERE scan_id=?""",
                       ("complete" if not failures else "partial_or_failed",
                        json.dumps(failures,ensure_ascii=False)[:2000],scan_id))
        return {"scan_id":scan_id,"case_id":case_id,"from_date":from_date,"to_date":to_date,
                "observations":observations,"errors":failures,
                "discovery_status":"real_openalex_metadata" if observations else "no_confirmed_results",
                "patent_novelty_assessed":False,
                "limitations":"按论文发表日期过滤；不代表该论文近期才入库，亦不等于专利最早公开日期。"}

    def variants(self,case_id:str,case_folder:Path,patent_name_or_number:str,limit:int=6)->dict:
        """必须根据真实案卷检索到的专利提出变种任务。"""
        self.workspace.status(case_id)
        if not isinstance(patent_name_or_number,str) or not 3<=len(patent_name_or_number.strip())<=300:
            raise PatentWorkflowError("提供真实专利名称或公开号。")
        if not 1<=limit<=len(VARIANT_OPERATORS):
            raise PatentWorkflowError("变种方向数量超出限制。")
        folder=Path(case_folder)
        source_path=folder/"02_patents.json"
        if source_path.is_symlink() or not source_path.is_file():
            raise PatentWorkflowError("缺少当前案卷原始专利记录。")
        intake=json.loads((folder/"00_intake.json").read_text(encoding="utf-8"))
        if intake.get("case_id")!=case_id:
            raise PatentWorkflowError("专利所在的案卷与当前项目案卷不一致。")
        raw=json.loads(source_path.read_text(encoding="utf-8")).get("records",[])
        term=patent_name_or_number.strip().casefold()
        matches=[]
        for row in raw:
            try:
                e=Evidence.from_dict(row)
            except (TypeError,KeyError,ValueError):
                continue
            if e.kind=="patent" and (e.publication.casefold()==term or e.title.casefold()==term):
                matches.append(e)
        if not matches:
            return {"status":"source_discovery_required","title_or_publication":patent_name_or_number,
                    "actions":["向合法专利供应商查询该名称及公开号","核对公开日和真实权利要求",
                               "将真实文献写入案卷后重新运行变种分析"],
                    "invented_patents":False}
        if len(matches)>1:
            return {"status":"ambiguous_patent_title","candidates":[{"publication":e.publication,
                       "title":e.title,"url":e.url} for e in matches[:10]]}
        e=matches[0]
        return {"status":"source_found_requires_independent_countersearch",
                "source":{"publication":e.publication,"title":e.title,"url":e.url,
                          "evidence_id":evidence_id(e),"publication_date":e.publication_date,
                          "claims_available":bool(e.claims),"source_verified":e.verified},
                "variants":[{"operator":name,"research_task":instruction,
                             "must_include":["原权要技术特征","新机理与具体部件","两者结构/控制差异",
                                             "理论公式与约束","现有技术二轮反证","可证伪实验"]}
                            for name,instruction in VARIANT_OPERATORS[:limit]],
                "notice":"变种研究任务供当前 AI 执行；仅凭名称不能确认原专利权利范围或创造性。"}
