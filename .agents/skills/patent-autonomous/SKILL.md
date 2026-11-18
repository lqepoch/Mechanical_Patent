---
name: patent-autonomous
description: "从自然语言技术问题出发完成全球检索、创意裂变、反证和机械可实施性论证；默认只交付供技术人员审查的白话 LaTeX 技术方案；明确申请并获企业授权后才进入申请文稿。"
user-invocable: true
---

# 自主专利研发总控：技术方案优先

## 默认交付
用户一句话提出机械/消防车辆/液压/控制技术难题时，当前 ChatGPT/Codex 负责创新推演，工具负责检索、证据、事实落盘和质量检查。**默认生成工程技术方案书（阶段 A）**；技术负责人确认创新点与工程实施路线后，即可归档本轮成果。技术评审通过 ≠ 法定新颖性或专利授权成立。

## 执行步骤
1. 读取 AGENTS.md、docs/ARCHITECTURE.md、docs/TECHNICAL_BRIEF_STANDARD.md，创建私有案卷，先完成保密分级。
2. 合规检索真实专利与论文；明确实际检索的国家、时间、权利要求全文覆盖和失效数据源。
3. 利用 TRIZ/SCAMPER/FMEA/跨领域机理形成多代备选，建立引用与因果谱系；不虚构专利号。
4. 对多候选进行专利+论文反证、技术矛盾与工程可行性审核。
5. 由人工/宿主 Agent 选定一个主要发明方案，保存原理、结构、连接关系、操作步骤、区别技术特征和待证伪试验。
6. 调用 skills/patent-technical-brief/SKILL.md 自适应选择 LaTeX 模板、CAD 线稿/draw.io/Mermaid 流程图/时序图和可用图表，MCP 用 patent_brief_save 输出 08a_technical_brief.json/.tex。
7. 对照证据库开展技术人员可读的风险与创新初筛，组织工程评审；通过后可直接完成本项目，未通过则迭代并保留旧版本。
8. **仅用户明确决定提出专利申请且可信外部审批系统验签通过**，再使用 patent-drafting-cn 和专利申请质量审核。专利局正式递交依旧需要真实授权人员。

## 企业级审查
区分技术事实、理论推断和真实台架证据；区分创造性初筛、工程可制造性、FTO、企业 IP 权属；由不同角色独立审核。保密未批准前不发送任何真实未公开技术到外部来源。模型服务不需要单独 API，外部检索供应商可能需要授权凭证。

## MCP 与异常处理
先调用 patent_capabilities；用户不提出申请决策时不要调用 patent_draft_save。研究错误、来源缺口、图纸缺失均如实保存在案卷，严禁静默降级后宣称通过。参考 docs/MCP_INTERFACE.md、docs/IDEA_FISSION.md 与 docs/WORKFLOW_OPERATIONS.md。

## 前沿专利与 LaTeX 主源（2026-11-18）
接到一条全新研发指令后，读取 patent-project-storage、patent-frontier-innovation、patent-latex-research 三项技能；锁定当前 project_id 的 SQLite；按实际供应商检索时间刷新专利索引及公开论文前沿。已有专利名称必须先核对真实公开号再裂变。研究论文独立保存分节 LaTeX 和 BibTeX；默认发明成果先生成白话工程技术方案；各个变种均按原权要逐技术特征反证，不能跳过工程实用性验证。


## 知识星图闭环：单文献、单项目、跨项目
开展双源检索后，必须读取 skills/patent-knowledge-atlas/SKILL.md。每批真实专利/论文入库后执行 atlas-index 或 MCP patent_knowledge_index；根据 patent_knowledge_graph 的单文献/单项目关联，追查相似专利原始权利要求、跨领域原理与尚未验证的假设。单文献自动记忆在 document_memory/generated/，工程与权要复核写在 document_memory/manual/，任何自动重建不得覆盖人工记忆。对已存正文的 AI 技术三元组使用 patent_knowledge_record_fact 并附可复核原文引句，标记待人工核实；引用数和文本相似不代表法律新颖性或创造性。跨项目图只能调用 global_public 公开投影；保密项目不得写入全局公开索引。可视化采用本地打包 Cytoscape.js，导出 JSON 由浏览器本地加载，禁止外部 CDN 上传案卷数据。
