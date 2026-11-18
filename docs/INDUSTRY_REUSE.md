# 行业开源项目取长补短：实际融合决策与企业验收

核查日期：2026年11月18日。所有介绍均以本仓库锁定的 Git SHA、上游许可证、README、实际源代码和复测结果为准。开源源码、商业专利数据和第三方数据集是三种完全不同的授权对象。

## 1. 最值得吸收的行业模块

| 组件 | 官网 / GitHub | 可复用的长处 | 本仓库融合情况 | 边界 |
| --- | --- | --- | --- | --- |
| Patent Client Agents | https://github.com/parkerhancock/patent-client-agents | MCP/Python 多国知识产权数据工具，来源明确，审查记录、权项和同族检索 | Apache-2.0 完整源码固定在 external/patent-client-agents；MCP 结构化导入契约已实现；Codex 可自行连接本地 MCP | 开源工具不等于免费数据库访问权限；托管 MCP 不得接收未公开发明 |
| patentkit | https://github.com/j-hedtke/patentkit | 专利统一数据模型、权项解析、逐特征证据、混合检索和指标体系 | Apache-2.0 完整源码固定在 external/patentkit；共享 Evidence 规范和独立反证可逐步适配 | 其可选 AI 推理和网页采集不能绕开本项目既定安全和 Crawl4AI 边界 |
| PatentAgentBench | https://github.com/patsnap/PatentAgentBench | 检索、权项对照、专利起草、审查答复等八类评测任务 | 自有离线评测模块、企业合法标注集许可门禁、CI 单元测试；采用任务划分作为后续 QA 体系参考 | 仓库 MIT 不代表各子数据集也一律 MIT；不复制未确认条款的题库 |
| PatSnap patent-bench | https://github.com/patsnap/patent-bench | Hit/Recall/MRR 等统计指标、严格全部样本计分、同族判断 | 自有 Python 零依赖评测实现，未复制第三方受限制数据 | 数据集 CC BY-NC 4.0，企业商业评测默认拒绝；部分指标代码另有 Apache-2.0 许可 |
| Docling | https://github.com/docling-project/docling | 本地文档结构、段落、页码和坐标定位，可导出 Markdown/JSON | 可选 pdf 依赖、本地离线模型资源及页码/哈希提取适配器，CI 使用 mock 测试 | 代码 MIT，模型权重许可独立；无真实原文使用授权禁止处理，结果仍待人工核查 |
| GROBID | https://github.com/grobidOrg/grobid | 学术论文元数据、参考文献、引用关系和 TEI XML | 后续论文引用网络路线图，尚未在运行时引入 | 部署 Java 服务、资源消耗和许可证细项先核查；只处理获授权文件 |
| BGE-M3 / FlagEmbedding | https://github.com/FlagOpen/FlagEmbedding | 跨语言语义向量、稀疏/稠密检索和重排序 | G1/G4 混合检索备选；当前用户不需安装模型或另付推理 API | 模型权重、算力、使用范围与当前 AI 客户端完全区分；先在真实中英机械专利语料评测 |
| 原有中文专利交底 Skill | https://github.com/handsomestWei/patent-disclosure-skill | 发明专利交底、权利要求、申请文件和审查口径 | 已固定源码，充当中文专利撰写基础 | 自带轻量 CNIPA 查新不足以代替系统化全球检索 |
| IdeaForge / Trinno | 固定在 external/ | TRIZ、SCAMPER 证据图谱、假说与可证伪实验 | 已有简体中文创新 Agent、案卷知识关联、质量规则 | 单一模型角色拆分不等于独立多模型验证；结果须工程师复核 |

## 2. 本轮直接写入的实际功能

A. 真实 MCP 工具数据统一进口：
- src/mechanical_patent/mcp_bridge.py 将有许可的结构化 MCP 工具返回转换为 Evidence；
- tool_family 仅限经评估的 Patent Client Agents / patentkit，检查原始公布号、URL、工具来源和授权；
- 禁止 HTML 爬虫输出伪装结构化 API；网页内容统一由 Crawl4AI 采集；
- 证据永远先是待核验：原始公开 PDF/权利要求需要独立核对后才可在案卷中确认；
- CLI：mechanical-patent mcp-import。

B. 真实 PDF 本地可选解析：
- src/mechanical_patent/pdf_extraction.py；
- 校核本地 PDF 文件格式和大小，读取真实原始文件并计算 SHA-256；
- 通过 Docling 离线版本抽取段落、标签、实际页码、可得坐标；
- 未配好本地 Docling 或离线模型资源时明确失败；绝不为了启动程序自动联网下载模型；
- 产出一直保持待核验状态，实际法律引用须打开原始公开 PDF 核对；
- CLI：mechanical-patent parse-pdf。

C. 公开、严格、可复现的专利检索质量评测：
- src/mechanical_patent/benchmarks.py；
- 企业拥有合法使用权的 JSONL 标注集，按同族定义真值；
- Hit@K、Recall@K、MRR@K，其中未返回案例在所有分母中计零；
- CC BY-NC、未知许可证、无企业用途批准的题库一律阻断；
- 提供“纯合成”测试样本，不声称代表实际全球专利检索质量；
- CLI：mechanical-patent benchmark。

D. Codex 本地自动发现：
- skills/ 为业务自有 Skill 的源目录；
- .agents/skills/ 是 Codex 实际扫描的仓库级技能目录；
- scripts/sync_skill_mirrors.py 负责镜像更新/CI 检测；
- 14 个简体中文 Skills 必须保持一致，以避免用户克隆项目后 Codex 不认识它们。

## 3. 业内值得借鉴但现在不直接部署的内容

1. GROBID：待建立论文全文合法来源、DOI 核验与参考文献抽取测试集，再单独运行解析服务。
2. BGE-M3：待建立 100 条以上中英机械专利黄金标注集后，对比关键词、BM25、稠密、稀疏、混合和重排序的准确度/延迟/成本。
3. PatentAgentBench：逐任务核实数据集具体授权，建立权利要求支撑、Claim Chart、专利草稿和审查意见等能力的评审 Rubric。
4. 多租户高可用：SQLite 现有单机事务和任务租约，未来升级 PostgreSQL + 项目权限、任务队列和 Outbox、不可篡改证据存储与审批系统。
5. 官方专利数据：CNIPA、USPTO ODP、EPO OPS、WIPO 授权数据和允许访问的商业 API。无源时记录缺口，绝不以 MCP 插件声称全球完整覆盖。

## 4. 工程验收和风险管理

- CI：多组数据/安全单元测试、技能镜像一致性、Python compileall、GitHub CodeQL；
- 数据：真实来源 URL、公布号/DOI、公开日期、原始 PDF 页面/段落、文献是否核验的状态；
- 安全：未公开发明外发审批、Web SSRF/redirect/DNS rebinding、未知外部工具数据注入；
- 许可：Git SHA、原 LICENSE、修改记录、安装依赖许可证和模型权重条款单独核查；
- 组织：工程师、真实发明人和专利专业人员分离审批，不以 AI 结论自动递交；
- 企业：部署 SLO、API 成本预算、恢复/回滚、权限和审计仍是下一轮独立验收任务。

## 5. 一条指令的使用示例

用户对 Codex 说：“检索全球高海拔消防泵汽蚀专利和学术论文，参考跨行业物理机理生成发明，先反证再写中国发明专利。使用仓库的 patent-autonomous、patent-industry-sources、patent-evaluation 与 patent-pdf-evidence 技能，保留真实来源和审核缺口。”

Codex 可从仓库根目录自动识别 .agents/skills/ 下的简体中文技能。真实专利 MCP 服务连接需要用户独立批准；没有数据库凭证时允许继续合规查找、记录缺口，但不能制造虚假的专利文献和法律结论。

## 6. 第三轮补充：开放引证网络与论文证据验证

- OpenCitations/oc_api：ISC 许可，固定 SHA d9448a6333f2eb9ed305cc05f52e9f287edf4e03；引证 API 关系、日期和引用 DOI。引用数据与代码许可各自独立，更多说明见 CITATION_DISCOVERY.md。
- Future-House/paper-qa：Apache-2.0，固定 SHA c692d0dfeac4a0296599f7fe21a253a58b7ac12a；重点复用多源论文元数据和证据定位/反证流程，当前项目不启动其默认外部模型运行时。
- google/patents-public-data：Apache-2.0，固定 SHA d3d08a00e41e411be11b8a1394dd6d84f1312463；仓库2026-04-18已归档，仅用于专利地图、权项抽取及 SQL 方法审查，运行时必须适配最新数据模式。
- 实际代码：citations.py 读取 OpenCitations v2 的一跳参考/被引关系；case_citations.py 保存批次和更新案卷图谱；lineage.py 加入“引用”关系，严格把新 DOI 标成待全文核对。
- 风险：开放引证网络并非完整学术文献全集；引用 DOI 不等于引用内容已得到核实。模型还须对每个候选进行专利和论文的反证检索。
