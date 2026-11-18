---
name: patent-project-storage
description: "每个机械专利研发项目独立 SQLite、独立案卷和最新专利索引，保留增量查询时间、源证据版本、失败状态及备份要求。"
user-invocable: true
---

# 专利项目隔离与索引时效技能

1. 读取 docs/PROJECT_SQLITE.md。新任务必须明确 project_id，每个 MCP 进程绑定一个 project_id。
2. 案卷数据和索引只保存至 private_patent_workspace/projects/<project_id>/patents.sqlite3。禁止跨项目共用一个 SQLite 文件。
3. 保密审批通过后，专利索引调用 patent_index_refresh 从真实授权供应商查询并写增量记录。自动生成检查时间、增量、错误和来源。
4. 使用 patent_index_search 读取离线数据时，必须同时显示检查时间、数据源与是否过期；使用 patent_index_history 查看变化和哈希。
5. 对新名称或未检索到的技术发起新一轮合法检索；EPO 数据延迟不可解释为全球不存在先前技术。
6. 旧 --db 模式仅保留历史兼容，所有新项目使用 --project-id、--storage-root 或项目范围内 MCP。
7. 实际生产需要加密备份、恢复测试、最小权限和强身份审计。

交付：每项目一 SQLite、可查的索引时间与文献历史、供应商故障记录和来源覆盖限制。
