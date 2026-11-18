# AI 客户端接入：ChatGPT、Codex、Dot

## 核心原则

本仓库没有语言模型服务端，也无需 PATENT_LLM_BASE_URL、PATENT_LLM_MODEL、OPENAI_API_KEY 或 Ollama。推理、创新构思、专利文件撰写由运行当前任务的 ChatGPT / Codex / 兼容 AI 客户端完成。这里的 Python 工具只负责数据检索、证据整理、文件生成和形式检查。

## Codex / 本地编码 Agent

1. 克隆本仓库（带子模块）：git clone --recurse-submodules https://github.com/lqepoch/Mechanical_Patent.git
2. 打开仓库作为 Agent 工作区。Codex 读取根 AGENTS.md；可选将 skills/patent-autonomous 和其他技能安装到兼容的 Agent Skills 目录。
3. 告诉 AI：“使用 patent-autonomous，检索全球专利和论文，再形成可实施的机械发明专利底稿”。
4. Agent 自行生成中英检索词，执行 Python 数据工具（可用时），读取证据 JSON，开展创新推演和反证，输出成果，运行静态 QA。普通论文元数据 API 无需模型账号。
5. 数据源凭证（例如 EPO OPS）属于专利检索账号，缺失时必须报告来源覆盖情况；Agent 可用客户端已有联网工具补充。

## ChatGPT 网页

- ChatGPT 网页不会自动读取用户电脑里下载的源码或加载其中的 SKILL.md。需要通过现有 GitHub 连接器、上传相关文件，或者支持操作仓库的 Work 模式让会话真正访问代码。
- 开始会话时指明仓库 URL，并请求读取根 AGENTS.md 和 skills/patent-autonomous/SKILL.md。若拥有合适的连接与工具，ChatGPT 可直接在当前会话开展专利和论文网页检索、生成创新候选和申请文本，并对 GitHub 提交修改。
- 网页会话并不天然拥有用户本机的 Python 环境或 SolidWorks。无法实际运行时标记为“未执行”，不得声称已跑 ANSYS 或已导出 STEP 专利附图。
- 结果可在对话中呈现或通过授权 GitHub 操作写入仓库；高级自动化需在客户端能力范围内配置。

## Dot

Dot 的主动研究、持续监控、GitHub/浏览器执行等实际功能由产品可用性与连接权限决定。本仓库提供可复用任务规范，无法保证 Dot 可以读取本地副本、安装自定义 Skill 或无须授权执行任务。启用前确认 Dot 的官方当前功能及账号配置。

## 保密门禁

- 公开发表的专利和论文可检索；输入给搜索引擎的词也可能泄露尚未申请的技术。
- 默认任何未申请的机械结构、CAD、BOM、试验、工艺数据为保密资料。外发需要分类审核和显式授权。
- 三类结论分开：已有文献证明了什么、AI 理论推演得出了什么、真实仿真/试验完成了什么。
- 系统最终交付可供审查的申请草稿，未自动获得申请授权或法律意见。
