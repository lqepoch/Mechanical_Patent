# Mechanical_Patent 标准 MCP 接口（2026-11-18）

## 目标与适用边界

本项目对外提供标准 Model Context Protocol（MCP）工具，而非专有模型 API。当前 ChatGPT、Codex 或其他 MCP Host 负责创造性推理；Python 工具负责真实专利/论文数据访问、证据、机械构思谱系、结构化发明申请草稿和确定性审核。接口采用 MCP Python SDK **v2**：本地 **stdio**；外部系统通过受控网关使用 **Streamable HTTP**。历史 SSE 仅为旧客户端兼容，不作为新接口设计。

**落地状态**：MCP 业务层已与本项目 SQLite 案卷、EPO OPS、OpenAlex/Crossref、构思裂变、逐项权利要求反证、工程假设、申请文档校验连接。全球全覆盖、完整中文多法域数据、真实 STEP 自动绘图、生产 OAuth2 身份服务和后台长任务队列仍需要后续集成。工具不会自动向国家知识产权局递交申请。

## 安装

Python 3.11+：

    python -m pip install -e '.[mcp]'

启动本地 MCP：

    python -m mechanical_patent.mcp_server --transport stdio --workspace /安全的私有目录/Mechanical_Patent

在可联网的受控主机部署 HTTP（仅回环）：

    python -m mechanical_patent.mcp_server --transport streamable-http --host 127.0.0.1 --port 8765 --workspace /安全的私有目录/Mechanical_Patent

HTTP 端点为 http://127.0.0.1:8765/mcp。公网、组织网络访问必须经过 TLS + 身份认证（OAuth2/OIDC/Keycloak）、访问权限和网络隔离网关；本代码拒绝监听 0.0.0.0。严禁将无认证的回环服务公开到公网或以负载均衡方式直接暴露。若有反向代理，必须保证代理到回环服务的链路仅由可信网关连接。生产环境还需要每个组织/项目独立的授权存储租户和真实用户身份审计。

### MCP 客户端配置示例（本地 Codex / 其他 Host）

    {
      "mcpServers": {
        "mechanical-patent": {
          "command": "python",
          "args": [
            "-m", "mechanical_patent.mcp_server",
            "--transport", "stdio",
            "--workspace", "/安全的私有目录/mechanical-patent"
          ]
        }
      }
    }

这是通用 MCP Host 示例；具体客户端（Codex、Claude Desktop、第三方业务系统）须按其配置文件格式设置。工作空间路径应放到私有目录且具有最小权限，绝对不能与公开 Git 仓库、CI 可访问目录共用。

## 能力契约

| MCP tool | 输入摘要 | 输出及安全边界 |
|---|---|---|
| patent_capabilities | 无 | 支持的方法、技术轴、评分尺度、协议 |
| patent_case_create | case_id, direction, confidentiality | 新建案卷；默认保密 |
| patent_case_status | case_id | 工作流状态及是否获外发批准 |
| patent_research | case_id, patent_queries, paper_queries, limit | 真实数据源检索；无当前轮保密批准即拒绝 |
| patent_case_artifact | case_id, run_id, artifact | 只读取14种白名单案卷文件；限制读取大小 |
| patent_idea_plan | case_id, run_id, parent_id, limit | 多方向裂变任务及物理/验证要求 |
| patent_idea_register | case_id, run_id, candidate | 保存机理、实施路径、父子关系、证据 |
| patent_idea_evaluate | case_id, run_id, candidate_id, scores, review, countersearch_refs, physical_principle, engineering_risks | 七项内部评分与反证假设 |
| patent_idea_frontier | case_id, run_id, top_k | Quality-Diversity 分组优选 |
| patent_idea_promote | case_id, run_id, candidate_id | 移交至发明候选文件，继续审核 |
| patent_countersearch_record | case_id, run_id, candidate_id, feature, source_id, quote | 引用必须存在于已取得且标记核验的专利权利要求正文 |
| patent_engineering_record | case_id, run_id, candidate_id, physical_principle, equations_and_units, assumptions, failure_modes, falsification_tests | 保存理论与待验证计划；严禁伪造仿真/实测 |
| patent_draft_save | case_id, run_id, candidate_id, draft | 保存权利要求、说明书、摘要及支持矩阵；检查审核问题 |
| patent_quality_audit | case_id, run_id, persist | 只读质量检查或持久化审计；不等于法律意见 |

MCP 同时提供 prompt 模板 autonomous_mechanical_patent(direction)，供调用端按一条指令调度全部步骤。MCP 本身没有擅自启动 ChatGPT、Codex 或其他模型服务的能力；宿主必须按提示运行专业 Agent。

### 研发案卷映射

1. 使用 patent_case_create 新建组织内唯一案卷。
2. 经过真实保密审批，将审批结果写入原有 LocalPatentWorkspace 工作流。可用现有 workspace CLI 的任务 claim/finish；MCP 禁止靠调用者自报角色跳过审批。
3. 使用 patent_research 创建 RUN-编号研究运行。没有 EPO OPS 数据凭证则明示缺口。支持调用其他授权检索 MCP 工具后，经本项目 mcp-import 命令将第三方结果导入为待核验资料。
4. 读取 02_patents、03_papers、04_evidence，进行多源差异分析；查询少、跨语种覆盖不足时继续拓展检索。
5. 使用 patent_idea_plan/register/evaluate/frontier 多代裂变；满足入库和反证记录后 promote。
6. 逐特征保存 countersearch_record、engineering_record；进行独立专业反证、理论/计算审核。
7. 在宿主 AI 内调用中文专利撰写 Skill，提供 draft JSON 给 patent_draft_save；机械附图 Skill 使用真实 STEP 文件并通过其独立测试和权限流程。
8. patent_quality_audit 返回真实缺口和待专业审核问题。**filing_authorized 永远是 false**；最终申请提交由获授权人员完成。

现有 CLI 保留：research、workspace、mcp-import、parse-pdf、citations、benchmark、validate。本 MCP 不向用户提供原始文件任意路径访问，不执行任意 Shell，不公开密钥或绕过许可下载。

### 结构化发明字段

candidate 必填：title、technical_problem、mechanism、enabling_details、distinguishing_features、assumptions、falsification_tests、expected_effect、technical_axis、inventive_method。可选 parent_id、evidence_ids。每一个来源编号必须实际存在于案卷 04_evidence.json，不能使用虚构公开号。

draft 包含 title、abstract、claims、description（technical_field/background/technical_problem/technical_solution/beneficial_effects/embodiments/drawings）、claim_support，支持段落必须真实存在于 description 中。格式检测只是基础校验，依然需要官方申请书式和专业人员全面复核。

## 安全、运行和可演进性

- 敏感检索词传出本机属于数据外发。需单独的保密审批和数据供应商合规使用授权。
- root、case_id 和 run_id 严格限制；禁止任意路径读取；不提供修改已批准证据的工具。
- 单机使用 SQLite + 文件锁，生产迁移到 PostgreSQL（RLS）、多租户对象存储、队列租约、Outbox、OIDC/AUD、限速、审计存证与备份。
- HTTP 使用受控上游网关；服务本身没有部署生产 OAuth2。需要在网关确保鉴权、用户与 case_id 的项目授权，随后建立后端逐请求的 ABAC 校验，才能在多租户远程环境使用。
- 单个检索 tool 当前是有界同步调用；生产超时任务应改为创建研究任务、返回 task_id、后台 worker 处理并支持结果轮询。
- 用官方 MCP SDK 的内存客户端测试 tools/list 和真实工具调用；CI 中安装 mcp 可选依赖执行协议测试。客户端可以使用 MCP Inspector 联机检查契约。
- 需要签订 SLA、源数据许可、地区合规和生产性能验收后，才可标为企业生产部署。

## 官方依据

- https://github.com/modelcontextprotocol/python-sdk
- https://py.sdk.modelcontextprotocol.io/
- https://modelcontextprotocol.io/specification/2026-07-28/basic/transports
