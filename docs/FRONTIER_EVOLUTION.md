# 前沿雷达与最新专利变种的研究算法

## 当下公开前沿
patent_frontier_scan 使用 OpenAlex 真实 API 和当前案卷外发审批。用户可给 1-6 组中英文主题，按 7-730 天发表窗口、日期降序读取 DOI、论文标题、OpenAlex ID、发表日期、主要主题；保存每次查询时间和失败记录。OpenAlex 元数据只能证明它在提供者索引中的公开记录，全文/工程机理仍需核对。

注意：OpenAlex from_publication_date 是论文发表日期，不等于该文献首次进入数据库的日期。from_updated_date 等精确同步接口要求更高等级的服务计划。最新发现与专利公开有延迟，不能据此证明新颖性。

## 最新公开专利的多方向变种
专利名称或公开号输入 patent_variant_plan 后，先在该项目案卷内核对对应真实专利。没找到返回 source_discovery_required；同名多件要求先选定真实公开号。确认母专利后按八种技术思维发散：
1. 机构/流道拓扑重构；
2. 替代物理机理；
3. 机械结构与控制系统协同；
4. 逆向边界工况；
5. 跨领域机理迁移；
6. 失效链反转；
7. 减件与可维护性；
8. 正交技术方案组合。

输出的是研究任务，需由当前 AI 提供结构、控制逻辑、动力/流体约束、理论计算与有效试验，并针对各个候选开展新的全球专利/论文反证。

## 吸收开源方法
- IdeaForge：TRIZ、SCAMPER、方法交叉融合和关联证据；
- AutoPatent：阶段状态、否定检索后再推演；
- Trinno：可证伪假说、AutoResearch、回滚；
- Co-Scientist（Apache-2.0）：Generation、Reflection、Elo Ranking、Evolution、Proximity、Meta-review 竞争进化与证据来源。参考 https://github.com/Ahmad-Jaradat-Space/Co-Scientist 及 Google DeepMind 公开研究。

下一阶段由 Codex Host 多智能体依序或并行执行上述各专业角色，对每代方案留存父子谱系、反对理由、模型/仿真或实验状态。Elo 和多样性评分只能排序研究价值，不能代替独立创造性、充分公开和 FTO 判断。

官方 API：https://help.openalex.org/api/ ，https://help.openalex.org/api/filtering/ ，https://help.openalex.org/api/sorting/ 。
