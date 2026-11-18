---
name: patent-paper-search
description: "联合 OpenAlex、Crossref、arXiv 等检索机械、材料、控制、流体等学术论文和跨领域科研方法，输出 DOI、技术机理和可迁移性证据并供专利反证使用。"
user-invocable: true
---

# 全球论文与科研文献检索技能

## 何时使用
技术路线研究、理论可行性核验、跨学科创新与候选方案反证。

## 责任智能体
参考 agents/README.md 中的第 04、05、07、08 号角色；运行环境可以用当前 AI 在同一会话中依次切换专业角色。

## 输入资料
物理问题、学科范围、中英文检索词、论文获取权限。

## 工作流程
1. 从用户技术难题展开物理现象、实验模型、数值方法、临界参数及异行业应用。
2. 分别检索 OpenAlex 与 Crossref；可用时补 arXiv 和有许可的学术资源。
3. 记录 DOI、发表日期、论文标题、来源机构、摘要可用性及全文阅读状态。
4. 对有合法权限的网页使用 Crawl4AI；对论文 PDF 采用专门文件工具阅读，不把元数据当成全文。
5. 抽取方程、量纲、适用边界、实验设计和反例，建立可转用技术原理的映射。
6. 每次发明后按新机理再次检索，寻找相关论文的否定证据。

## 必交付成果
03_papers.json、物理机理矩阵、科研来源和论文反证列表。

## 质量门禁与失败处置
没有看到论文全文时明确说明；绝对不能伪造 DOI、表格、实验参数；引用遵守版权和许可。

检索或工具调用失败时保存错误、实际检查范围和后续动作，记录到案卷的质量门禁；未经证实的假设不得当作事实。输出应使用简体中文，保留 DOI、专利公开号、IPC/CPC、技术公式和标准名称的原始准确写法。


## 引证网络深挖

当科研论文提出一个关键物理机制、控制策略或存在技术争议时，读取 patent-citation-discovery 技能。用真实 DOI 对参考文献和后续引用开展一跳扩展，将新 DOI 作为待验证线索，再通过 OpenAlex/Crossref/Crawl4AI 搜索真实原文和相反证据。不能根据引用次数判断专利创造性。


## 统一科研数据源与多渠道选择（2026-11-18）

1. 调用 `paper-sources` / MCP `patent_capabilities` 获取平台能力。按问题选择：广域关键词 OpenAlex + Crossref；引文扩展 Semantic Scholar；预印本 arXiv；生医 Europe PMC + PubMed；有许可的机构库 CORE；专利与学术引用协同 Lens。缺少来源时解释覆盖盲区。
2. 使用明确外发审批后的 `--paper-provider` 或 MCP `paper_sources`。默认 OpenAlex、Crossref、Semantic Scholar；`all` 跳过无商业授权或无凭证的 CORE/Lens；单独选择有价平台必须既提供 Key，又明确 `--allow-paid-paper-apis` / MCP `allow_paid_paper_apis`。
3. 通过 DOI 合并不同源元数据，统一记录来源列表、作者、引用数、发表日、OA、许可、候选 PDF URL。Unpaywall 仅做 DOI 合法 OA 位置补全（需真实邮件），未获取/核验全文时 `full_text_verified=false`。
4. 保存 03_papers.json、04_evidence.json、03_paper_memory/EV-*.md，每篇文献独立记忆元数据、可追溯链接、待核对全文的实验/公式和相反证据。优先在项目私有工作空间内持久化，通过 manifest 校验，不将内部技术与大文件提交到公共仓库。
5. 供应商异常、缺摘要、失效 PDF/非开放许可、限额及 429 时记录缺口并保留可用来源；仅在许可和审批后再下载原文，通过 Docling/PDF 审核核查页码、方程、实验结论，再联动专利权利要求反证。

接口及平台政策详见 docs/PAPER_SOURCES.md；不做各站未授权抓取，不擅自扩大用户明确的费用预算。
