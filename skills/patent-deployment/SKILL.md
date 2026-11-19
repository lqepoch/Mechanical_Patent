---
name: patent-deployment
description: "在 Ubuntu 26.04 上部署、升级或备份 Mechanical_Patent 的 Docker/GHCR MCP 服务，保证磁盘持久化、回环监听、安全发布与可恢复运行。"
user-invocable: true
---

# 专利研发 Docker 与 GHCR 部署技能

## 何时使用

当用户提出 Docker、Ubuntu 26.04、GHCR、数据磁盘、容器升级、备份恢复、服务部署、公开镜像要求时，先阅读本技能与 docs/DEPLOYMENT_UBUNTU26.md。先审查现有 MCP 入口、主机与数据权限、安全网络约束，禁止将公开容器镜像等同于公开专利数据或企业级认证完成。

## 固定技术边界

- GHCR 镜像：ghcr.io/lqepoch/mechanical_patent，main 与 v* 标签在 CI 验证通过后发布。
- 宿主机：Ubuntu 26.04 LTS；Docker Compose host network；MCP 始终监听 127.0.0.1:8765。
- 容器：UID/GID 10001，只读根文件系统，/tmp 临时存储，/data bind mount。所有私有案卷数据不进入镜像。
- 数据：PATENT_DATA_DIR 必须是指向明确挂载磁盘的绝对路径，容器内部 /data。保留 projects/<project-id>/patents.sqlite3、projects/<project-id>/cases、各案卷 JSON/PDF 与事件审计信息。默认拒绝挂载到系统盘。
- 当前已采用每项目独立 SQLite，路径为 /data/projects/<project-id>/patents.sqlite3；仍未完成真实身份、OIDC 与跨项目 ABAC 权限校验。组织级共享需在业务层实施 OIDC 和项目 ABAC。

## 发布和操作流程

1. 检查 GitHub 仓库现状、基础镜像、官方 Docker/Ubuntu/GHCR 文档和敏感数据排除清单。
2. 运行 scripts/deploy_ubuntu26.sh init 验证真实磁盘已挂载、UID 10001、0700 目录权限，失败则终止操作。
3. 升级前记录旧镜像 digest，使用 scripts/backup_ubuntu26.sh 在单独磁盘生成停服一致性备份与 SHA256。
4. 在 PR 中执行 Python 测试、Docker 镜像构建、MCP 运行与容器删除后恢复持久化核查。main/版本标签发布使用最小授权 GITHUB_TOKEN。
5. 拉取指定版本镜像，执行 up 和 status，检查健康状态与 SDK 初始化，再由真实 MCP Host 接入。首次发布后核实 GHCR Package 已设为 Public，匿名拉取有效。
6. 每次升级保存可回滚的镜像版本与数据库备份。定期演练恢复和异地备份；任何数据库格式迁移单独审查。

## 禁止操作和失败恢复

- 未部署 TLS + OAuth2/OIDC + 逐项目访问控制时，禁止对公网开放 MCP API。
- 数据盘未挂载、权限不符或检出 .env/私有资料进入镜像时立即停止发布。
- 确认镜像问题后回退到已验证 digest；若存在不可逆数据迁移，停服恢复完整案卷快照并复核事件链。
- 不要在容器或 CI 中执行未授权专利检索、上传内部图纸、公开企业秘密或伪造研究结果。

## 论文全文安全处理与 GHCR 生产分工（2026-11-19）

原有镜像仍保持轻量 MCP 服务，项目卷新增 `knowledge/fulltext`，随 patents.sqlite3、literature.sqlite3、Markdown 一并备份/恢复。下载和 Docling 解析采用有身份审批的受控本机 CLI 或后续隔离 Worker，模型权重必须在离线目录准备，禁止由公网 MCP 请求触发未知来源 PDF 下载。主容器通过只读 MCP 提供任务状态和页码检索；权限、出站防火墙、日志与许可证审计以及 PDF 防毒沙箱在正式生产前验收。具体见 docs/FULLTEXT_PIPELINE.md。
