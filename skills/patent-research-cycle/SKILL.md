---
name: patent-research-cycle
description: "基于项目独立 SQLite 调度课题发现、专利论文并行检索、独立反证、理论或实验验证、成果分流的多 Agent 科研循环；支持任务租约、失败重试和版本化迭代。"
user-invocable: true
---

# 多 Agent 科研循环与证据质量门禁

## 使用场景与约束

当用户要求科研全过程执行、发散研究、专利与论文双路线产出、持续迭代时，先读取 AGENTS.md、docs/RESEARCH_CYCLE.md、docs/WORKFLOW_OPERATIONS.md。当前 ChatGPT、Codex、兼容 MCP 客户端承担专业推理；Python 负责状态、真实证据索引、哈希与过程约束。不得把十个任务创建成功当成十个 Agent 已实际运行。

## 操作步骤

1. 明确 project_id 和 case_id，优先通过 ProjectStorage / patent_case_create 创建受控案卷。先调用来源目录、课题目录、已有文献记忆，按项目边界开展保密分级。
2. 使用 patent_cycle_create 创建循环；patent_cycle_status 查 ready_steps，按步骤角色使用 patent_cycle_claim 领取。无项目真实保密审批时禁止外发任何未公开检索词；数据库里的 remote_used 字段仅记录真实检索是否发生，不能代替本项目原有权限门禁。
3. 课题发现保存 problem 和 measurable_goal。专利检索与论文检索完成真实查询或注明未覆盖源；MCP patent_research 和已授权数据渠道的结果先落当前案卷，再由资料核验人按公开原始来源登记已核验状态。
4. 证据整合只引用本案卷真实已核验 EV- 编号，并说明未检索到、全文缺失或样本偏差等局限。
5. 构思生成至少两条可实施、可证伪的独立候选，每条写 id、mechanism、enabling_details、falsification_tests 和 evidence_ids。反证 Agent 必须逐候选提交 risk、可追溯 evidence_ids 或明确证据不足。
6. 独立评审 Agent 与本轮构思 Agent、反证 Agent 不同，作出 advance / iterate / stop 并写理由。iterate 后由 patent_cycle_iterate 建立新一轮，不覆盖已完成任务；生产环境角色与审批必须绑定真实 IAM，不得依赖自报 actor。
7. 技术验证逐选定候选标记 L0-L5。L2 以上需要实际保存在当前项目的数据文件及 SHA256；即使文件存在，仍需区分计算记录、仿真结果、真实实验和人工复核，不能自我授予实测认证。
8. 成果分流只允许 technical_brief、paper_draft、patent_candidate、new_research，分别移交现有技术交底、LaTeX 论文、专利申请前评估和课题库。正式专利申请仍依赖原有独立签名审批；论文发表和实体试验也须真实人员核验。
9. 持续监测节点登记后续跟踪源、指标和下次人工执行计划。当前版本未实现外部定时器或无人值守监测；新资料触发后应创建经审批的新循环。

## CLI / MCP 与审计

CLI：mechanical-patent cycle --project-id <项目> --storage-root <私有路径> {create,status,claim,finish,fail,iterate,audit}

MCP：patent_cycle_create、patent_cycle_status、patent_cycle_claim、patent_cycle_finish、patent_cycle_fail、patent_cycle_iterate、patent_cycle_audit。

任务结果 JSON 需满足文档中当前 step 的强制字段。任务租约30–7200秒，最多3次尝试，超限进入阻断；不自动丢弃任何历史轮次。错误记录到项目级研究事件表，使用 SHA256 链核对，但同数据库哈希链并非独立可信时间戳或不可篡改的外部审计。

## 开源复用与下一阶段

本模块吸收 Google Co-Scientist 的生成—反证—选择—演化流程、LangGraph checkpoint / human-in-the-loop 思路；现阶段直接复用仓库自有 LocalPatentWorkspace / ProjectStorage，避免第二套数据库和模型服务。后续需要跨节点调度时，可在明确 SLO、幂等和失败语义后增加 Temporal 或 LangGraph 适配器；统一的项目任务协议应保持独立，不绑定供应商推理 SDK。生产暴露 MCP 前须先部署 OIDC/OAuth2 网关、项目级 ABAC 与审计日志保留机制。
