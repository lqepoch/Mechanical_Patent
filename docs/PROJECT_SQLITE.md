# 每个研发项目独立 SQLite 的实施规范

2026-11-18。项目存储示意：

    private_patent_workspace/
      projects/PM80/patents.sqlite3
      projects/PM80/cases/CASE-A/runs/RUN-.../...
      projects/PM80/cases/CASE-A/manuscripts/PAPER-.../...
      projects/PM120/patents.sqlite3

一个项目一份 SQLite（WAL）、项目内支持多个案卷与研究轮次。MCP 启动必须使用 --project-id，进程绑定唯一 project_id；数据库 project_identity 固定身份；同名 case_id 仅在项目内唯一。目录及 SQLite 文件检查符号链接；其他项目无法通过该进程访问。

MCP 启动：

    python -m mechanical_patent.mcp_server --workspace ./private_patent_workspace --project-id PM80 --transport stdio

CLI 新建案卷：

    python -m mechanical_patent workspace --project-id PM80 --storage-root ./private_patent_workspace create --case-id CASE-A --direction "消防泵吸水"
    python -m mechanical_patent research --project-id PM80 --storage-root ./private_patent_workspace --workflow-case-id CASE-A --direction "消防泵吸水" --patent-provider none --paper-provider none

旧版 --db 或没有 --project-id 的 research CLI 仅保留兼容。生产级新增项目全部使用项目模式；集中式历史库应由管理员完成数据归属审批、备份、逐案拆分与恢复验证，绝不在后台静默跨项目迁移。

专利索引：
- patent_index_checks：每次授权供应商请求的执行时间、检索词、错误、新增与变更数量。
- patent_index_current：每项目每案卷的文献内容、首次发现时间、最后检查时间。
- patent_index_versions：每次真实内容变化的历史记录与 SHA-256。
- patent_index_refresh 每次执行真实 EPO OPS 请求；没有案卷外发审批或数据凭证则拒绝。
- patent_index_search 只读取本项目数据库；展示最新一次检查时间与是否过期。
- patent_index_history 用于追溯同一公开号发生了什么变化。
- 第三方授权专利 MCP 可通过 patent_source_import 导入，结果强制标注未核验，原始公布文献核对后再使用。

“实时”是系统在需要时实际连接上游检查的时间；EPO 覆盖统计每周更新，文献公开日期与供应商入库时间存在时差。不存在能够取得尚未公开发明申请的全球实时数据库，检索未命中不能宣称不存在在先技术。

权限、安全及恢复：SQLite 的 WAL 文件和备份同属项目私有资产；使用 SQLite backup API、一致快照、密钥与受控文件权限、备份恢复演练、审计哈希链。多用户公网生产部署仍需独立 OAuth2/OIDC、组织/项目鉴权、网关和远程隔离。

官方参考：
https://www.epo.org/en/service-support/faq/searching-patents/open-patent-services/coverage/where-can-i-see-latest-coverage
https://www.epo.org/en/searching-for-patents/data/web-services/ops
