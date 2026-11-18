---
name: patent-idea-fission
description: "面向机械发明专利自主研发，执行多代想法裂变、TRIZ/SCAMPER/跨领域迁移、质量—多样性筛选和逐候选反证，保存父子谱系并移交中国发明申请工作流。"
user-invocable: true
---

# 发明构思裂变与多方向优选技能

## 触发场景
用户提出“给我新的专利突破口”“想法裂变”“自动发现创新方案”，或总控专利工作流进入候选构思阶段时使用。当前 AI 会话负责创新推理，本仓库的确定性工具保存谱系和验证状态，无需另外配置模型 API。

## 工作步骤
1. 读取同一案卷的 02_patents.json、03_papers.json、04_evidence.json，确认已进行的真实检索、缺失渠道、权利要求是否取得。
2. 通过 MCP 工具 patent_idea_plan 建立独立任务，按机械、流体、控制、材料、制造、系统集成与跨领域机理展开。
3. 独立运行 TRIZ、SCAMPER、FMEA、形态分析、逆向约束、跨行业类比、第一性原理和结构组合；每个新构思用 patent_idea_register 保存技术原理、具体实施手段、假设、预期效果、证伪实验及来源编号。
4. 对值得继续的构思沿技术矛盾反转、结构拆分、拓扑变异、跨领域迁移、故障倒推及跨代组合再裂变。使用 parent_id 保留祖先；同一代避免结构雷同。单案最多120个构思、最多4代。
5. 独立反证角色使用真实公开专利权要与论文提出挑战。记录证据及物理基础，用 patent_idea_evaluate 填写七项评分；该评分只是研发资源分配信号。
6. 使用 patent_idea_frontier 按“技术轴×创新方法”保留多样性；重要路线可以保留未成熟探索项目。
7. 对具备具体可实施手段、已关联文献和反证来源的候选调用 patent_idea_promote；随后保存逐技术特征对照、工程理论分析和中国发明申请草稿。
8. 回到 patent-autonomous 的申请和审查阶段，遵守真人审核与保密审批要求。

## 失败及法律边界
- 缺少先前文献：可以生成探索假说，但不能导出已通过审核的专利结论。
- 检索冲突：记录具体否定原因，允许回到父节点重新裂变，不能直接删除失败历史。
- 多方法共识、评分、语义相似、Elo、Quality-Diversity 仅是研究启发式，不能证明法定创造性。
- 仿真、制造、实验未真实执行时标注“待验证”；允许理论上可推演的大胆构思，但必须有结构或控制可复现的实施路径。
- 一个发明方向可拆为多个子案；实际分案、优先权、申请单一性应由专利专业人员审核。

## 输出
05a_idea_fission.json、候选的父子关系、独立验证问题、质量—多样性候选前沿、移交至05_inventions.json的待审核发明，及完整人工复核清单。

## 供应商无关检索证据导入
若当前宿主已有授权检索 MCP，可先执行 patent_run_create，随后通过 patent_source_import 接入专利、论文记录；导入时主动标注未核验，必须打开原始公布专利和权利要求逐字核查，方可作为正式反证。

## 跨技术轴交叉与失败记忆（2026-11-19）

当不同技术轴的候选已分别通过研发评分时，调用 `patent_idea_crossovers` 获取交叉任务。AI 必须解释两种机理真正耦合的原因，填写 `parent_ids`（2–3个父构思），`inventive_method=组合创新`、`synergy`、`interface_definition`、结构/控制实施步骤和证伪试验，再调用 `patent_idea_register`。仅有并列功能或更改常规参数的组合仍需继续反证。不要让文本相似度参与法律创造性判断。

当已知文献或物理分析否定一条研究路线，调用 `patent_idea_reject` 保存 reason、learned_constraints、来源编号（可选）；下一轮 `patent_idea_plan` 必须读取 `avoid_failed_constraints` 并避免重复踩坑。失败路线保留且不能直接重评、晋级或参与交叉，必须新建有完整实施细节的修复子案。案例和契约见 docs/IDEA_FISSION.md、docs/MCP_INTERFACE.md。

### 失败子案修复与可信检索门禁

已归档为 `rejected_research_route` 的候选可以作为单亲本“修复来源”，但新构思必须使用新的 ID，并显式提交 `parent_id`、`repair_of_failed_route=true` 和 `repair_rationale`，描述如何具体消除原来的失败约束。原失败假说持续留档，不允许直接重评或晋级；失败路线也不能参加多亲本交叉。

`patent_idea_promote` 现在额外要求案卷真实存在一份 `verified=true` 且带原文权利要求的专利来源，同时该来源必须出现在构思的 `evidence_ids` 与评审 `countersearch_refs` 中。导入的第三方检索结果默认 `verified=false`，无法通过这一安全门禁。此状态只证明来源被核验，并不代表权利要求反证已通过法律审查。
