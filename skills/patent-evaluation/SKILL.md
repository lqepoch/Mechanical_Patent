---
name: patent-evaluation
description: "使用企业自有、授权明确的机械专利标注集，对全球专利检索排序、同族召回率、反证证据质量和专利撰写能力建立可复现实验；默认拒绝 CC BY-NC 等非商业评测数据。"
user-invocable: true
---

# 企业专利检索与撰写质量评测技能

## 工作目标

借鉴 PatSnap PatentAgentBench 的八类专业任务与专利查新指标，形成研发系统的质量闭环。无需模型推理 API。代码中的 benchmarks.py 已提供严格、可复现的专利检索召回与排序评测。

## 输入

企业有权使用的 JSONL 标注集、检索排序结果和独立的 rights.json 许可声明。标注记录包含 case_id、relevant_publications 或 relevant_families；预测记录包含 case_id 与 ranked_publications。

## 执行方式

运行：

    python -m mechanical_patent benchmark --gold examples/benchmark_demo/gold.jsonl --results examples/benchmark_demo/results.jsonl --rights examples/benchmark_demo/rights.json --output cases/benchmark-output.json

输出宏平均 Hit@1/5/10/20、Recall@1/5/10/20、MRR@1/5/10/20、样本数、未返回数和逐案例明细。未预测的案例默认计零。历史不同版本的检索引擎使用同一冻结标注集与查询条件作回归比较。

## 专业指标拓展

- 新颖性检索：审查员引用的 X 类文献召回、同族展开召回、专家复核精确度。
- 专利反证：Claim Chart 中每个技术特征能否被真实原文支持。
- 申请撰写：独立权利要求完整性、说明书支持、技术效果与实施方式的可复现性。
- 审查意见：对引用文献的理解、答复策略、修改是否超出原始公开。
- 风险与 FTO：单独按目标司法辖区、时间、有效权项评审；AI 评分不得充当法律结论。

## 数据权利门禁

patsnap/patent-bench 的整体数据集是 CC BY-NC 4.0，企业评测默认禁止复制与使用；其部分评测代码可按单独 Apache-2.0 许可评估重用。PatSnap PatentAgentBench 的 MIT 仓库与子数据集采用不同许可，所有实际题库必须逐项取得合法授权。当前示例全部是合成数据，不能声称实际性能水平。
