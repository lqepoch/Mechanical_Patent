# 全球机械工程问题驱动的自主课题发现

更新：2026-11-19。状态：跨行业来源/课题目录、行业机理双轴、公开来源增量监测已实现；深度研究任务调度与独立工程认证仍在开发。

## 1. 目标与定位

以公开需求、真实工程失效与尚未解决的技术矛盾发现研究课题，再连接现有的专利、论文、TRIZ、想法裂变、独立反证和机械工程论证模块。面向全球所有机械工程应用，消防车仅为其中一个行业专题；范围覆盖机床、工程机械、航空航天、海工、机器人、能源、矿山、农业、轨道、医疗机械、精密机构以及未来新型机械装备。

不得自动声称某构思“全球尚未发明”，不得将未公开申请、失效专利、专利授权与实施自由混同。过期课题公告保留研究价值但不是当前申报机会。

## 2. 原始问题平台与更新边界

| 问题源 | 用途 | 注意 |
| --- | --- | --- |
| 国家消防救援局：2026年度科技计划指南（2026-02-24） | 高层供液、臂架抑振、高效泵炮、无氟泡沫比例供给等已确认需求 | 申报期限2026-03-15，已过期；原文 https://www.119.gov.cn/zfxxgk/fdzdgknr/tzgg/2026/53398.shtml |
| 国家消防救援局第三批“揭榜挂帅”2026-10 | 密集低层建筑消防车、无人机供水、超高层轻型供液、高海拔长隧道泡沫车、机器人通用平台 | 公告称第三批；流转附件标题可能标“第二批”，需以官方通知为准，2026-10-30截止已过 |
| FAA / EASA 公开技术报告 | 无氟泡沫计量、喷嘴、兼容性、使用替代液验证 | 保存报告、公告发布日期、测试边界与适用场景 |
| NFPA / 中国消防标准及修订信息 | 安全、操作、性能、认证与设计约束 | 核对标准版本和条款，非公开标准全文遵循许可 |
| 采购/招标/验收公告、公开事故分析、维保及故障记录 | 实际客户任务约束、使用痛点、失效频次和维修成本 | 谨防竞标文件中的单一厂家参数、保密信息、失效归因未经复核 |
| HeroX / MIT Solve 等开放创新挑战 | 跨行业问题发现、迁移机理及需求访谈 | 平台题目不自动证明消防行业存在同等商业需求 |

## 3. 最低可用问题记录

字段：`problem_id`、`title`、`domain`、`scenario`、`observed_failure`、`failure_physics`、`source_url`、`publisher`、`published_at`、`captured_at`、`deadline_at`、`source_hash`、`licence`、`confidentiality`、`metrics`、`boundary_conditions`、`known_methods`、`open_gaps`、`cross_domain_analogues`、`evidence_ids`、`status`、`reviewer`。

每个问题输出：
1. 大白话描述的“谁在什么工况遇到什么故障、造成什么损失”；
2. 对应机械/流体/控制机理与最小系统边界；
3. 可测验的性能指标和失败反证试验；
4. 候选结构的零件组成及连接机理；
5. 国内外检索的技术特征对照与未覆盖范围；
6. 成本、制造、仿真、台架、标准、知识产权与商业价值评估；
7. 课题卡、证据文件、每份原始专利/论文的 Markdown 记忆文件及项目独立 SQLite 记录。

## 4. 课题发现规则

A. 以真实失效、复现条件、客户需求和强制标准变更驱动。单一论文“未来趋势”只能形成探索性候选。
B. 基于功能分类、IPC/CPC、同族引用、核心结构拓扑、FMEA、TRIZ、SCAMPER 和跨行业迁移提出不同物理机理的候选；通过已有 idea-fission 保留多样性与反证链。
C. 先进行独立新颖性对照与机械理论检验（载荷、流量、压力、温度、材料和疲劳），再按工程可验证程度分级；缺少全文保留覆盖缺口。
D. 以安全/任务价值、故障频率、技术效果、试验可行性、车型平台复用、制造成本、专利冲突风险分别给出0–5分证据化评审；这些分数仅用于研发排期。
E. 交付候选阶段只输出白话课题、原理结构、草图计划、关键公式与实验方案。专利申请格式由发明人明确选择后启动。
F. 不得将企业内部故障、CAD 或未申请发明上传公开平台；保密审批先于任何外部检索。网页采集遵守网站条款、robots 与授权，API token 按服务方合规管理。

## 5. 依托已有工程设施

- 复用 `skills/patent-landscape`、`patent-industry-sources`、`patent-ideation`、`patent-idea-fission`、`patent-countersearch`、`patent-engineering-review`；禁止重复造出另一套互斥研发工作流。
- 当前已有 OpenAlex、Crossref、可授权 EPO OPS、专利原文与 DOI 证据协议。评估 PQAI 作为语义相似检索参考，谨防误将匹配分数当作法律意见。
- 研究案卷以每项目独立 SQLite、可校验哈希与 Markdown 文献记忆为准；若尚未实现某项持久化写入，必须报告开发缺口而不能伪称可用。
- 企业扩展计划：分源适配器、发布与变更时间索引、来源信誉、重复题目聚类、定期增量发现、失败自动重试、仪表板与 MCP `discover_problems` / `rank_topics` 接口、人工审核审计，保持 AWS Lambda 与阿里云 FC 共用云中立业务入口。
- OpenAlex 免费额度/Key 条款会变动，运行时须核实当日官方政策；开源代码许可不代表全文和题库数据可商业使用。

## 6. 可考核验收

真实问题源收录与更新是否有来源链；已过期通知被正确识别；每个候选拥有至少一个可测失效假设；同一问题跨站点去重；主题检索返回可追溯来源；任何证据缺口明显可见；人工作业可复现；重启后从 SQLite/Markdown 恢复研究；绝不以搜索空结果自动出具“全世界没有该专利”的结论。


## 7. 可运行的公共来源目录与增量闭环（2026-11-19）

### 当前实现

- 37个可复用问题来源平台种子：src/mechanical_patent/data/problem_sources.json。包含国家消防救援局、中国消防标准/采购、FAA、EASA、NFPA、NASA、HeroX、MIT Solve、OpenAlex、Crossref、EPO、USPTO、WIPO等；默认网页需人工/合法网页采集工具核查。已预配两条 NASA 官方技术/航空 RSS。
- 40个跨行业机械课题假说种子：src/mechanical_patent/data/fire_apparatus_topics.json。全部标记 hypothesis_only、novelty_checked=false。研究候选与经检索认证的发明分别看待。
- 公共目录独立 SQLite：工作区 public_source_catalog/sources.sqlite3，不存储私有技术、CAD、BOM或项目标识；每个专利项目仍使用 projects/<project-id>/patents.sqlite3。
- 新平台通过 propose 自动登记为 pending，等待管理员核实站点身份、采集条款与许可后通过 CLI approve。MCP 特意没有 approve 工具，AI 无权批准新来源。
- RSS 巡检：批准来源限定同源 HTTPS、DNS 非私网校验、禁止重定向、限制1MB与请求超时；SQLite 存储 ETag、Last-Modified、下次扫描时间、租约、指数退避、变化版本和审计哈希。跨域链接只提候选且不访问，未经审核不得扩张抓取范围。
- AI 可执行：MCP patent_source_catalog → patent_topic_catalog → patent_discovery_inbox → patent_public_observe → patent_topic_derive → patent_topic_plan → 现有专利论文检索与 TRIZ / 想法裂变 → patent_public_research_note。公开笔记仍是 unverified_ai_assessment；用户决定采用的课题通过 patent_topic_adopt 转入绑定的项目案卷，继续原有保密/专利申请审批。
- 周期循环可以由 cron/systemd/K8s CronJob 定时调用，也可用 Compose 的 discovery profile 运行受控 source_catalog_worker 周期巡检。后台只访问已批准公共 RSS，不运行 LLM 推理、不接触专利项目私有数据；CI 不保存实际企业公共库。

### 使用命令

    mechanical-patent source-catalog sources --status approved
    mechanical-patent source-catalog topics
    mechanical-patent source-catalog inbox
    mechanical-patent source-catalog cycle
    mechanical-patent source-catalog cycle --allow-public-network --max-sources 5
    mechanical-patent source-catalog audit

新增平台候选及管理员批准：

    mechanical-patent source-catalog propose --name "新问题平台" \
      --url "https://example.org/challenges" \
      --reason "稳定公开机械技术挑战，需核实开放使用许可"
    mechanical-patent source-catalog sources --status pending
    mechanical-patent source-catalog approve --source-id DISC-实际返回ID \
      --reviewer "企业知识管理员" --rights-reviewed

根据已核验网页元数据手工入库，并让 AI 发散研究：

    mechanical-patent source-catalog observe --source-id US-FAA-ARFF \
      --url "https://www.faa.gov/airports/airport_safety/aircraft_rescue_fire_fighting" \
      --title "公开机场消防技术问题" --summary "相关工程问题待核验"
    mechanical-patent source-catalog derive --observation-id OBS-实际返回ID \
      --problem "描述已有问题与可复现工况" \
      --hypothesis "具体机构与物理作用过程" \
      --falsification "对照试验及否定条件"

每一轮的输入先读取旧平台、旧课题、旧证据、旧失败记录，避免重复研究。原始内容和发布时点都要可追溯；检索到的来源不是其专利权利范围认证。已过申报时间的政府课题只能作历史需求证据。

### 开源工具的增量接入边界

- changedetection.io（Apache-2.0）：HTTPS 网站及 PDF 变更检测、REST API、MCP；适合补强 manual 页面监测，尚未集成：https://github.com/dgtlmoon/changedetection.io
- Huginn（MIT）：RSS、网站事件及 Webhook 持续代理；适合跨渠道事件输入，尚未集成：https://github.com/huginn/huginn
- RSSHub（AGPL-3.0）：拓展可采集 RSS 站点，版权与网络使用条款需独立审查，尚未集成：https://github.com/DIYgod/RSSHub

### 安全和企业生产验收的后续工作

1. 管理员审批需要可信 OIDC 身份与组织内部分权；当前 CLI reviewer 字符串只供本地审计，不具备真实身份认证能力。
2. 出站代理与防 DNS rebinding、DNS Pinning、robots/ToS 审查、RSS 链路级商业许可判断、漏洞和成本观测需要生产部署强化。
3. 提取真实工程失效、跨源问题合并、质量多样性评分、相似权利要求逐项反证及模型评测仍需要继续接现有 research tools。
4. 外部不可变存储和带密钥签名的审计、备份恢复、限流熔断、轮询误报回滚尚待实现；SQLite 哈希链不能防范有数据库写权限的管理员改写整条记录。
5. 真实仿真、样机、实验数据与工程师署名后才允许标记 engineering_verified；自动生成的评分、论文摘要与法律意见均不代替这一验收。


## 8. 全机械工程范围：应用行业 × 共性物理机理

2026-11-19 更新。原有20个消防相关来源平台和20个消防机械课题完整保留，新增17个跨行业公开来源和20个跨行业机械假说。当前总计37个平台来源、40个候选课题。这些是公开入口和待检验课题，不代表全部已执行逐条原文核验、专利查新或工程实验。

行业标签（18项初始）：消防与应急、工程机械、工业制造、机器人、航空航天、船舶海工、轨道交通、汽车/特种车辆、能源、矿山、农机、医疗康复、建筑基础设施、精密仪器、环保水务、材料成型、通用所有领域和未分类。

物理机理（19项初始）：流体与汽蚀、液压、热力学、振动动力学、疲劳断裂、摩擦磨损、密封腐蚀、动力传动、机构运动、致动、制造工艺、材料连接、结构控制协同、可靠性、检测测量、机器人交互、能量转换、多物理场耦合、通用机理。

公开来源和研发课题分别保存 industry_tags_json 与 mechanism_tags_json。现有 SQLite 自动执行向后兼容的 ADD COLUMN 迁移，保留旧研究问题、人工审批状态、失效来源记录、审计哈希、阅读批注与历史版本。数据源标为 all 时对所有特定行业检索可见；任何新型未列行业可以使用 unclassified，并在后续人工审核中增加新分类；以上标签并非行业白名单。

### 新增重点源头（核对过的官网入口）

| 场景 | 来源链接 | 用途 |
| --- | --- | --- |
| 中国机械与工艺 | https://service.most.gov.cn/kjjh_tztg/ | 国家重点研发计划；2026-11-14 关键基础件及制造工艺公开专项方向 |
| 中国科研基础 | https://www.nsfc.gov.cn/p1/4201/sqzz.html | NSFC 基金指南、学科前沿与技术目标 |
| 美国机械与制造 | https://www.nsf.gov/eng/programs | NSF 工程/CMMI；制造、机械、动力学、材料 |
| 美国能源技术 | https://arpa-e.energy.gov/programs-and-initiatives/view-all-programs | ARPA-E 能源、储能、热、流体、装备技术 |
| 美国制造标准 | https://www.nist.gov/smart-manufacturing | NIST 智能制造、机器人测量、性能试验 |
| 美国前沿工程 | https://www.darpa.mil/work-with-us/opportunities | DARPA 研发机会与技术挑战 |
| 美国公开挑战 | https://www.usa.gov/find-active-challenge | 美国政府当前挑战入口；Challenge.gov 2026-03-30 已关停 |
| 欧洲研究成果 | https://cordis.europa.eu/projects | EU CORDIS 项目报告、成果和开放数据入口 |
| 欧洲新兴技术 | https://eic.ec.europa.eu/eic-funding-opportunities_en | EIC 深科技及工程挑战 |
| 英国跨学科工程 | https://www.ukri.org/councils/epsrc/ | EPSRC 机械、先进材料和制造 |
| 英国产业问题 | https://apply-for-innovation-funding.service.gov.uk/competition/search | Innovate UK 产业竞赛与研发需求 |
| 机械设计竞赛 | https://www.asme.org/conferences-events/competitions | ASME 设计、CAD、增材、机器人赛事 |

大多数平台是 mode=manual 的来源目录，需要在版权/网站条款及访问权限审批后由可选网页/PDF/API适配器监控；目前可自动轮询的仅为单独已配置的 RSS。历史挑战平台和过期征集必须标注停用/失效日期，不将其当成当前申请机会。

### CLI

    mechanical-patent source-catalog taxonomy
    mechanical-patent source-catalog sources --industry industrial_manufacturing
    mechanical-patent source-catalog sources --industry robotics
    mechanical-patent source-catalog topics --mechanism fatigue
    mechanical-patent source-catalog analogies --industry fire_rescue --mechanism fluid
    mechanical-patent source-catalog analogies --industry robotics --mechanism kinematics

新增源可以使用 source-catalog propose 的 --industry-tag 和 --mechanism-tag 参数登记分类，仍须独立来源审批。基于公开观察派生新课题也能指定这些标签。MCP 增加 patent_mechanical_taxonomy、patent_mechanical_analogies，现有 source_catalog/topic_catalog 接口增加可选的行业与机理检索参数。

### 研究边界

AI 可以自动把同一机理跨行业对照，但必须重新证明工况可迁移、结构连接可实施、技术效果可测，并逐个候选完成原始专利权利要求的反证检索。来源平台上的“研究方向”仅代表公开提出过问题，不能直接当成未解决或尚未申请专利的证明。任何独立工程实验、法律结论仍需要对应证据与人类专业签核。
