"""面向已绑定项目的标准 MCP 工具扩展：前沿雷达/可追溯索引/LaTeX。"""
from __future__ import annotations

from typing import Any

from .core import PatentWorkflowError
from .patent_index import PatentIndex
from .frontier_radar import FrontierRadar
from .latex_manuscript import ManuscriptWorkspace


def register_project_research_tools(server: Any, service: Any) -> None:
    # 每个业务层只允许访问 service.project，传入 case_id 不能跨 project_id。
    index = PatentIndex(service.workspace)
    radar = FrontierRadar(service.project)
    papers = ManuscriptWorkspace(service.project)

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
