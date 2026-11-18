---
name: patent-literature-memory
description: "维护每个研发项目独立的专利/论文长期记忆：有界分页检索、每篇一份Markdown、来源出处、SQLite全文搜索、逐篇AI批注、断点恢复和跨会话研究快照。"
user-invocable: true
---

# 专利与论文项目级长期研究记忆

## 适用场景
每次收到专利检索、科研文献检索、技术发散、反证审查、老项目延续指令时主动使用本技能。尤其适用于单项目数百至数千篇的长期科研任务。

## 操作优先级
1. 先确认 case_id、项目根目录和密级，读取 knowledge/RESEARCH_RESUME.md 与 knowledge/INDEX.md；本地 SQLite 的数据永远优先于重新爬取。未取得保密审批或显式联网许可，完全拒绝查询词外发。
2. 使用 patent_literature_stats 和 patent_literature_search，按工程对象、失效机理、材料/结构、控制策略、边界工况、跨行业类比组合中英文检索式。
3. 按来源与预算进行分页官方 API 查询：OpenAlex/Crossref 检索论文，EPO OPS 检索专利；已授权的 Patent Client Agents 及其他正式数据源可通过现有 patent_source_import 批次导入。保留失败状态、游标、配额和未覆盖地区/年份。
4. 每篇发现立即生成稳定文献编号和单独 Markdown，归属项目 knowledge/documents/patents 或 papers。文献表结构及 FTS5 检索索引保存在该项目自己的 knowledge/literature.sqlite3。重复检索更新机器著录字段，但不得覆盖之前研究批注。
5. 执行 patent_literature_pending，按每批10–30篇分组做实质研读。对每篇依次 patent_literature_read，然后读取合法取得的摘要、权利要求、原文或已授权 PDF。用 patent_literature_note 写入可理解的白话总结、技术机理、关键结构与控制、参数、效果、缺点、矛盾、跨文献关联、后续创新和反证任务。
6. 每篇分析的 basis 必须取 metadata、abstract、claims、full_text 之一。使用 full_text 必须有可定位页码或章节；没有原文仅允许输出“根据摘要暂时推断”，不能断言实验数值、权利要求覆盖或已核验全文。
7. 每一轮研读结束，读取 patent_literature_resume 最新摘要和 SHA256，再以 patent_literature_resume_save 乐观锁更新项目问题、已核实事实、关键引用、候选创新、重大反例、当前优先级、待审风险、下一批搜索式、下次恢复入口。遇到版本冲突必须重新读取并合并；前版会写入 resume_history。
8. 生成技术方向前先专利/论文双向引证、同族合并和反证检索；取得核心技术特征差异后再调用 patent-idea-fission 和工程技能。是否已经符合专利创造性只能经有证据的专业复核判断。

## 目录契约
项目根目录下 knowledge/RESEARCH_RESUME.md 为跨会话入口；knowledge/INDEX.md 是每篇 MD 链接总目录；knowledge/literature.sqlite3 是独立索引与分页检查点；knowledge/documents/patents 和 knowledge/documents/papers 中每份 MD 保留原始链接、检索时间、出版标识、摘要、权要、阅读依据和分析版本；knowledge/resume_history 保留旧项目总结。

研究任务可以从 MCP、CLI 或导入的离线 JSON 触发。CLI 示例：

    python -m mechanical_patent literature --project-dir cases/X01 stats
    python -m mechanical_patent literature --project-dir cases/X01 search --query "消防泵汽蚀"
    python -m mechanical_patent literature --project-dir cases/X01 pending --limit 20
    python -m mechanical_patent literature --project-dir cases/X01 harvest --provider openalex --provider crossref --query "cavitation pump NPSH" --workflow-case-id X01 --workspace-db private/index.sqlite3 --max-documents 1000 --allow-search-exposure

## 质量控制
- 每一个检索批次必须区分发现条数、唯一文献数、已获摘要数、可获取原始全文数、已实质解读数、反证命中数。
- 千篇元数据不等于千篇全文阅读，不等于全球检索穷尽；对未访问数据源列出技术盲区。
- SQLite FTS5 trigram 用于中文/英文子串检索；缺失 FTS5 时降级 LIKE。向量语义检索属于可选升级模块，不得宣称现有代码已支持向量检索。
- 数据库和 Markdown 都属于保密研究资产；严禁提交到 Git 仓库，禁止公开检索词、原始 PDF、企业 BOM 和未申请技术方案。
- 现阶段项目级文献库隔离，MCP 的工作流任务调度仍共用中心目录的 index.sqlite3。生产级企业隔离需要企业身份、权限和加密存储边界。
- 来源元数据合法获取和开放全文版权许可需分别审查；EPO OPS 的公平使用限速不可通过增加并发绕过。

## 已授权论文全文索引的增量合并（2026-11-19）

项目级 `knowledge/literature.sqlite3` 在旧文献表增量保留 `pdf_url` 和 `metadata_json`；全新 `fulltext_jobs/fulltext_events/fulltext_blocks` 及全文 FTS5 只归属当前案例。工作流先 `fulltext-status`，再按公司版权记录及保密审批执行 `fulltext-plan` 和 `fulltext-process`，可使用 `fulltext-pending` 做恢复队列。机器解析记录以稳定 SHA 标记附加至原单篇 EV-*.md，重复导入保留人工批注与断点。MCP 通过 `patent_literature_fulltext_status/search/pending` 按需读取原文证据，不提供未经身份认证的外部下载工具。详见 docs/FULLTEXT_PIPELINE.md。


## 论文 DOI 来源谱系与合规全文记忆（2026-11-19）

不同 API 分批返回相同 DOI 时，合并 DOI、作者、原生 ID、来源列表及合法 PDF 候选，保留原始提供方和每次检索日期；不以标题猜测无 DOI 文献同一性。文学研究批注/逐页解析的持久区与机器元数据分开，避免刷新覆盖。最新版权状态冲突时失效优先，等待人工许可复核。每次 AI 复用 RESEARCH_RESUME.md 与来源 MD，先检查过去已阅读内容。OA 地址查询用 oa-enrich，真正下载与解析参照 patent-fulltext-processing Skill，技术结论需独立原文核验。
