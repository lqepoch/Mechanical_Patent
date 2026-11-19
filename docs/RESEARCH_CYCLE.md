# 多 Agent 科研循环：可恢复的课题—专利—论文研发编排

2026-11-19。源码：src/mechanical_patent/research_cycle.py、research_cycle_cli.py。示范性质：本地可执行的状态编排、质量门禁与交接基础；它不会自行调用语言模型、科研求解器、外部网络或自动监测任务。

## 系统边界

一个 project_id 对应 projects/<project_id>/patents.sqlite3，原有案卷 case_id 作为权限和文献主键。一个案卷可以有多个科研循环 cycle_id；一个循环内部可以有最多 20 轮迭代，每轮各有完整任务和输出。严禁用外部用户提供的 cycle_id 自动探索其他项目。MCP 服务进程只绑定一个项目；真实身份由外部受控网关验证，actor 仅为本地审计字段。

本模块借鉴 DeepMind Co-Scientist 对假设的生成、反思与进化，LangGraph checkpoint/interrupt，以及 Temporal 的持久执行经验，现阶段不引入其重型依赖。保留无 LLM API 的本地客户端模型：专业推理与调用真实工具由当前授权 AI 宿主执行，Python 实施确切的状态约束。

上游资料：
- https://deepmind.google/blog/co-scientist-a-multi-agent-ai-partner-to-accelerate-research/
- https://github.com/langchain-ai/langgraph
- https://docs.temporal.io/evaluate/understanding-temporal
- https://github.com/SakanaAI/AI-Scientist-v2
仅借鉴思路，未复制上游源码；需要实际集成第三方代码时另行审查 LICENSE、维护状态及 API 兼容性。

## 状态机与并行

    课题发现 ──┬─> 专利检索 ─┐
               └─> 论文检索 ─┤
                              ↓
     证据整合 → 构思生成 → 反证检索 → 独立裁决
                                           │
                      iterate ──> 新一轮任务（旧轮保留）
                      stop ─────> 终止并封锁下游
                      advance ──> 技术验证 → 成果分流 → 持续监测 → 已完成

研究任务状态：待领取、运行中、已完成、已阻断。获取租约使用 BEGIN IMMEDIATE 原子事务；30–7200 秒租约、最多三次尝试，过期可被新工作者领取；主动失败默认可重试，明确不可重试或耗尽上限进入阻断。受阻任务保留证据和日志，需人工调查，当前版本无自动解锁端点。

核心区别：独立审查不是自动评分。科研裁决要求与本轮候选构思及反证记录采用不同的执行者；生产端仍需企业可信身份认证。专利新颖性、创造性和 FTO 分开评估；即使科研流结束也不代表具备专利提交资格。

## 启动与恢复

    python -m mechanical_patent workspace --project-id projectA --storage-root /data create \
      --case-id CASE-01 --direction "机械设备的结构与控制研究"

    python -m mechanical_patent cycle --project-id projectA --storage-root /data create \
      --case-id CASE-01

    python -m mechanical_patent cycle --project-id projectA --storage-root /data status \
      --cycle-id RC-得到的编号

    python -m mechanical_patent cycle --project-id projectA --storage-root /data claim \
      --cycle-id RC-得到的编号 --role "课题发现智能体" --actor "受控客户端的实际执行者"

读取领取的 task_id。将本阶段所产生的结构化 JSON 存放在项目私有目录后：

    python -m mechanical_patent cycle --project-id projectA --storage-root /data finish \
      --task-id 1 --actor "受控客户端的实际执行者" --result-file /data/stage.json

    python -m mechanical_patent cycle --project-id projectA --storage-root /data audit \
      --cycle-id RC-得到的编号

CLI task_id 只是示意，实际以 claim 返回的编号为准。任务结束后再次 status，使用 ready_steps 查下一批可执行任务；专利和论文检索可以并发领取。所有外网访问仍需原有案卷本轮保密审批及显式联网许可；CLI 的 cycle 只处理本地研究记录，不能代替 patent_research 的强制出站门禁。

MCP 对应工具：patent_cycle_create、patent_cycle_status、patent_cycle_claim、patent_cycle_finish、patent_cycle_fail、patent_cycle_iterate、patent_cycle_audit。宿主可按角色调用已有 patent_research、patent_literature_resume/read、patent_idea_*、patent_countersearch_record、patent_engineering_record、patent_brief_save 和 patent_manuscript_* 等业务工具，再将受核验的总结提交至本循环。

## 各阶段 result JSON 契约

| step | 必需字段 | 严格要求 |
|---|---|---|
| 课题发现 | problem, measurable_goal | 问题和可测目标必须明确 |
| 专利检索/论文检索 | coverage_report, remote_used | remote_used 为 bool；远程使用须经原有保密审批 |
| 证据整合 | evidence_ids, limitations | 至少一个真实当前案卷已核验的 EV- 编号 |
| 构思生成 | hypotheses | 2–50 条，id、mechanism、enabling_details、falsification_tests、evidence_ids 必备 |
| 反证检索 | challenges | 每候选恰有一条，包含 hypothesis_id、risk、evidence_ids |
| 独立裁决 | decision, rationale, selected_ids | advance、iterate、stop；advance 至少选择一个真实候选；禁止由构思/反证人审理 |
| 技术验证 | assessments | 每个已选候选均须写 hypothesis_id、level、method、limitations、artifacts |
| 成果分流 | routes | 选定候选关联技术方案、论文草稿、专利候选或新课题 |
| 持续监测 | followups | 计划列表；本模块不会启动实际定时任务 |

最小候选示例：

    {
      "hypotheses": [
        {
          "id": "H1",
          "mechanism": "压力自适应的机械预紧",
          "enabling_details": "弹簧与凸轮组件随入口压力联动",
          "falsification_tests": ["测量不同压力下的接触力与泄漏率"],
          "evidence_ids": ["EV-当前案卷实际证据编号"]
        },
        {
          "id": "H2",
          "mechanism": "受控旁路减缓瞬态压力波动",
          "enabling_details": "旁路单向阀与压力传感器联动",
          "falsification_tests": ["测量阶跃加载时的压力超调"],
          "evidence_ids": ["EV-当前案卷实际证据编号"]
        }
      ]
    }

evidence_ids 必须与原有 LocalPatentWorkspace.documents 中的已核验编号一致；无法靠虚构编号满足门禁。已核验文献也可能只核实著录信息，不可自动等同全文事实核验或真实实验。检索覆盖报告必须披露国家、时间、语言、数据源与未知缺口。

验证级别为 L0 假设、L1 理论推导、L2 数值计算、L3 仿真、L4 实测、L5 复现。L2–L5 需要 artifacts 数组，数组元素为 {"path":"project_relative/path","sha256":"64位小写十六进制"}。程序读取项目内真实文件核对 SHA256、20MiB 大小和路径合法性，阻止跨项目读取；哈希存在不等于真实实验已获人工认可。外部设备、CAD 和求解器运行的审签需要后续独立集成。

## 生命周期、故障与审计

- 独立裁决为 iterate 时当前轮下游任务被阻断，调用 cycle iterate 可生成下一轮任务。旧轮 task/result/event 不删除。
- 独立裁决为 stop 时循环终止；无需伪造技术成果。
- 专利成果只能以 patent_candidate 类型流转。正式交底书审查、签名授权、论文出版和任何申请递交沿用原有独立工作流。
- 数据库记录任务结果 JSON 与 SHA256；同一项目内维护单向追加的事件哈希链。它能够提示普通误改，却无法替代 WORM 存储、外部可信时间戳、真实 IAM 审计。
- 当前没有分布式 worker、Webhook、定时监测、成果自动发表和自主驱动实验。生产升级时可增加 Temporal + PostgreSQL + 对象存储、OIDC/ABAC、Outbox、备份恢复、指标与告警；先做并发一致性、断电恢复、权限与来源真实性的集成测试。
- 现有 LocalPatentWorkspace 中的专利申请撰写序列维持兼容；新的科研循环是旁路编排层，不会自动推进或签署那条原有任务链。未来融合应统一门禁语义并避免双任务状态冲突。

## 测试与发布

    python -m unittest discover -s tests -p test_research_cycle.py -v
    python scripts/sync_skill_mirrors.py --check
    python -m unittest discover -s tests -v

CI 已加入专用科研循环测试任务；合并前须同时验证原有 MCP SDK v2 合约、LaTeX、容器与安全回归。
