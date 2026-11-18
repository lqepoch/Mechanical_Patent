# 工程白话技术方案规范 / Engineering Brief v1.0

更新时间：2026-11-18。关联 Issue #27、#2、#8、#25。本文件规范技术方案形成、绘图选择、排版和申请转换门禁。默认目标读者为机械设计、控制设计、工程主管及专利代理对接人员。

## 1. 两阶段审批与文档责任

- **阶段 A——研发技术方案（默认）**：研究问题 → 全球已获授权的数据源检索及覆盖缺口 → 创意裂变 → 逐特征反证 → 工程论证 → **单一候选方案** → 白话技术说明 → 工程负责人内部评审 → 归档/迭代/准备申请决策。通过技术评审即可结束本轮任务，完整保留证据、假设和未验证事项。
- **阶段 B——申请材料（仅明确申请决定后）**：用户明确同意 + 企业可信审批系统对已锁定的技术方案哈希签名 → 代理交底包 → 权利要求、说明书、摘要、附图和支持关系 → 法务/代理机构审阅 → 由授权人员履行申报。系统从不将“批准转换底稿”视为“批准向专利局递交”。
- **法律与工程判断各自独立**：公开检索无法保证全球查全；内部“创新初筛通过”不等于法定新颖性/创造性确定成立，也不等于 FTO 或商业成功。2026-01-01 起适用第84号令对审查指南的修改。审查结论须标记证据覆盖及待核验范围。

## 2. 数据事实源与成品

每一专利研究运行在私有案卷中以 \`08a_technical_brief.json\` 储存结构化技术事实，\`08a_technical_brief.tex\` 是无损/可审阅的排版视图，附属原始 \`.drawio/.mmd/.SLDPRT/.STEP\` 与导出 PDF/SVG/PNG 独立保留；\`08_application.json\` 只用于已获转换审批的阶段 B。现有案卷检索/创新/质量资料不被覆盖。

技术方案 JSON 最小字段：
- \`candidate_id\`：关联已选定的一个候选。一个独立创新方案一个案卷技术说明；候选裂变池可以同时存很多方向，最终主文档只锁定一个。
- \`title\`, \`technical_problem\`, \`solution\`, \`mechanism\`：自然语言说明工程动机、完整技术手段和实现原理。避免专利式长句。
- \`components\` 可选：\`number/name/role\`，明确连接/相对位置时在 role 文字写清，结构复杂时增加机械视图。
- \`process_steps\` 可选：\`trigger/action/result\`。结构与步骤至少一种有内容。
- \`innovation_points\`：每项 \`feature/prior_difference/technical_effect/evidence_ids\`，把区别结构、为何有效和相关公开专利来源对应起来。没有核验证据只能写“待验证”，不能给“绝对新颖”判定。
- \`expected_effect\`：定性或带假设的预期效果；量化结果必须给出工况、测量或计算证据。
- \`verification_plan\`：可证伪条件、测试设备、对照基线和通过阈值（若未定须标注待定）。
- \`prior_art\` 可选：\`evidence_id/known_solution/difference\`，无来源不能添加编造的对比结论。
- \`risks\` 可选：\`failure/mitigation\`，覆盖极端工况、失效安全与制造检验。
- \`figures\` 可选：\`kind/caption/asset\`，asset 只引用 \`figures/\` 中本地 PDF/PNG/JPG；原始可编辑文件另存。
- \`profile\`：\`auto|mechanical|control|hybrid|concise\`，auto 由结构与动作内容决定。
- 文档和状态须绑定项目/运行/版本/操作者/文件 SHA256，内部审批记录不得由 AI 自我签字。

已落地 JSON 合同与 renderer 为 \`src/mechanical_patent/technical_brief.py\`；无模型生成器和外部 Shell 执行。实际正文内容由当前 ChatGPT/Codex 等调用方填写。

## 3. 文档版式

默认 A4、23mm 页边距、CTeX 11pt、编号章节、简明封面、自动目录、页眉版本、居中页码。首章“一页理解方案”高度概括问题、解决手段、预期效果，随后按需编排机理、结构/接口、触发-动作-结果、区别技术特征、公开技术差异、工程风险、测试计划、配图与待办。

技术文件采用**一个关键问题一段话、一个运动链一张结构图、一个交互机制一张时序图、一个可量化差异一张表**的原则。没有相关内容时自动省略相应章节；不得机械堆砌图、装饰性图片或空白图框。图表紧邻首次解释该技术机理的位置，图序连续；引用统一使用“图1、图2”/“表1、表2”及 101、102、103 部件标记。需要申请时由专业附图转换器再执行专利制图规范审核。

## 4. 按需图表决策表

| 工程信息 | 推荐可编辑源 | 放入方案时机 | 避免的误用 |
| --- | --- | --- | --- |
| 零件相对位置、运动和连接关系 | CAD/STEP → 线稿 SVG/PDF，简图可 draw.io | 仅文字不能解释装配关系时 | 不用随意示意图冒充尺寸准确工程图 |
| 内部流路、电路/控制数据通道 | draw.io \`.drawio\` 或 TikZ | 需要说明介质/信号流向时 | 不混淆流体、机械和电气回路 |
| 若干步骤和判断条件 | Mermaid \`.mmd\` flowchart | 有明确分支、循环、异常路径时 | 简单两步文字足够就省略 |
| PLC/传感器/泵/阀跨组件顺序 | Mermaid sequenceDiagram | 时间顺序影响工作原理时 | 不把机械结构图当控制时序 |
| 状态互锁、故障恢复 | Mermaid stateDiagram | 模式切换及安全联锁复杂时 | 不虚构未实现状态 |
| 试验指标、流量、压力曲线 | 受控数据 → matplotlib/PGFPlots → PDF | **存在真实计算或试验数据**且注明来源时 | 不把示意曲线写成实测 |
| 与 D1/D2 已公开专利对照 | 来源锚点表/对比矩阵 | 每一关键创新点完成反证后 | 仅摘要比对不可声称权利要求全文检索 |
| 短小纯结构构思 | 无图，清晰文字或一个部件表 | 内容可完整理解时 | 严禁为了套模板增加无用图 |

绘图工具：CTeX/XeLaTeX（中文排版）；Mermaid CLI（mmd → SVG/PNG/PDF）；draw.io Desktop（\`.drawio\` 可编辑源，导出 SVG/PDF）；真实 CAD 使用当前独立机械附图 skill；Pandoc 可作为 Markdown/DOCX 辅助导出但不能绕过结构化内容与来源门禁。

**图源与导出关系**：\`figures/structure.drawio\` → \`figures/structure.pdf\`；\`figures/sequence.mmd\` → \`figures/sequence.svg\` → \`figures/sequence.pdf\`；PDF 或 PNG 才嵌入现有 XeLaTeX 模板。保存源文件和实际导出版本的哈希、工具版本、字体以及转换命令。独立绘图工具可能依赖浏览器/Electron，生产运行需隔离、限额和许可审核。现有 API 仅排版已导出的图，不自动执行这些程序。

## 5. 模板组合策略

\`mechanical\` 强调标号、部件、连接、运动学、结构剖面和可制造性；\`control\` 强调触发条件、状态、时序、互锁、异常处置；\`hybrid\` 依次给机械与控制信息；\`concise\` 用于结构很简单的沟通审阅，省略无数据的扩展表；\`auto\` 依据有无部件与步骤作初选，可人工覆盖。

渲染链：可信结构化技术事实（JSON） → 字段验证/来源编号校验 → 模块选择 → LaTeX 特殊字符逐字符转义 → CTeX 母版 → 内网隔离编译 → 技术评审 → 完成/退回。图片只允许 \`figures/[安全ASCII名].pdf/png/jpg\`，越界引用、TeX 命令注入和符号链接必须阻断。生产不允许 \`--shell-escape\` 或任意远程图片地址。

## 6. 评审决策门与安全

阶段 A 必须解释“是什么、放在哪里、如何连接、何时动作、为什么有效、与公开方案区别在哪、哪里会失败、怎么验证”；每项发明点关联现有技术来源和核验状态。静态报告的 \`valid=true\` 只表示字段满足排版合同，\`review_status=awaiting_engineering_review\` 一直等待真实工程负责人签字。工程评审可以给出技术可实施、需补实验或暂停项目结论。**阶段 A 通过后允许归档结束**。

阶段 B 的 \`patent_draft_save\` 由 \`08b_conversion_approval.json\` 门禁阻断：审批记录含 case_id/run_id/candidate_id/brief_sha256/decision=convert_to_application/approved_by/approved_at/signature；安全审批系统持有 \`PATENT_CONVERSION_APPROVAL_KEY\` 高熵密钥并用 HMAC-SHA256 签名。仅服务端验证，不提供 MCP 签名工具；无签名、密钥长度不足、错案卷、文稿变更、90天过期皆关闭转换。此为本地签名边界；组织级生产须用 Keycloak/OIDC 确认真实审批人、保留双人复核与防重放证据、实施 KMS/PKI 密钥轮换。**转换申请稿许可始终不是向专利局提交许可**。

签名数据计算：按所有字段（不含 signature）进行 UTF-8 JSON 序列化，\`sort_keys=true, ensure_ascii=false, separators=(',',':')\`；企业审批服务使用密钥计算十六进制 HMAC-SHA256 写入 signature。绝不把密钥提交到仓库、MCP 返回或日志。

本地范围仍以单用户、私有 SQLite 和文件系统 ACL 为基础。完全每项目隔离的 SQLite、企业真实身份和项目级 ABAC、PDF 渲染沙箱、异常重试与版本化审批由 #25 与后续生产任务推进。

## 7. 使用与验证

编辑 \`examples/technical_brief_demo.json\`（模拟数据，请勿视为真实已核专利），在受控本机或 ChatGPT/Codex MCP Host 中将真实案卷候选及来源提交 \`patent_brief_save\`；输出 \`08a_technical_brief.json/.tex\`。LaTeX 编辑器在案卷目录运行 \`xelatex -no-shell-escape -interaction=nonstopmode 08a_technical_brief.tex\`；PDF 构建平台必须附加进程权限、超时、内存限额及安全隔离。

运行 \`python -m unittest discover -s tests -p 'test_technical_brief.py' -v\` 和 \`test_conversion_gate.py\`；GitHub CI 校验上述无依赖行为。演示文件中的所有数字、技术机理均为虚构的测试输入，不作为对外公开研发成果。

## 8. 开源上游与法律依据（截至2026-11-18）

- CTeX：https://ctan.org/pkg/ctex
- Mermaid CLI：https://github.com/mermaid-js/mermaid-cli （MIT，生成SVG/PNG/PDF）
- draw.io：https://github.com/jgraph/drawio 与 https://github.com/jgraph/drawio-desktop （须核对嵌入/商用部署和品牌条款）
- Pandoc：https://github.com/jgm/pandoc （可借鉴 AST 转换，非本次核心必需）
- Eisvogel：https://github.com/Wandmalfarbe/pandoc-latex-template （BSD-3-Clause，可借鉴视觉分层，暂未复制其源码）
- 《专利法实施细则》：https://www.cnipa.gov.cn/art/2023/12/21/art_98_189197.html
- 《专利审查指南》2025 年第84号令修改，自2026-01-01施行：https://www.cnipa.gov.cn/art/2025/11/13/art_74_202560.html


## 9. 工程技术方案评审与结案合同

\`patent_brief_audit\` 只评审阶段 A：要求每项主要创新点至少有一条已核验原始专利权利要求正文引用、明确的公开技术对比、当前候选的反证记录、机械理论与可证伪实验，以及已声明的图纸附件完整性。证据不足时仍可继续编辑方案，最终状态为 \`revision_required\`。

通过静态检查后，进入 \`awaiting_dual_human_review\`。组织授权的工程人员与知识产权管理人员独立审查，可信审批服务形成 \`08c_technical_review.json\`，签署 \`approve_technical_brief\`。两名审查人 ID 必须不同。审批对象绑定案卷/运行/候选/技术方案 SHA256、技术结论、专利初筛意见和签字时间；独立签名密钥 \`PATENT_TECHNICAL_REVIEW_KEY\` 不同于申请转换密钥。MCP 提供只读验签，无自签接口。只有证据检查合格且双审阅签名有效时状态 \`technical_complete\`，即可研发结案，无须生成任何权利要求。

研发结案与是否正式申请分开处理：已完成的技术方案可以归档，之后如申请仍要由用户明确作出申请决定，再由另一个独立审批服务签署 \`08b_conversion_approval.json\`。文件修改或签名过期自动失效。以上 HMAC 是本地安全控制，正式多租户环境应由组织身份审批、不可抵赖电子签名、密钥轮换、分级授权和长期审计替代或增强，跟踪 Issue #25。
