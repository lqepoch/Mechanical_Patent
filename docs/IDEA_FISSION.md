# 想法裂变引擎：多代进化、Quality-Diversity 与工程反证

## 设计目标

解决机械发明研发中三个问题：
- 初次生成的构思容易沿着同一个熟悉路径重复；
- AI 只关注短期高分解，可能删除最有潜力的跨领域探索；
- 已失败或被专利反证的方案没有转化为下一代技术约束。

采用 TRIZ、SCAMPER、FMEA、形态分析、逆向约束、跨领域类比、第一性原理、组合创新，再通过不同技术轴和方法分组保留多样性。借鉴 AutoPatent 的阶段保存、IdeaForge 的知识关联、Trinno 的可证伪假设、Co-Scientist 的研究演化，以及 IDEAgent 的 Quality-Diversity 思路。

上述思想独立实现为 ideation_fission.py；第三方许可证不能凭 README 推定，未经许可绝不复制仓库源码。质量与多样性评分不代替中国《专利法》第22条和第26条中的法律判断。

## 裂变模型

每个想法都有 id、parent_id、generation、mechanism、enabling_details、distinguishing_features、evidence_ids、technical_axis、inventive_method、falsification_tests、evaluation、status。

- 根节点 generation=0；子代 +1；最高代数4。
- 每个研究运行实例最多120个节点，超量先筛选再生成。
- 完全相同的机理加技术特征由 SHA-256 指纹拒绝；语义近似的多方案仍由 AI 检查。
- 未引用来源可保存探索假设，但未取得真实文献和反证来源的候选不能移交申请。
- 质量评价包含七项评分（0至5）：技术可行性、公开充分度、差异假说、技术效果、应用价值、复杂性风险、现有技术冲突。
- 评价得分是资源分配启发式；Quality-Diversity 按技术轴×方法分组，每组优先保留当前最有意义的一个方案，不据此认定任何方案有创造性。
- 反证须使用真正获取的相关专利权利要求与论文，重要区别特征须有逐字来源锚点。
- 工程记录必须写明物理原理、量纲、假设边界、失效模式及可证伪实验。未执行真实实验时保持 hypothesis_only。

## 单条任务的多轮执行协议

1. 充分检索全球专利、论文、技术标准及工业公开资料，形成技术矛盾和当前已知手段。
2. 使用 patent_idea_plan 调度六种变换：矛盾反转、拆分重构、拓扑跃迁、异域迁移、失效倒推、跨代组合。
3. 当前 AI 分别提出具体可制造/可控制技术构思，通过 register 入库。
4. 按不同技术路线独立反证并 evaluate；留下被挑战的原方案和挑战原因。
5. 使用 frontier 选出不同机理的研究候选，继续跨代探索，直至边际收益下降、成本预算上限或工程证据否定。
6. 满足引用、反证及理论支持的候选 promote；在现有 06_countersearch、07_engineering、08_application 与 09_quality_gate 审核。
7. 记录申请主案、可组合从属方案和可能独立申请的其他方向。由真实专利专业人员评审单一性和权利要求范围。

## 企业生产升级

目前研究谱系在单个案卷 JSON 内持久化并使用本地文件排他锁。企业版需要：
- PostgreSQL 的 idea_candidate、idea_lineage、idea_evaluation、claim_feature、source_anchor、review_decision、patent_family_plan 表，以及行级组织/项目权限。
- 知识图谱投影可选 FalkorDB 或 PostgreSQL AGE，权威事实存于事务数据库，禁止把向量相似当成法律证据。
- 同源反证、独立专利专业评审、费用预算、队列租约、异常重试及审批人员身份。
- 支持按工程学领域配置力学、流体、材料、机电、控制等计算验证插件，计算结果关联可复核文件哈希。
- 专项检索评测：Hit@K、同族去重召回、权利要求对照来源准确率、工程假设复查一致性，以及多路线多样性。

## 2026-11-19：双亲交叉创新与失败记忆

在 `patent_idea_plan` 基础上新增两项确定性 MCP 工具：

- `patent_idea_crossovers(case_id, run_id, limit)`：对已评价、跨技术轴、未归档为失败的候选按研发评分配对，输出 AI 待论证的双亲研究问题。只输出组合任务，不直接生成所谓新颖技术。
- `patent_idea_reject(case_id, run_id, candidate_id, reason, learned_constraints, source_ids)`：保留被反证或工程试验否定的技术路线，记录真实来源编号和对下一代构思的负面约束。下次调用 `patent_idea_plan` 时返回 `avoid_failed_constraints`。

AI 以 `patent_idea_register` 保存交叉构思时，需显式提供 `inventive_method="组合创新"`、`parent_ids`（2–3 个不同父节点）、`synergy`（组合后的功能耦合机理）、`interface_definition`（机械/流体/电气连接与失效界面），以及现有必填结构、证据和试验字段。父构思至少横跨两个技术轴，代数按所有父节点最大代数 +1 计算，仍执行四代/120 节点预算。

新构思同时提供 `text_overlap_neighbors`（基于中文二元字组的文字重叠提醒）；这是轻量排查辅助信号，**既非语义近似定论，也不作为现有技术冲突或授权概率判断**。原有 SHA-256 完全重复门禁继续启用。失败路线可以产生新修复路线，但不能被直接重评、直接组合或直接移交申请。多亲本身份和协同接口会保留到 05_inventions.json；申请底稿仍必须经历独立反证、工程审核和人工签核。

依据研究方向：IDEAgent 的 Quality-Diversity 谱系、Open Coscientist 的假说竞赛与迭代、Idea Darwin 的交叉育种与失败保留。这里采用自主实现的数据结构和校验逻辑，未复制上述第三方源码。

### MCP 调用顺序示例

1. `patent_idea_plan` 规划并 `patent_idea_register` 登记多个单机制方案。
2. `patent_idea_evaluate` 对候选分别执行专利反证与工程评分。
3. `patent_idea_crossovers` 选取不同技术轴的亲本，AI 描述实际耦合路径、构件接口、边界工况后，以 `parent_ids` 注册新的组合方案。
4. 对失败路线调用 `patent_idea_reject`，保存约束和原始证据。下轮 `plan` 应显式避开已知失败条件。
5. 重复 `evaluate` → `frontier` → `promote`，并进行独立的权利要求对照、公开充分性和工程验证。不得自动声明获授权或者全球检索完备。

### 失败子案修复与可信检索门禁

已归档为 `rejected_research_route` 的候选可以作为单亲本“修复来源”，但新构思必须使用新的 ID，并显式提交 `parent_id`、`repair_of_failed_route=true` 和 `repair_rationale`，描述如何具体消除原来的失败约束。原失败假说持续留档，不允许直接重评或晋级；失败路线也不能参加多亲本交叉。

`patent_idea_promote` 现在额外要求案卷真实存在一份 `verified=true` 且带原文权利要求的专利来源，同时该来源必须出现在构思的 `evidence_ids` 与评审 `countersearch_refs` 中。导入的第三方检索结果默认 `verified=false`，无法通过这一安全门禁。此状态只证明来源被核验，并不代表权利要求反证已通过法律审查。
