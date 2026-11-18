"""面向已绑定项目的标准 MCP 工具扩展：前沿雷达/可追溯索引/LaTeX。"""
from __future__ import annotations

from typing import Any

from .core import PatentWorkflowError
from .patent_index import PatentIndex
from .frontier_radar import FrontierRadar
from .latex_manuscript import ManuscriptWorkspace
from .problem_sources import ProblemSourceRegistry


def register_project_research_tools(server: Any, service: Any) -> None:
    # 每个业务层只允许访问 service.project，传入 case_id 不能跨 project_id。
    index = PatentIndex(service.workspace)
    radar = FrontierRadar(service.project)
    papers = ManuscriptWorkspace(service.project)
    public_catalog = ProblemSourceRegistry(service.project.workspace_root)

    @server.tool()
    def patent_index_refresh(case_id: str, query: str, limit: int = 20) -> dict:
        """每次真正访问 EPO OPS，并在本项目 SQLite 记录时间、变化及失败。"""
        service._case(case_id)
        if not service.workspace.can_egress(case_id):
            raise PatentWorkflowError("项目当前轮缺少保密外发授权。")
        from .providers import EPOOPSProvider
        provider = EPOOPSProvider()
        return index.refresh(case_id, query, provider.name,
                             lambda term, size: provider.search(term,limit=size), limit)

    @server.tool()
    def patent_index_search(case_id: str, term: str = "",
                            max_age_hours: int = 6, limit: int = 40) -> dict:
        """查询本项目专利索引，包括更新时间和过期状态。"""
        service._case(case_id)
        return index.search(case_id,term,limit,max_age_hours)

    @server.tool()
    def patent_index_history(case_id: str, publication: str, limit: int = 20) -> list[dict]:
        """返回这项已公开专利在项目索引中的变化版本与来源。"""
        service._case(case_id)
        return index.history(case_id,publication,limit)

    @server.tool()
    def patent_frontier_scan(case_id: str, topics: list[str] | None = None,
                             days: int = 90, per_topic: int = 8) -> dict:
        """实际查询近期 OpenAlex 文献，返回 DOI/来源时间/可验证技术前沿。"""
        current=service._case(case_id)
        return radar.scan(case_id,topics or [current["direction"][:140]],days,per_topic)

    @server.tool()
    def patent_variant_plan(case_id: str, run_id: str,
                            title_or_publication: str, limit: int = 6) -> dict:
        """基于已有公开专利的真实名称/公开号提出机械、控制等不同变种路线。"""
        folder=service._folder(case_id,run_id)
        return radar.variants(case_id,folder,title_or_publication,limit)

    @server.tool()
    def patent_manuscript_create(case_id: str, title: str, manuscript_id: str = "") -> dict:
        """创建当前项目的 LaTeX 论文初稿、章节、BibTeX 与追溯索引。"""
        service._case(case_id)
        return papers.create(case_id,title,manuscript_id)

    @server.tool()
    def patent_manuscript_read(case_id: str, manuscript_id: str, section: str) -> dict:
        """获取单章节 LaTeX 或参考文献 BibTeX 源文本。"""
        return papers.read(case_id,manuscript_id,section)

    @server.tool()
    def patent_manuscript_edit(case_id: str, manuscript_id: str, section: str, latex: str) -> dict:
        """修改一个 LaTeX 章节并保存不可覆盖的源版本及内容哈希。"""
        return papers.edit(case_id,manuscript_id,section,latex)

    @server.tool()
    def patent_manuscript_revisions(case_id: str, manuscript_id: str, section: str) -> list[dict]:
        """查询论文一节的历史修订记录和 SHA256。"""
        return papers.revisions(case_id,manuscript_id,section)

    @server.tool()
    def patent_manuscript_export(case_id: str, manuscript_id: str,
                                 output_format: str = "docx") -> dict:
        """使用 Pandoc 转 DOCX/HTML/Markdown，服务端拒绝执行原始 TeX/PDF。"""
        return papers.export(case_id,manuscript_id,output_format)


    @server.tool()
    def patent_source_catalog(status: str = "approved", limit: int = 60) -> dict:
        """默认先查长期共享的公开课题平台库，包括来源等级、监测方式与更新时间。"""
        return {"sources": public_catalog.sources(status,limit),
                "project_id": service.project.project_id,
                "contains_confidential_project_data": False}

    @server.tool()
    def patent_topic_catalog(limit: int = 60) -> dict:
        """检索沉淀的消防车机械研究题目，包括历史 AI 假说；未证明新颖性。"""
        return {"topics": public_catalog.topics(limit),"novelty_certified":False}

    @server.tool()
    def patent_discovery_inbox(limit: int = 30) -> dict:
        """读取新增公告、待审核平台和待独立核实的公开研究笔记。"""
        return public_catalog.inbox(limit)

    @server.tool()
    def patent_source_propose(name: str, url: str, reason: str,
                              discovered_from: str = "manual") -> dict:
        """AI 发现新大平台后只能登记候选；禁止自动批准外网监测。"""
        return public_catalog.propose(name,url,reason,discovered_from=discovered_from)

    @server.tool()
    def patent_public_observe(source_id: str, url: str, title: str,
                              summary: str = "", published_at: str = "") -> dict:
        """保存从已批准公开来源得到的公告元信息；内容仍待原文核验。"""
        return public_catalog.observe(source_id,url,title,summary=summary,
                                      published_at=published_at)

    @server.tool()
    def patent_topic_derive(observation_id: str, problem: str, hypothesis: str,
                            falsification: str, domain: str = "mechanical") -> dict:
        """根据真实公开来源观察提出新机械课题和可证伪实验，持久化但不认证专利性。"""
        return public_catalog.derive_topic(observation_id,problem,hypothesis,
                                          falsification,domain)

    @server.tool()
    def patent_topic_plan(topic_id: str) -> dict:
        """创建查新、论文、机理迁移与实验评审的研究计划，优先复用原有文献。"""
        return public_catalog.plan(topic_id)

    @server.tool()
    def patent_public_research_note(topic_id: str, agent: str, findings: str,
                                    evidence_urls: list[str], public_only: bool = False) -> dict:
        """公开资料研究笔记；默认拒绝保密信息，AI 结论永远待独立核验。"""
        return public_catalog.record_research(topic_id,agent,findings,evidence_urls,
                                              public_only=public_only)

    @server.tool()
    def patent_source_cycle(allow_public_network: bool = False,
                            max_sources: int = 5) -> dict:
        """执行一轮有界公开 RSS 巡检，需显式网络授权；持久计时、去重、退避。"""
        return public_catalog.cycle(allow_network=allow_public_network,
                                    max_sources=max_sources)

    @server.tool()
    def patent_topic_adopt(case_id: str, topic_id: str) -> dict:
        """把公开课题转入当前项目私有案卷，保密审批后才允许对外检索。"""
        plan=public_catalog.plan(topic_id)
        result=service.create_case(case_id,plan["title"],confidentiality="秘密")
        with service.workspace.connect(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS project_topic_links
                (case_id TEXT PRIMARY KEY REFERENCES cases(case_id),
                 public_topic_id TEXT NOT NULL, linked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            db.execute("INSERT INTO project_topic_links(case_id,public_topic_id) VALUES(?,?)",
                       (case_id,topic_id))
        return {"case_id":result["case_id"],"topic_id":topic_id,
                "research_project_id":service.project.project_id,
                "outbound_approved":False,"filing_authorized":False,
                "next_action":"项目保密审批后启动全球专利及论文检索。"}
