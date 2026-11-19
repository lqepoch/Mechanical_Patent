# Ubuntu 26.04 LTS：Docker + GHCR + 磁盘持久化部署

> 适用范围：受控单机运行 Mechanical_Patent MCP；镜像可公开，专利案卷和接口须保持私有。文档日期 2026-11-18。

## 架构

~~~text
GitHub main / v* --CI测试--> GHCR: ghcr.io/lqepoch/mechanical_patent:main
                                     |
Ubuntu 26.04 LTS + Docker Engine + Compose
    | Linux host network; 只监听 127.0.0.1:8765/mcp
    | MCP SDK v2 服务; UID/GID=10001; 根文件系统只读
    + bind mount: /srv/mechanical-patent/data -> /data
          /data/projects/PM80/patents.sqlite3
          /data/projects/PM80/cases/<case-id>/runs/<run-id>/
          案卷证据、索引及审计事件
~~~

容器网络采用 Linux host network，保留现有 MCP 服务仅绑定回环地址的安全检查。未接入 OAuth2/OIDC + 逐项目访问控制前，该接口只能由同一主机上的可信进程访问，不能直接映射公网或接入开放代理。host network 同时意味着容器共享宿主机网络命名空间，应运行在专用受控宿主机上。

## Ubuntu 26.04 安装 Docker Engine

参考官方安装说明 https://docs.docker.com/engine/install/ubuntu/ 。新主机示例：

~~~bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<'EOF'
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: resolute
Components: stable
Architectures: amd64 arm64
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker compose version
~~~

按服务器真实架构只保留对应 Architectures 值。若主机已安装 docker.io、非官方 containerd 或已经运行其他容器服务，应先安排兼容性评估，避免在生产主机直接替换容器运行时。使用 Docker 组与访问 Docker daemon 均属于高权限操作。

## 磁盘和环境准备

用 lsblk -f 查询专用磁盘实际设备、文件系统和 UUID；操作前确认设备上没有需要保留的数据。在 /etc/fstab 中使用真实 UUID 配置开机挂载（由管理员审核），挂载至 /srv/mechanical-patent，再核对：

~~~bash
sudo mkdir -p /srv/mechanical-patent
# 已正确配置 fstab 并已核实设备后：
sudo mount /srv/mechanical-patent
findmnt -T /srv/mechanical-patent
df -h /srv/mechanical-patent
~~~

无需对已有数据磁盘进行格式化。为了阻断数据盘未挂载导致写入 Ubuntu 系统盘，部署脚本默认拒绝位于根分区的路径。只有明确接受单盘风险的测试主机才允许在执行命令时设置 PATENT_REQUIRE_SEPARATE_DISK=false。

~~~bash
git clone https://github.com/lqepoch/Mechanical_Patent.git
cd Mechanical_Patent
cp .env.example .env
chmod 600 .env
# 编辑 .env：
# PATENT_DATA_DIR=/srv/mechanical-patent/data
# PATENT_IMAGE=ghcr.io/lqepoch/mechanical_patent:main
bash scripts/deploy_ubuntu26.sh init
bash scripts/deploy_ubuntu26.sh up
bash scripts/deploy_ubuntu26.sh status
~~~

init 会把数据目录权限设为 0700，UID/GID 10001。容器启动时仅把该目录挂载到 /data，且 bind.create_host_path=false，避免输入错误路径时自动创建目录。/data 的 SQLite 索引、案件目录和事件记录在容器被删除或镜像升级后仍然保留。

初次使用需要在真实 GHCR 镜像成功发布后，进入仓库 Packages 中查看容器 Package Settings，将权限调整为 Public；公开源仓库不代表首次发布的镜像包已公开。此项配置通常需要拥有者在 GitHub 网页完成。公开包可以匿名 docker pull，私有包需要授权。参考 https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry 。

## 状态、协议与本机客户端

~~~bash
bash scripts/deploy_ubuntu26.sh status
bash scripts/deploy_ubuntu26.sh logs
curl -i --max-time 5 -H 'Accept: application/json, text/event-stream' http://127.0.0.1:8765/mcp
~~~

纯 HTTP GET 并非完整 MCP 初始化请求，因此响应码不一定为 200。容器 HEALTHCHECK 仅检查 TCP 监听；完整协议在 CI 使用官方 MCP SDK 的测试用例校验，实际客户端接入时需执行 MCP 初始化。

容器内执行工作流 CLI：

~~~bash
docker compose run --rm --entrypoint mechanical-patent patent-mcp workspace --db /data/projects/PM80/patents.sqlite3 status --case-id PUMP-001
~~~

该查询要求案卷已经创建。现有代码已经提供每项目独立 SQLite（由 PATENT_MCP_PROJECT_ID 指定），但仍缺少真实的身份化项目 ACL/OIDC；可信单用户/单组织本机部署适用，跨组织 SaaS 仍需独立的授权数据存储与实际鉴权。

## 备份、恢复、升级、回滚

备份需将数据库和研究文档同时冻结。当前使用停服一致性备份，将完整 /data 目录归档到不同挂载磁盘，生成 SHA256：

~~~bash
sudo mkdir -p /mnt/patent-backups
# 先把单独备份磁盘挂载到 /mnt/patent-backups，并确认 findmnt 结果
findmnt -T /mnt/patent-backups
sudo PATENT_BACKUP_DIR=/mnt/patent-backups bash scripts/backup_ubuntu26.sh
~~~

备份脚本在服务运行时短暂停机，备份结束或失败会尝试恢复服务；如果本来没有运行则维持停止状态。生成的 tar.gz 并未自动加密，必须实施专用访问控制、异地副本、定期恢复演练、明确的保留策略及灾备 RPO/RTO。

恢复前先停服并核对 SHA256、归档清单、真实挂载盘，审计归档内容不存在路径穿越或符号链接后再执行：

~~~bash
bash scripts/deploy_ubuntu26.sh down
cd /mnt/patent-backups
sha256sum -c mechanical-patent-YYYYMMDDTHHMMSSZ.tar.gz.sha256
tar -tzf mechanical-patent-YYYYMMDDTHHMMSSZ.tar.gz | head
# 在全新、已隔离、空的数据目录内由管理员确认恢复：
sudo tar --numeric-owner -xzf mechanical-patent-YYYYMMDDTHHMMSSZ.tar.gz -C /srv/mechanical-patent/data
sudo chown -R 10001:10001 /srv/mechanical-patent/data
cd /path/to/Mechanical_Patent
bash scripts/deploy_ubuntu26.sh up
~~~

真实路径与归档文件名均需按环境替换。升级使用 bash scripts/deploy_ubuntu26.sh up；该命令会先 pull、再按当前镜像配置 up。稳定环境应将 .env 中 PATENT_IMAGE 固定为验证过的 sha 标签或完整 sha256 digest，记录前一镜像摘要；需要回滚时将镜像引用改回该版本、运行 up。回退镜像只恢复代码：若数据库有不可逆迁移，需要配套还原升级前完整案卷备份。

## 安全与交付分界

- PR 阶段：Python 测试、Docker 构建、SQLite quick_check、容器销毁与重启后的文件持久性检查；PR 不向 GHCR 推送。
- main 或 v* 标签：验证通过后使用 scoped GITHUB_TOKEN 自动发布 linux/amd64、linux/arm64，同时产出 SBOM 和构建 provenance；GITHUB_TOKEN 不需要额外存入长期 PAT。
- 镜像构建上下文排除 .env、真实案例、原始 PDF、SQLite、外部 Git submodules 等私有内容；宿主 .env 文件权限为 0600，权限管理员自行负责。
- 需要新增依赖锁、定期 CVE 扫描、供应链签名、镜像签名验证与自动安全升级。现有 Python 依赖未完全锁定，不具备严格可复现供应链认证。
- 对外 MCP 接口需要 TLS/OIDC、真实用户与项目 ABAC、速率限制和日志权限；Docker 镜像发布本身不解决这些问题。

相关原始资料：https://docs.docker.com/engine/install/ubuntu/ 、https://docs.docker.com/build/ci/github-actions/ 、https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry 。


## 当前项目独立数据库约定

`.env` 必须配置 `PATENT_MCP_PROJECT_ID=PM80`（仅作示例，可选当前项目合法 ID）。服务一个实例绑定一个项目，将案卷和研究数据库持久化至 `/data/projects/PM80/patents.sqlite3`。切换项目 ID 会创建新的独立目录，不会自动读取旧项目数据。多个项目需要独立 MCP 进程和端口，当前 Compose 模板仅支持一个项目实例；跨项目访问控制仍须经真实身份网关与业务 ABAC 评估。


## LaTeX 文件导出能力

运行镜像包含 Pandoc，支持当前项目的 LaTeX 源稿导出 DOCX、HTML、Markdown；MCP 接口由当前调用端 AI 负责推理和修改。在线 MCP 容器故意不安装 TeX/PDF 编译器，不具备不可信 TeX 安全隔离；PDF 编译须按 docs/LATEX_WORKFLOW.md 部署独立离线受控构建服务。

## 离线论文全文任务与资源边界（2026-11-19）

论文 PDF 与机器解析数据应写入现有数据盘 /data/projects/项目ID/cases/案卷ID/knowledge/fulltext/。默认 GHCR MCP 镜像只安装轻量业务依赖，不自动包含 Docling 模型权重，也不允许模型运行时隐式联网获取权重。通过宿主受控 CLI 或独立审批的解析 Worker 在持久卷上执行时需设置受控离线模型目录、来源域名白名单、外网防火墙、最大文件/页数、资源上限和内容扫描。容器主进程通过只读 MCP 查询已经形成的页码索引与进度。升级前按照原有 SQLite WAL 与 PDF 目录一同做停服一致性备份和恢复演练。详见 [FULLTEXT_PIPELINE.md](FULLTEXT_PIPELINE.md)。


## 公开科研问题自动巡检服务（2026-11-19）

已增加 Compose 可选 profile discovery。启用后，独立 source-radar 容器使用同一 GHCR 镜像和持久化磁盘 /data，按3小时周期检索**已经批准的公共 RSS**。不提供公网入口，不向第三方传输内部项目内容。其公共数据库位于 /data/public_source_catalog/sources.sqlite3；每个项目仍有各自独立 /data/projects/.../patents.sqlite3。

    # 启动之前先审查已批准平台和具体 feed_url、出口防火墙与收集许可
    docker compose run --rm --entrypoint mechanical-patent patent-mcp \
      source-catalog sources --storage-root /data
    # 显式启用巡检容器，并保持 MCP 主服务继续运行
    COMPOSE_PROFILES=discovery docker compose up -d
    COMPOSE_PROFILES=discovery docker compose logs --tail=100 source-radar
    # 可只停止此公开巡检 worker，保留 MCP 主服务
    COMPOSE_PROFILES=discovery docker compose stop source-radar

默认未设置 COMPOSE_PROFILES=discovery 时，该 worker 完全不启动。不得通过编辑 compose 把外部 API 密钥或未公开专利内容注入巡检任务。该服务只负责来源监测和新问题入库；全自动 AI 深度研究还需接入有审批、预算、可恢复队列和独立核验机制的 Agent 调度服务。Dockerfile 原始 TCP HEALTHCHECK 专用于 MCP，worker 禁用该检查，由容器 restart 策略和日志进行初级监控；正式环境应接入真实探针及统一告警。

备份时连同 /data/public_source_catalog/ 一并执行停服一致性备份。灾备恢复应核验审计哈希链并进行故障重试检查，进阶环境另行设计外部签名/只追加事件仓库。
