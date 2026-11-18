# 企业专利研发工作流操作手册（简体中文）

当前入口：ChatGPT / Codex 等 AI 客户端读取 AGENTS.md 与 skills/patent-autonomous/SKILL.md。程序不接入另一个 AI 模型，不需要 Ollama 或 LLM API Key。

## 运行准备

- Python 3.11 及以上、可写入的工作目录；
- 安装依赖：python -m pip install -e .；
- 自动化验证：python -m unittest discover -s tests -v；
- 企业内部使用前，先批准未公开发明、查询词、论文和专利资料的外发范围；
- 专利公开原文通过官方/授权数据渠道定位，论文元数据通过 OpenAlex/Crossref，HTML 正文由经许可的 Crawl4AI 获取；
- 用户未提供 EPO OPS 等数据源账号时，记录来源缺口，当前 AI 用其具备的网页检索/连接器补充，严禁假称全球已查全。

## 典型流程

1. AI 解析用户的技术要求，拟定工程目标、检索关键词、保密等级与案卷编号。
2. AI 或 CLI 创建案卷。默认保密级别为“秘密”，独立智能体的状态均为“待领取”。
3. 保密与权限智能体完成审批；若不允许外发，使用本地已获授权的文件，禁止将机密检索词发往外部。
4. 专利和论文智能体分别领取已解锁的任务，可同时工作；任务拥有租约和失败重试记录。每次真实查询保存公开号、DOI、网址和时间。
5. 文献进入索引，默认“待核验”；资料核对人联网查看真实公开文件，确认标题、正文、公开日、分类和关键权利要求后，逐条保存核验结果和理由。
6. 所有待核验文献处理完毕，双源覆盖符合任务要求，或存在明确的缺口例外及原因时，证据核验才能结束。
7. 技术方向评审智能体保存“继续 / 改换方向 / 终止”及真实证据依据。选改换方向时，开启新 revision，旧轮证据和任务留存。
8. 创新、反证、工程与专利撰写按任务依赖逐阶段开展。适当情况下不同候选可分派多个 AI 执行，再由独立质量角色核查来源和物理约束。
9. 执行静态 QA，保存质量记录与事件哈希，真实工程师和专利人员分别签核。未经真实审批不能标记可提交。

## CLI 命令

新建：

    python -m mechanical_patent workspace --db cases/index.sqlite3 create --case-id PM-001 --direction "机场消防车吸水系统创新"

状态：

    python -m mechanical_patent workspace --db cases/index.sqlite3 status --case-id PM-001

任务领取：

    python -m mechanical_patent workspace --db cases/index.sqlite3 claim --case-id PM-001 --role "保密与权限智能体" --actor "执行人001"

其中执行人是实际管理系统的记录字段。生产环境必须将该字段绑定企业认证用户，不能仅依靠 CLI 传入字符串。

将任务结果存为真实 JSON（保密审批的最小结构为：{"outbound_approved": false}），然后执行：

    python -m mechanical_patent workspace --db cases/index.sqlite3 finish --task-id 1 --actor "执行人001" --result-file privacy.json

例如核验一个公开文献：

    python -m mechanical_patent workspace --db cases/index.sqlite3 review --case-id PM-001 --doc-id EV-有效证据编号 --actor "资料核对人" --accept --rationale "已经核验公开全文、标题、日期及来源" --pdf-url "https://真实的原始专利PDF地址"

本地数据库检索：

    python -m mechanical_patent workspace --db cases/index.sqlite3 search --query "高海拔消防泵"

在线原始 PDF：

    python -m mechanical_patent workspace --db cases/index.sqlite3 source --case-id PM-001 --doc-id EV-有效证据编号

结果中的 public_pdf_url 是可以交给浏览器打开的公开文献地址；若为空，优先从 source_url 查找真实公开 PDF。绝不自行拼接未经验证的 PDF 地址。

合规可选下载：

    python -m mechanical_patent workspace --db cases/index.sqlite3 archive --case-id PM-001 --doc-id EV-有效证据编号 --pdf-dir patent_library --allow-domain 已经授权的PDF域名 --authorized

该命令只在下载许可和用户授权明确时运行。二进制下载验证 HTTPS、文件大小、PDF 文件头，阻断重定向并保留 SHA256。本地数据文件与 PDF 默认排除在 Git 提交范围之外。

已有研究案卷加入本地索引：

    python -m mechanical_patent workspace --db cases/index.sqlite3 import --case-dir cases/real-case

原有 research 命令生成双源检索结果时，会在案卷父目录自动创建 index.sqlite3，无需手动重复导入。

方向不成立时，经方向评审判定“改换方向”后运行：

    python -m mechanical_patent workspace --db cases/index.sqlite3 revise --case-id PM-001 --actor "技术负责人" --direction "新的结构控制方案" --rationale "前一轮证据表明技术问题定义不完整且当前手段不具差异"

该操作将 revision + 1，不清除历史文献、核验记录和旧任务。

## 状态与异常恢复

任务状态：待领取、运行中、已完成、失败、已阻断。每次租约有领取人及超时，超过允许重试次数后进入阻断。失败和超时需要由人工或受控调度器介入诊断。

缺少真实专利全文、论文原文、CAD、仿真数据、审批身份时，工作流允许保存不完整的研究结果和待补证据任务，但正式质量门禁不能以“通过”替代缺失事实。

## 生产级升级

SQLite 支持单机并发事务和离线索引，但没有真正的组织权限认证。正式生产平台需将工作流事件、证据和签核迁至 PostgreSQL，采用受控对象存储、RLS、角色授权、任务队列/Outbox、分布式重试和跟踪链路。专利与论文全文需按使用许可和保密要求保存；费用按数据访问、AI 客户端、存储、工程求解和专家审核分项核算。
