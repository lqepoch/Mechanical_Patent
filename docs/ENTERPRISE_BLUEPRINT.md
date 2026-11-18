# Mechanical_Patent 企业级专利研发工作流蓝图

方案日期：2026-11-18。当前属于可运行的工作流/证据工具基础，本文同时列出尚待实施的企业级生产要求。

## 一、系统目标与判断

用户只需输入一次机械技术难题，当前 ChatGPT、Codex 或其他已获授权的 AI 客户端便可承担检索、创新、反证、工程推演和中国发明专利撰写。Python 程序负责资料获取、文献归档、任务领取与状态恢复、审计、质量校验。无须安装模型服务器或配置任何 LLM API。

知识产权质量的核心是：搜索真实、信息可追溯、方向可证伪、技术方案能够由本领域技术人员实施，权利要求有说明书支持，申请递交前经过工程师与专利专业人员复核。

## 二、完整工作流与门禁

用户指令 → 保密分级（G0）
→ 专利检索与论文检索并行
→ 正式来源及文献真实性核验（G1）
→ 技术路线评审（继续 / 改换方向 / 终止）
→ 多路线创新（TRIZ、SCAMPER、FMEA、跨学科）
→ 各方案专利及论文再次反证检索（G2）
→ 理论计算、结构控制方案、失效及工程验证计划
→ 中国发明专利交底、权利要求、说明书、摘要及附图（G3）
→ 独立 QA、真实工程师与专利专业人员签核
→ 人工提交决定（G4）。

各阶段写入统一案卷、证据 ID 和执行日志。发生新证据、错误或不合理方案时，记录原因并开启新一轮检索，保留旧轮证据和否定结论。技术方向评审与真实权利要求核验缺失的情况必须标注。

## 三、多 Agent 编排

agents/ 下的 13 个简体中文角色负责总控、保密、专利、论文、知识图谱、创新、反证、工程、布局、撰写、附图、QA 和案卷治理。AI 宿主支持并行 Agent 时，使用持久任务队列领取工作；不支持时，当前 AI 在同一会话中按角色和阶段分开进行，每项形成独立结论，并披露自审独立性有限的事实。

本地现已引入 SQLite 事务任务队列：
- 案卷 ID、阶段、修订版本和保密等级；
- 十二个具备依赖关系的任务，专利检索与论文检索并行；
- 按角色领取、租约、超时重领、重复领取防护及失败重试阻断；
- 每个任务的结构化结果与完成记录；
- 方向评审（继续/改变方向/终止），改变方向后生成全新轮次；
- 证据核验与文献覆盖缺口记录；
- 本地检索索引、PDF 原文链接与可选归档；
- JSON 质量门禁与本地审计事件哈希链。

本地数据库尚未具有多租户、SSO、真正授权校验和跨机高可用，正式企业部署须迁移至 PostgreSQL、项目级 RBAC/ABAC、队列和事务 Outbox，并接入可验证的人类签名或企业工作流审批系统。

## 四、专利证据库：本地索引、公开原文在线核对

资料使用两层保存策略：

1. 本地：专利公开号、标题、摘要、公开日期、著录来源、原始 URL、论文 DOI、核验状态、索引时间和证据 ID；使用 SQLite 快速按标题/标识/摘要查找。
2. 原始公开 PDF：public_pdf_url 保存官方或可核验的公开 PDF 链接；用户可以直接打开原文进行二次核查。
3. 可选 PDF 本地副本：有明确权限、网站许可和下载必要性时，使用仅接受合法 HTTPS PDF 的归档工具下载，以 SHA-256 命名，去重并保存来源和文件哈希。数据库保留在线链接，不会改成只指向本地文件。

没有合法 PDF 直接地址时，仅保存原始文献详情 URL，避免编造 PDF 下载链接。原文查看应优先采用真实公开 PDF，检索摘要只能用于初筛。

PDF 下载使用确定性二进制传输；普通 HTML 页面统一由 Crawl4AI 在网站许可范围内抓取。PDF 下载需限制大小、阻断重定向、验证 PDF 文件头与内容哈希；生产环境还必须有浏览器/进程隔离和出站代理级 SSRF 防护。科研论文全文下载单独考虑出版社许可。

## 五、证据状态和权利要求链路

每个证据有来源、专利号/DOI、公开日期、检索日期、元数据核实状态和人工复核状态。用户从文件导入的资料即使声明已验证，仍按未核验源处理。

方向与创新链路为：
技术问题 → 真实专利证据 / 论文证据 → 物理机理
→ 发明候选（方法、结构/控制细节、区别特征）
→ D1/D2/论文反证锚点
→ 工程公式、工况、失效与证伪计划
→ 独立权利要求及实施例支持
→ 独立质检与人工审批。

技术知识关联图谱保存节点和关系，而非仅输出一段总结。文本匹配与证据 ID 合法性检查仅是静态 QA；真实性、完整性及法律创造性还需专业审查。

## 六、真实部署路线

G0 研究工具可靠化：MIT/Apache 开源来源/许可证、中文 Skills、测试、工作流图、模型无关。
G1 文献覆盖：CNIPA、EPO OPS、USPTO、PCT/许可服务，论文 OpenAlex/Crossref/arXiv，完整权利要求和来源覆盖统计、增量更新。
G2 创新与工程：多 Agent 并行协调、可解释图谱、反证重检索、真实 CAD/ANSYS 和可重复技术试验。
G3 申请文件：完整中国发明专利交底、权要、说明书、摘要、附图、专业法务和工程人员审签。
G4 生产系统：PostgreSQL/pgvector、项目权限和企业 SSO、加密对象存储、审计、SLO、RPO/RTO、灾备、可观测性、API 费用与限速、两云适配及升级回滚。

当前分支的 SQLite 为本地可运行实现，提供确定性任务交接与检索索引；并不代表已完成 G4 级多用户生产平台。

## 七、使用示例

创建研发案卷：

    python -m mechanical_patent workspace --db cases/index.sqlite3 create --case-id PUMP-001 --direction "高海拔消防泵快速吸水"

查看待办与阶段：

    python -m mechanical_patent workspace --db cases/index.sqlite3 status --case-id PUMP-001

按角色领取任务：

    python -m mechanical_patent workspace --db cases/index.sqlite3 claim --case-id PUMP-001 --role "保密与权限智能体" --actor "实际执行人"

任务结果填入 JSON 文件后提交：

    python -m mechanical_patent workspace --db cases/index.sqlite3 finish --task-id 1 --actor "实际执行人" --result-file privacy.json

AI 双检索流程自动创建索引：

    python -m mechanical_patent research --direction "消防泵进水系统" --patent-query "vacuum priming system" --paper-query "pump cavitation NPSH" --allow-search-exposure --case-dir cases/research-001

检索现有文献：

    python -m mechanical_patent workspace --db cases/index.sqlite3 search --query "消防泵"

查询在线原文及本地副本：

    python -m mechanical_patent workspace --db cases/index.sqlite3 source --case-id PUMP-001 --doc-id 真正的证据编号

获真实网站许可、用户授权后保存原始公开 PDF：

    python -m mechanical_patent workspace --db cases/index.sqlite3 archive --case-id PUMP-001 --doc-id 真正的证据编号 --pdf-dir patent_library --allow-domain 已授权PDF域名 --authorized

文献核验和下一轮技术方向评审详见 docs/WORKFLOW_OPERATIONS.md。

## 八、开源组件复用边界

handsomestWei/patent-disclosure-skill 提供完整中文交底/申请子技能；IdeaForge 的图谱与多方法创新、Trinno 的证伪实验记录、china-patent-figure-skill 的 STEP 原始结构附图、patent-template 的格式 QA 都采用固定版本子模块保存源码。可以在许可兼容和来源记录完整的条件下通过 scripts/vendor_upstreams.py 二次开发。AutoPatent 的方法已被独立参考，当前未确认其完整代码可直接重新分发。Crawl4AI 仅作为合规 HTML 采集引擎，不代替结构化官方/授权专利数据库接口。

## 九、组织治理、成本与合规

申请前有三重独立签核：资料真实性、工程可实施性、专利法律适格性。发明人和专利申请人身份归属需基于真实贡献/协议。FTO 和专利性独立评价。未公开的设计与检索词外发必须符合公司保密控制。

成本应按专利/论文数据源查询、Crawl4AI 页面采集、AI 客户端使用、CAD/ANSYS 求解、存储、审批工时和运维分别计量。SLA/SLO、RPO/RTO、审批时限、检索覆盖率均需在企业投入预算和负载评估后确定。
