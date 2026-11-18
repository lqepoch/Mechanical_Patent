"""Mechanical_Patent 标准 MCP 业务接口（官方 Python MCP SDK v2）。

MCP 是跨应用工具协议；模型推理由调用端负责，服务端执行真实数据获取、
谱系存档、证据逐项核验与专利稿结构检查。远程 HTTP 仅监听本机回环。
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from .core import Evidence, PatentWorkflowError, evidence_id, save_json, validate_draft
from .ideation_fission import FissionBoard, AXES, METHODS, SCORE_FIELDS
from .technical_brief import render_brief
from .figure_pipeline import prepare_figures, read_figure_plan
from .figure_worker import sync_figures
from .technical_review import inspect_brief
from .filing_gate import conversion_status, require_conversion_approval
from .local_workspace import LocalPatentWorkspace
from .literature_memory import LiteratureMemoryStore
from .project_storage import ProjectStorage
from .quality import inspect_research_case, audit_research_case
from .workflow import PatentResearch

_CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}\Z")
_RUN_ID = re.compile(r"RUN-[A-Za-z0-9_-]{1,80}\Z")
_READABLE = frozenset({
    "00_intake.json", "01_search_plan.json", "02_patents.json", "03_papers.json",
    "04_evidence.json", "04b_technology_graph.json", "05_inventions.json",
    "05a_idea_fission.json", "06_countersearch.json", "07_engineering.json",
    "08_application.json", "08a_technical_brief.json", "08a_technical_brief.tex",
    "08d_figure_plan.json", "08e_figure_render.json", "08f_figure_sync.json",
    "08g_pdf_build.json",
    "09_quality_gate.json", "10_enterprise_quality.json",
    "manifest.json", "AGENT_NEXT_STEPS.md",
})


class PatentMCPService:
    """传输无关服务层，供 MCP、本地 CLI 与未来 REST 网关共同复用。"""

    def __init__(self, workspace_dir: Path, project_id: str = "local"):
        # 一个 MCP 进程固定一个项目。不能借助 case_id 查找其他项目。
        self.project = ProjectStorage(workspace_dir, project_id)
        self.root = self.project.root
        self.workspace = self.project.workspace

    def _case(self, case_id: str) -> dict[str, Any]:
        if not isinstance(case_id, str) or not _CASE_ID.fullmatch(case_id):
            raise PatentWorkflowError("案卷编号只能使用字母、数字、横线和下划线。")
        return self.workspace.status(case_id)

    def _folder(self, case_id: str, run_id: str) -> Path:
        self._case(case_id)
        if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
            raise PatentWorkflowError("研究运行编号无效。")
        expected = self.root / "cases" / case_id / "runs" / run_id
        # 解析后仍须留在工作空间内；阻断恶意符号链接造成的跨租户读取。
        if not expected.resolve().is_relative_to(self.root / "cases" / case_id / "runs"):
            raise PatentWorkflowError("路径越界。")
        if not expected.is_dir() or not (expected / "00_intake.json").is_file():
            raise PatentWorkflowError("此案卷中不存在该研究运行。")
        data = json.loads((expected / "00_intake.json").read_text(encoding="utf-8"))
        if data.get("case_id") != case_id:
            raise PatentWorkflowError("研究运行与案卷身份不匹配。")
        return expected

    def create_case(self, case_id: str, direction: str, confidentiality: str = "秘密") -> dict[str, Any]:
        if not isinstance(case_id, str) or not _CASE_ID.fullmatch(case_id):
            raise PatentWorkflowError("案卷编号不合法。")
        result = self.workspace.create_case(case_id, direction, confidentiality=confidentiality)
        LiteratureMemoryStore(self.root / "cases" / case_id)
        return {"case_id": result["case_id"], "status": result["status"],
                "revision": result["revision"], "confidentiality": result["confidentiality"],
                "next_action": "保密管理员在原有案卷工作流批准查询词外发后可执行专利检索。"}

    def status(self, case_id: str) -> dict[str, Any]:
        record = self._case(case_id)
        return {"case_id": record["case_id"], "project_id": self.project.project_id, "revision": record["revision"],
                "status": record["status"], "confidentiality": record["confidentiality"],
                "outbound_approved": self.workspace.can_egress(case_id),
                "tasks": record.get("tasks", []), "document_totals": record.get("source_reviews", [])}


    def _memory(self, case_id: str) -> LiteratureMemoryStore:
        self._case(case_id)
        project = self.root / "cases" / case_id
        if project.is_symlink():
            raise PatentWorkflowError("项目目录禁止符号链接。")
        return LiteratureMemoryStore(project)

    def literature_search(
        self, case_id: str, query: str, kind: str | None = None, limit: int = 20,
    ) -> dict[str, Any]:
        """返回可查证的文献与稳定 MD 地址，避免把千篇正文塞入上下文。"""
        records = self._memory(case_id).search(query, limit=limit, kind=kind)
        return {"case_id": case_id, "matches": records, "count": len(records)}

    def literature_read(
        self, case_id: str, doc_id: str, max_chars: int = 24000,
    ) -> dict[str, Any]:
        note = self._memory(case_id).read(doc_id)
        size = max(1000, min(int(max_chars), 60000))
        return {"case_id": case_id, "doc_id": doc_id,
                "markdown": note["markdown"][:size],
                "truncated": len(note["markdown"]) > size,
                "full_length": len(note["markdown"]), "note_path": note["path"],
                "content_hash": note["content_hash"]}

    def literature_note(
        self, case_id: str, doc_id: str, analyst: str,
        basis: str, analysis: dict[str, str], source_positions: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._memory(case_id).write_analysis(
            doc_id, analyst=analyst, basis=basis,
            analysis=analysis, source_positions=source_positions,
        )

    def literature_stats(self, case_id: str) -> dict[str, Any]:
        return self._memory(case_id).stats()

    def literature_pending(self, case_id: str, limit: int = 30) -> dict[str, Any]:
        return {"case_id": case_id, "pending": self._memory(case_id).pending_analysis(limit=limit)}

    def literature_resume(self, case_id: str) -> dict[str, Any]:
        return self._memory(case_id).read_resume()

    def literature_resume_save(
        self, case_id: str, analyst: str, markdown: str, expected_sha256: str,
    ) -> dict[str, Any]:
        return self._memory(case_id).update_resume(
            markdown, analyst=analyst, expected_sha256=expected_sha256,
        )

    def literature_harvest(
        self, case_id: str, provider: str, query: str,
        max_documents: int = 200, max_pages: int = 4,
        allow_search_exposure: bool = False,
    ) -> dict[str, Any]:
        """同步受控批量检索；更大规模由带预算的 CLI 持续分批调用。"""
        self._case(case_id)
        if not allow_search_exposure or not self.workspace.can_egress(case_id):
            raise PatentWorkflowError("未同时取得显式外发授权和案卷保密批准。")
        from .papers import CrossrefProvider, OpenAlexProvider
        from .providers import EPOOPSProvider
        from .literature_harvest import HarvestBudget, LiteratureHarvester
        options = {
            "openalex": OpenAlexProvider, "crossref": CrossrefProvider,
            "epo-ops": EPOOPSProvider,
        }
        if provider not in options:
            raise PatentWorkflowError("不支持的文献数据源。")
        budget = HarvestBudget(
            max_documents=max(1, min(int(max_documents), 1000)),
            page_size=20 if provider == "epo-ops" else 100,
            max_pages=max(1, min(int(max_pages), 20)),
            max_seconds=120,
        )
        return LiteratureHarvester(self._memory(case_id)).harvest(
            options[provider](), query, budget=budget,
        )

    def create_run(self, case_id: str) -> dict[str, Any]:
        """离线创建研究运行；供其他已授权搜索 MCP 导入结果。"""
        from .external_sources import create_offline_run
        return create_offline_run(self, case_id)

    def import_sources(self, case_id: str, run_id: str,
                       records: list[dict[str, Any]],
                       patent_queries: list[str] | None = None,
                       paper_queries: list[str] | None = None) -> dict[str, Any]:
        """接收供应商结果，强制标记待原文核验。"""
        from .external_sources import import_external_sources
        return import_external_sources(self, case_id, run_id, records, patent_queries, paper_queries)

    def research(self, case_id: str, patent_queries: list[str], paper_queries: list[str],
                 limit: int = 10, paper_sources: list[str] | None = None,
                 enrich_unpaywall: bool = False,
                 allow_paid_paper_apis: bool = False) -> dict[str, Any]:
        """必须通过已经登记的保密审批才会对外发送真实检索词。"""
        self._case(case_id)
        if not self.workspace.can_egress(case_id):
            raise PatentWorkflowError("案卷当前轮尚无有效的外发批准；拒绝向第三方检索服务发送查询词。")
        if not isinstance(patent_queries, list) or not isinstance(paper_queries, list):
            raise PatentWorkflowError("检索词必须是数组。")
        if not patent_queries and not paper_queries:
            raise PatentWorkflowError("专利或论文检索词至少提供一项。")
        if not 1 <= limit <= 25:
            raise PatentWorkflowError("每个查询的条数限制为1至25。")
        if patent_queries and not (os.getenv("EPO_OPS_CLIENT_ID") and os.getenv("EPO_OPS_CLIENT_SECRET")):
            raise PatentWorkflowError("专利检索尚缺 EPO OPS 授权凭证；可通过已授权行业 MCP 导入真实证据。")
        from .providers import EPOOPSProvider
        from .paper_sources import UnpaywallEnricher, build_paper_providers
        provider = EPOOPSProvider() if patent_queries else None
        papers, paper_warnings = build_paper_providers(
            paper_sources, allow_paid=allow_paid_paper_apis
        ) if paper_queries else ([], [])
        enricher = UnpaywallEnricher() if (paper_queries and enrich_unpaywall) else None
        case = self._case(case_id)
        run_id = "RUN-" + uuid4().hex[:16].upper()
        path = self.root / "cases" / case_id / "runs" / run_id
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        result = PatentResearch(
            provider, papers, path, memory_root=self.root / "cases" / case_id,
            paper_enricher=enricher, paper_source_warnings=paper_warnings,
        ).run(
            case["direction"], patent_queries, paper_queries,
            limit=limit, case_id=case_id,
        )
        indexing = self.workspace.import_case(path)
        return {"case_id": case_id, "run_id": run_id, "patents_with_claims": result["patent_claims_available"],
                "paper_count": result["papers_discovered"], "provider_errors": result["search_errors"],
                "paper_sources": [x.name for x in papers], "paper_source_warnings": paper_warnings,
                "indexed": indexing.get("indexed", 0), "complete_global_search": False,
                "filing_authorized": False}

    def read_artifact(self, case_id: str, run_id: str, artifact: str) -> dict[str, Any]:
        if artifact not in _READABLE:
            raise PatentWorkflowError("读取范围仅允许白名单中的案卷文件。")
        path = self._folder(case_id, run_id) / artifact
        if path.is_symlink() or not path.is_file():
            raise PatentWorkflowError("案卷附件不存在或被替换为符号链接。")
        payload = path.read_bytes()
        if len(payload) > 750_000:
            raise PatentWorkflowError("附件超过MCP安全读取上限，请使用企业受控文件接口。")
        text = payload.decode("utf-8")
        return {"artifact": artifact, "sha256": sha256(payload).hexdigest(),
                "content": json.loads(text) if artifact.endswith(".json") else text}

    def _board(self, case_id: str, run_id: str) -> FissionBoard:
        return FissionBoard(self._folder(case_id, run_id))

    def fission_plan(self, case_id: str, run_id: str, parent_id: str = "", limit: int = 6) -> dict[str, Any]:
        return self._board(case_id, run_id).plan(parent_id, limit)

    def fission_register(self, case_id: str, run_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
        return self._board(case_id, run_id).register(candidate)

    def fission_evaluate(self, case_id: str, run_id: str, candidate_id: str,
                         scores: dict[str, float], review: str, countersearch_refs: list[str],
                         physical_principle: str, engineering_risks: list[str]) -> dict[str, Any]:
        return self._board(case_id, run_id).evaluate(
            candidate_id, scores, review, countersearch_refs, physical_principle, engineering_risks
        )

    def fission_frontier(self, case_id: str, run_id: str, top_k: int = 8) -> dict[str, Any]:
        return self._board(case_id, run_id).frontier(top_k)

    def fission_promote(self, case_id: str, run_id: str, candidate_id: str) -> dict[str, Any]:
        return self._board(case_id, run_id).promote(candidate_id)

    def countersearch_record(self, case_id: str, run_id: str, candidate_id: str,
                             feature: str, source_id: str, quote: str) -> dict[str, Any]:
        """引用真实存档权利要求中的逐字片段；仅有摘要时拒绝标成权要对照。"""
        folder = self._folder(case_id, run_id)
        ideas = json.loads((folder / "05_inventions.json").read_text(encoding="utf-8")).get("candidates", [])
        if not any(x.get("id") == candidate_id for x in ideas):
            raise PatentWorkflowError("须先移交候选方案，才能保存独立反证。")
        if not isinstance(feature, str) or not feature.strip():
            raise PatentWorkflowError("被比较技术特征不能为空。")
        records = json.loads((folder / "04_evidence.json").read_text(encoding="utf-8")).get("records", [])
        patent = None
        for raw in records:
            try:
                e = Evidence.from_dict(raw)
                if e.kind == "patent" and e.verified and evidence_id(e) == source_id:
                    patent = e
                    break
            except (ValueError, TypeError, KeyError):
                continue
        if patent is None or not patent.claims.strip():
            raise PatentWorkflowError("对比文件尚无核验的专利权利要求正文。")
        normalized = " ".join(quote.split()) if isinstance(quote, str) else ""
        if len(normalized) < 4 or normalized not in " ".join(patent.claims.split()):
            raise PatentWorkflowError("引用文本在该件专利的存档权利要求中不存在。")
        path = folder / "06_countersearch.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        charts = data.setdefault("claim_charts", [])
        entry = {"candidate_id": candidate_id, "feature": feature.strip(),
                 "evidence": [{"evidence_id": source_id, "quote": normalized}],
                 "review_state": "source_quote_matched_not_legal_opinion"}
        if entry not in charts:
            charts.append(entry)
            save_json(path, data)
        return {"saved": True, "source_id": source_id, "citation_verified_against_stored_claims": True,
                "novelty_confirmed": False}

    def engineering_record(self, case_id: str, run_id: str, candidate_id: str,
                           physical_principle: str, equations_and_units: list[str],
                           assumptions: list[str], failure_modes: list[str],
                           falsification_tests: list[str], verification_status: str = "hypothesis_only") -> dict[str, Any]:
        """仅记录理论/估算；真实仿真、实验的验证须经受控工程资料流程。"""
        folder = self._folder(case_id, run_id)
        ideas = json.loads((folder / "05_inventions.json").read_text(encoding="utf-8")).get("candidates", [])
        if not any(x.get("id") == candidate_id for x in ideas):
            raise PatentWorkflowError("找不到已移交的候选方案。")
        if verification_status not in {"hypothesis_only", "analytical_estimate"}:
            raise PatentWorkflowError("仿真和实测状态必须通过带可核验原始文件的专门审核流程。")
        if not isinstance(physical_principle, str) or not physical_principle.strip():
            raise PatentWorkflowError("理论原理为空。")
        if any(not isinstance(x, list) or not x or not all(isinstance(s, str) and s.strip() for s in x)
               for x in (equations_and_units, assumptions, failure_modes, falsification_tests)):
            raise PatentWorkflowError("必须提供公式单位、假设、失效模式和证伪试验。")
        path = folder / "07_engineering.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assessments = data.setdefault("assessments", [])
        entry = {"candidate_id": candidate_id, "physical_principle": physical_principle,
                 "equations_and_units": equations_and_units, "assumptions": assumptions,
                 "failure_modes": failure_modes, "falsification_tests": falsification_tests,
                 "verification_status": verification_status,
                 "notice": "仅为 AI 技术论证；无仿真或实验验证记录。"}
        assessments[:] = [x for x in assessments if x.get("candidate_id") != candidate_id]
        assessments.append(entry)
        save_json(path, data)
        return {"saved": True, "verification_status": verification_status, "engineer_signoff": False}

    def brief_save(self, case_id: str, run_id: str, candidate_id: str,
                   brief: dict[str, Any]) -> dict[str, Any]:
        """保存并渲染白话技术方案；不触发正式申请稿。"""
        folder = self._folder(case_id, run_id)
        if not isinstance(brief, dict) or len(json.dumps(brief, ensure_ascii=False)) > 180_000:
            raise PatentWorkflowError("技术方案须为不超过180KB的结构化对象。")
        inventions = json.loads((folder / "05_inventions.json").read_text(encoding="utf-8")).get("candidates", [])
        if not any(i.get("id") == candidate_id for i in inventions):
            raise PatentWorkflowError("技术方案必须绑定已经移交的发明候选。")
        if brief.get("candidate_id") != candidate_id:
            raise PatentWorkflowError("技术方案与已选定的候选编号不同。")
        known = set()
        for raw in json.loads((folder / "04_evidence.json").read_text(encoding="utf-8")).get("records", []):
            known.add(evidence_id(Evidence.from_dict(raw)))
        latex, review = render_brief(brief, folder, known_evidence=known)
        outfile = folder / "08a_technical_brief.tex"
        if outfile.is_symlink() or (folder / "08a_technical_brief.json").is_symlink():
            raise PatentWorkflowError("方案输出文件不允许是符号链接。")
        save_json(folder / "08a_technical_brief.json", brief)
        outfile.write_text(latex, encoding="utf-8")
        from .audit import append_audit_event
        append_audit_event(folder, stage="工程技术方案", action="生成白话工程方案及LaTeX模板",
                           actor="MCP 工具", role="系统",
                           payload={"candidate_id": candidate_id,
                                    "brief_sha256": sha256((folder / "08a_technical_brief.json").read_bytes()).hexdigest(),
                                    "tex_sha256": sha256(outfile.read_bytes()).hexdigest()})
        return {
            "saved": True, "candidate_id": candidate_id, "review": review,
            "json_artifact": "08a_technical_brief.json",
            "latex_artifact": "08a_technical_brief.tex",
            "conversion_authorized": False, "filing_authorized": False,
        }

    def figure_prepare(self, case_id: str, run_id: str, candidate_id: str,
                       wanted: list[str] | None = None) -> dict[str, Any]:
        """仅生成本案卷可编辑图源与哈希计划，绝不执行系统渲染命令。"""
        folder = self._folder(case_id, run_id)
        result = prepare_figures(folder, candidate_id=candidate_id, wanted=wanted)
        from .audit import append_audit_event
        append_audit_event(folder, stage="工程技术方案", action="生成可编辑图源与渲染计划",
                           actor="MCP 工具", role="系统",
                           payload={"candidate_id": candidate_id, "source_ids": [x["id"] for x in result["entries"]]})
        return result

    def figure_source(self, case_id: str, run_id: str, figure_id: str) -> dict[str, Any]:
        """按图源编号读取固定白名单内的可编辑工程原理图内容。"""
        folder = self._folder(case_id, run_id)
        plan, _ = read_figure_plan(folder)
        match = next((x for x in plan["entries"] if x["id"] == figure_id), None)
        if match is None:
            raise PatentWorkflowError("该研究运行没有此图源编号。")
        source = (folder / match["source"]).read_text(encoding="utf-8")
        return {"id": figure_id, "source": match["source"], "format": match["renderer"],
                "source_sha256": match["source_sha256"], "content": source,
                "geometry_proven": False}

    def figure_status(self, case_id: str, run_id: str) -> dict[str, Any]:
        folder = self._folder(case_id, run_id)
        try:
            plan, _ = read_figure_plan(folder)
        except PatentWorkflowError:
            return {"status": "not_prepared", "files": [], "filing_authorized": False}
        status = {"status": plan["status"], "files": [
            {"id": x["id"], "kind": x["kind"], "source": x["source"], "asset": x["asset"],
             "source_sha256": x["source_sha256"]}
            for x in plan["entries"]],
            "render_executed_by_mcp": False, "filing_authorized": False}
        record = folder / "08e_figure_render.json"
        if record.is_file() and not record.is_symlink():
            result = json.loads(record.read_text(encoding="utf-8"))
            status["worker_status"] = result.get("status", "unknown")
            status["rendered_count"] = len(result.get("rendered", []))
            status["failure_count"] = len(result.get("failures", []))
        return status

    def figure_sync(self, case_id: str, run_id: str, candidate_id: str) -> dict[str, Any]:
        """只验证渲染产物并更新图文，不启动浏览器、CAD 或 LaTeX。"""
        return sync_figures(self._folder(case_id, run_id), candidate_id=candidate_id)

    def brief_audit(self, case_id: str, run_id: str, candidate_id: str) -> dict[str, Any]:
        """独立审查工程技术方案，可双人签核归档，无须生成权利要求书。"""
        return inspect_brief(self._folder(case_id, run_id), case_id=case_id,
                             run_id=run_id, candidate_id=candidate_id)

    def conversion_status(self, case_id: str, run_id: str, candidate_id: str) -> dict[str, Any]:
        return conversion_status(self._folder(case_id, run_id), case_id, run_id, candidate_id)

    def draft_save(self, case_id: str, run_id: str, candidate_id: str, draft: dict[str, Any]) -> dict[str, Any]:
        folder = self._folder(case_id, run_id)
        require_conversion_approval(folder, case_id, run_id, candidate_id)
        if not isinstance(draft, dict) or len(json.dumps(draft, ensure_ascii=False)) > 300_000:
            raise PatentWorkflowError("申请正文须为有界的结构化 JSON 对象。")
        ideas = json.loads((folder / "05_inventions.json").read_text(encoding="utf-8")).get("candidates", [])
        idea = next((x for x in ideas if x.get("id") == candidate_id), None)
        if idea is None:
            raise PatentWorkflowError("申请稿尚未关联已经移交的技术方案。")
        patent_raw = json.loads((folder / "02_patents.json").read_text(encoding="utf-8")).get("records", [])
        patents = [Evidence.from_dict(x) for x in patent_raw]
        draft_issues = validate_draft(draft, patents, idea)
        save_json(folder / "08_application.json", {
            "status": "needs_human_review" if not draft_issues else "revision_required",
            "selected_candidate_id": candidate_id, "draft": draft,
            "submission_authorized": False, "draft_issues": draft_issues,
        })
        quality = inspect_research_case(folder)
        return {"saved": True, "selected_candidate_id": candidate_id,
                "draft_issues": draft_issues, "case_quality": quality["status"],
                "quality_blockers": quality["issues"], "filing_authorized": False}

    def quality(self, case_id: str, run_id: str, *, persist: bool = False) -> dict[str, Any]:
        folder = self._folder(case_id, run_id)
        return audit_research_case(folder) if persist else inspect_research_case(folder)


def create_server(service: PatentMCPService):
    """由 MCP SDK 生成正式 tools/list、JSON Schema、资源与提示词。"""
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:
        raise RuntimeError("请安装可选依赖：pip install -e '.[mcp]'（MCP Python SDK v2）。") from exc
    server = MCPServer(
        "Mechanical_Patent", version="0.2.0",
        instructions="简体中文机械发明研发。必须先获外发审批再检索，引用真实权要；构思与评分均为假说；最终须工程师及专利人员签核。",
    )

    @server.tool()
    def patent_capabilities() -> dict[str, Any]:
        """获取支持的研究能力、技术轴、评价字段和法律限制。"""
        from .paper_sources import paper_source_catalog
        return {"service": "Mechanical_Patent", "project_id": service.project.project_id, "contract_version": "1.6",
                "paper_sources": paper_source_catalog(),
                "methods": list(METHODS), "axes": list(AXES), "scores": list(SCORE_FIELDS),
                "agent_llm_api_required": False, "transports": ["stdio", "streamable-http"],
                "submit_to_patent_office": False,
                "security": "保密审批先于真实检索；HTTP 仅回环监听，由前置 OAuth2/OIDC 网关鉴权。"}

    @server.tool()
    def patent_project_info() -> dict[str, Any]:
        """读取当前绑定的项目身份及该项目独立数据库信息。"""
        return service.project.describe()

    @server.tool()
    def patent_case_create(case_id: str, direction: str, confidentiality: str = "秘密") -> dict[str, Any]:
        """创建一个可审计的研发案卷；不会向外网发送技术信息。"""
        return service.create_case(case_id, direction, confidentiality)

    @server.tool()
    def patent_case_status(case_id: str) -> dict[str, Any]:
        """查询案卷审批状态、工作流任务与可否外发检索词。"""
        return service.status(case_id)

    @server.tool()
    def patent_research(case_id: str, patent_queries: list[str],
                        paper_queries: list[str], limit: int = 10,
                        paper_sources: list[str] | None = None,
                        enrich_unpaywall: bool = False,
                        allow_paid_paper_apis: bool = False) -> dict[str, Any]:
        """选择论文检索平台；商业来源和保密数据外发需独立审批。"""
        return service.research(case_id, patent_queries, paper_queries, limit,
                                paper_sources, enrich_unpaywall, allow_paid_paper_apis)


    @server.tool()
    def patent_literature_search(
        case_id: str, query: str, kind: str | None = None, limit: int = 20,
    ) -> dict[str, Any]:
        """项目内混合索引检索，返回单篇 MD 证据编号和永久路径。"""
        return service.literature_search(case_id, query, kind, limit)

    @server.tool()
    def patent_literature_read(
        case_id: str, doc_id: str, max_chars: int = 24000,
    ) -> dict[str, Any]:
        """按文献证据编号恢复上次 AI/研究者写入的原文摘要与技术分析。"""
        return service.literature_read(case_id, doc_id, max_chars)

    @server.tool()
    def patent_literature_note(
        case_id: str, doc_id: str, analyst: str,
        basis: str, analysis: dict[str, str],
        source_positions: list[str] | None = None,
    ) -> dict[str, Any]:
        """保存白话解读、机械机理、反证与衍生方向；需标记阅读依据。"""
        return service.literature_note(
            case_id, doc_id, analyst, basis, analysis, source_positions,
        )

    @server.tool()
    def patent_literature_stats(case_id: str) -> dict[str, Any]:
        """文献累计规模、已分析数、未完分页任务及研究恢复文档位置。"""
        return service.literature_stats(case_id)

    @server.tool()
    def patent_literature_pending(case_id: str, limit: int = 30) -> dict[str, Any]:
        """批量读取尚未写入实质研究分析的文献队列，逐篇处理。"""
        return service.literature_pending(case_id, limit)

    @server.tool()
    def patent_literature_resume(case_id: str) -> dict[str, Any]:
        """恢复项目最新研究任务、假设、证据与后续方向。"""
        return service.literature_resume(case_id)

    @server.tool()
    def patent_literature_resume_save(
        case_id: str, analyst: str, markdown: str, expected_sha256: str,
    ) -> dict[str, Any]:
        """乐观锁更新研究快照并归档旧版，防止上下文压缩和并发覆盖。"""
        return service.literature_resume_save(
            case_id, analyst, markdown, expected_sha256,
        )

    @server.tool()
    def patent_literature_harvest(
        case_id: str, provider: str, query: str,
        max_documents: int = 200, max_pages: int = 4,
        allow_search_exposure: bool = False,
    ) -> dict[str, Any]:
        """已获保密许可才按官方 API 分页查询，增量生成每篇 MD。"""
        return service.literature_harvest(
            case_id, provider, query, max_documents, max_pages,
            allow_search_exposure,
        )

    @server.tool()
    def patent_run_create(case_id: str) -> dict[str, Any]:
        """本地离线新建一次研究运行，随后可导入其他授权检索服务的证据。"""
        return service.create_run(case_id)

    @server.tool()
    def patent_source_import(case_id: str, run_id: str, records: list[dict[str, Any]],
                             patent_queries: list[str] | None = None,
                             paper_queries: list[str] | None = None) -> dict[str, Any]:
        """导入第三方专利或论文元数据及权利要求，来源一律标记待核验。"""
        return service.import_sources(case_id, run_id, records, patent_queries, paper_queries)

    @server.tool()
    def patent_case_artifact(case_id: str, run_id: str, artifact: str) -> dict[str, Any]:
        """在白名单内读取结构化案卷证据、研究报告与申请底稿。"""
        return service.read_artifact(case_id, run_id, artifact)

    @server.tool()
    def patent_idea_plan(case_id: str, run_id: str, parent_id: str = "",
                         limit: int = 6) -> dict[str, Any]:
        """产生分叉研究任务，由当前 AI 自己生成具体技术方案。"""
        return service.fission_plan(case_id, run_id, parent_id, limit)

    @server.tool()
    def patent_idea_register(case_id: str, run_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
        """保存 AI 提出的完整机械/控制发明假说、父系与证据，不伪造验证结果。"""
        return service.fission_register(case_id, run_id, candidate)

    @server.tool()
    def patent_idea_evaluate(case_id: str, run_id: str, candidate_id: str,
                             scores: dict[str, float], review: str, countersearch_refs: list[str],
                             physical_principle: str, engineering_risks: list[str]) -> dict[str, Any]:
        """记录逐项研究评分、真实证据编号、物理依据与风险。"""
        return service.fission_evaluate(case_id, run_id, candidate_id,
                                        scores, review, countersearch_refs,
                                        physical_principle, engineering_risks)

    @server.tool()
    def patent_idea_frontier(case_id: str, run_id: str, top_k: int = 8) -> dict[str, Any]:
        """质量—多样性筛选：每类技术轴和创新方法优先保留一个方案。"""
        return service.fission_frontier(case_id, run_id, top_k)

    @server.tool()
    def patent_idea_promote(case_id: str, run_id: str, candidate_id: str) -> dict[str, Any]:
        """将证据关联的候选交给反证/工程/撰写流程；不授予专利法律结论。"""
        return service.fission_promote(case_id, run_id, candidate_id)

    @server.tool()
    def patent_countersearch_record(case_id: str, run_id: str, candidate_id: str,
                                    feature: str, source_id: str, quote: str) -> dict[str, Any]:
        """逐特征保存对比文献引用，并核验引文确在存档权利要求文本中。"""
        return service.countersearch_record(case_id, run_id, candidate_id, feature, source_id, quote)

    @server.tool()
    def patent_engineering_record(case_id: str, run_id: str, candidate_id: str,
                                  physical_principle: str, equations_and_units: list[str],
                                  assumptions: list[str], failure_modes: list[str],
                                  falsification_tests: list[str],
                                  verification_status: str = "hypothesis_only") -> dict[str, Any]:
        """记录物理机制、量纲、失败模式及证伪测试；不伪造真实仿真/试验。"""
        return service.engineering_record(case_id, run_id, candidate_id, physical_principle,
                                          equations_and_units, assumptions, failure_modes,
                                          falsification_tests, verification_status)

    @server.tool()
    def patent_brief_save(case_id: str, run_id: str, candidate_id: str,
                          brief: dict[str, Any]) -> dict[str, Any]:
        """保存工程人员看得懂的技术方案并输出按需组合的LaTeX，不生成权利要求。"""
        return service.brief_save(case_id, run_id, candidate_id, brief)

    @server.tool()
    def patent_figure_prepare(case_id: str, run_id: str, candidate_id: str,
                              wanted: list[str] | None = None) -> dict[str, Any]:
        """从已保存的研发事实中生成可编辑 draw.io/Mermaid 图源和安全渲染计划。"""
        return service.figure_prepare(case_id, run_id, candidate_id, wanted)

    @server.tool()
    def patent_figure_source(case_id: str, run_id: str, figure_id: str) -> dict[str, Any]:
        """按图示ID读取可编辑图源及SHA，不提供任意文件路径读取。"""
        return service.figure_source(case_id, run_id, figure_id)

    @server.tool()
    def patent_figure_status(case_id: str, run_id: str) -> dict[str, Any]:
        """检查图示源和隔离渲染器结果，不执行外部程序。"""
        return service.figure_status(case_id, run_id)

    @server.tool()
    def patent_figure_sync(case_id: str, run_id: str, candidate_id: str) -> dict[str, Any]:
        """核实所有PDF输出的哈希后将配图写入新的工程说明书版本。"""
        return service.figure_sync(case_id, run_id, candidate_id)

    @server.tool()
    def patent_brief_audit(case_id: str, run_id: str, candidate_id: str) -> dict[str, Any]:
        """阶段A工程技术方案独立质检、双人评审验签和结案状态。"""
        return service.brief_audit(case_id, run_id, candidate_id)

    @server.tool()
    def patent_conversion_status(case_id: str, run_id: str, candidate_id: str) -> dict[str, Any]:
        """只读检查真实企业审批签名是否允许由技术方案转换为专利申请底稿。"""
        return service.conversion_status(case_id, run_id, candidate_id)

    @server.tool()
    def patent_draft_save(case_id: str, run_id: str, candidate_id: str,
                          draft: dict[str, Any]) -> dict[str, Any]:
        """仅可信企业审批允许申请转换后保存权项、说明书与摘要。"""
        return service.draft_save(case_id, run_id, candidate_id, draft)

    @server.tool()
    def patent_quality_audit(case_id: str, run_id: str, persist: bool = False) -> dict[str, Any]:
        """检查案卷来源、反证、工程和申请文件；始终要求真人审核。"""
        return service.quality(case_id, run_id, persist=persist)

    @server.prompt()
    def autonomous_mechanical_patent(direction: str) -> str:
        """提供一次指令完成全球检索、想法裂变、反证与中国发明撰写的中文工作流。"""
        return (
            "请以企业级机械发明专利研发智能体身份处理以下技术任务：" + direction
            + "\n操作：先调用 patent_capabilities / patent_case_create；遵守保密审核。"
            + "利用 patent_research 获取实际专利及论文记录；若缺 EPO 凭证，调用 patent_run_create 并使用宿主授权检索工具获取真实文献，随后通过 patent_source_import 导入待核验资料。"
            + "调用 patent_index_refresh 保持项目索引可追溯，patent_frontier_scan 发现公开前沿，并通过 patent_variant_plan 研究已公开专利的变种；"
            + "利用 patent_manuscript_create/edit 保存分节 LaTeX 技术论文，引用写入真实 BibTeX；"
            + "按 patent_idea_plan 执行多方法、多代候选裂变，调用 register/evaluate/frontier；"
            + "针对候选用专利权利要求全文逐特征反证，记录理论计算与失效模式；"
            + "默认用 patent_brief_save 输出工程技术方案，可调用 patent_figure_prepare 生成可编辑 draw.io/Mermaid 源图，由企业隔离worker导出PDF后调用 patent_figure_sync；只有用户申请决定及企业验签通过才可写专利申请文本；"
            + "执行 patent_brief_audit 审阅工程方案，双人签核可直接结案；独立批准后才可运行 patent_draft_save 与 patent_quality_audit。"
            + "模型推断须标记假说，未经授权不得发起外部查询或专利申请。"
        )
    from .mcp_extensions import register_project_research_tools
    register_project_research_tools(server, service)
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mechanical_Patent 官方 MCP SDK v2 服务器")
    parser.add_argument("--workspace", type=Path,
                        default=Path(os.getenv("PATENT_MCP_WORKSPACE", "./private_patent_workspace")))
    parser.add_argument("--project-id", default=os.getenv("PATENT_MCP_PROJECT_ID"),
                        help="必须显式绑定项目，项目之间隔离 SQLite、论文和证据目录")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if not args.project_id:
        parser.error("必须传 --project-id 或 PATENT_MCP_PROJECT_ID，不能部署跨项目共享数据库。")
    if args.transport == "streamable-http" and args.host not in {"127.0.0.1", "::1", "localhost"}:
        parser.error("MCP HTTP 强制绑定回环地址；企业远程接入请经过 HTTPS + OIDC 网关。")
    service = PatentMCPService(args.workspace, project_id=args.project_id)
    server = create_server(service)
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="streamable-http", host=args.host, port=args.port,
                   stateless_http=True, json_response=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())