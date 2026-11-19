---
name: patent-figure-cad
description: "按技术方案选择必要的 CAD 结构线稿、draw.io 原理图、Mermaid 流程与时序图；申请阶段另按真实 STEP 模型进行专利附图规范检查。"
user-invocable: true
---

# 图示与机械结构表达技能

## 两种用途
阶段 A 的工程技术方案可使用辅助理解的简明图；阶段 B 专利申请才要求执行专业专利附图质检。图示只用于解释方案，缺 CAD 时明确标注非精确工程示意图。

## 图表选择
- 几何结构/构件装配、运动机构：优先经授权的 SolidWorks/STEP 输出线稿（必要剖面、局部放大、爆炸图），统一 101、102 等部件标号。
- 机械/液压/电气的功能关系或接口：draw.io \`.drawio\` 编辑源，导出 PDF/SVG；AI 可通过可编辑 XML 建模，人工检查位置关系。
- 工艺流程与判断分支：Mermaid flowchart；多主体时序交互：Mermaid sequenceDiagram；复杂状态机：stateDiagram。
- 真实测量或经核验的计算：数据图与轴/单位/来源；已有专利区别：证据对照表。
- 不增加与发明机理无关的装饰图。若文字或零件表足以说明，直接省略。具体判定见 docs/TECHNICAL_BRIEF_STANDARD.md。

## 交付
把原始 \`.drawio/.mmd/.STEP/.SLDASM\` 与输出 \`.svg/.pdf/.png\` 及转换命令、来源哈希、工具版本一起归档。LaTeX 中使用受控 \`figures/\` 相对路径导入已导出 PDF/PNG，源图片未生成则输出待补图纸清单。涉及附图生成不要把截图冒充 CAD 工程图。

## 阶段 B
经转换审批后，读取 external/china-patent-figure-skill 和 external/patent-template，按当前适用规定核查黑白线稿、可辨认性、标号、引线、部件一致性、图号以及说明书的逐图引用；无模型返回待补材料，不自动猜出尺寸精度。

## 自动图源与隔离渲染（2026-11-19）
根据真实工程事实选择图表：diagram_relations 只表达 components[].number 已明确给出的机械/液压/信号连接；process_steps >= 2 生成顺序流程；sequence_messages 显式给出交互双方及消息时生成时序图。没有对应事实时省略图，不补造几何、尺寸、测量曲线、参与者。调用 patent_figure_prepare 生成以 SHA 命名的可编辑 .drawio/.mmd，MCP 可用 patent_figure_source 读取。渲染只能由运营方隔离 figure_worker 运行，输出正式 PDF 和 08e_figure_render.json，经 patent_figure_sync 验证哈希后更新 LaTeX。任何变更触发已签核方案版本失效；工程质量复核必须针对最新版本。详见 docs/TECHNICAL_BRIEF_STANDARD.md 第10节。
