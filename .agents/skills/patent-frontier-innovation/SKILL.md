---
name: patent-frontier-innovation
description: "主动搜索真实最新公开前沿，按现有专利标题/公开号进行跨技术轴多变种探索，融合 Co-Scientist 研究假说生成、反思、竞争和进化。"
user-invocable: true
---

# 实时科研前沿及专利变种演化

1. 读取 docs/FRONTIER_EVOLUTION.md 与 patent-idea-fission/SKILL.md。
2. 由当前 AI 形成中英技术主题，调用 patent_frontier_scan 获取实际近期公开的 OpenAlex 论文、DOI、日期和方向，记录事实与未获取原文。
3. 用户仅提供最新专利名称/公开号，先查证真实专利；调用 patent_variant_plan，没有明确出处时继续检索。
4. Generation：独立沿机械拓扑、流体/热、材料、制造、控制、机电协同、极限工况及跨领域原理提出差异性构思。
5. Reflection：逐个检查物理规律、具体部件接口、工程可实施性和反证资料。
6. Ranking：将不同专业角色的审查意见成对比较，以多样性、理论、证据等内部优先级排名，不能把 Elo 评分当作创造性结论。
7. Evolution：对被反证、被质疑或有潜力的候选多代裂变，保存父子来源和失败原因；通过 patent_idea_register/evaluate/frontier 保留不同技术机理。
8. 新变种针对专利权利要求、公开论文再做多语种检索；可实施候选提交工程验证和中国发明专利撰写。
9. 所有当下热门方向附实际检索时间、来源、公开日期；不能将论文元数据推断成专利法律结论。

产出：真实前沿索引、已核验母专利、多种技术变种研究任务、技术树、可证伪实验与专利申请待审草稿。
