---
name: patent-industry-sources
description: "使用 Apache-2.0 授权的 Patent Client Agents / patentkit 等行业开源组件执行真实专利检索，按不同国家选择数据接口、记录结果、权利要求、同族与审查记录。仅在用户具有授权时连接外部 MCP 或数据服务。"
user-invocable: true
---

# 行业专利数据工具与开源组件技能

## 目标

优先使用成熟行业工具获得真实原始专利证据，再与 Mechanical_Patent 的论文检索、发明创新和中国专利撰写工作流结合。当前 ChatGPT/Codex 就是 AI 推理主体，不要求另行配置模型 API。

## 开源组件

- Patent Client Agents：Apache-2.0；固定源码位于 external/patent-client-agents；可在支持 MCP 的 Codex 中使用其原生插件或者 Python 数据客户端。官方文档：https://docs.patentclient.com/ 。
- patentkit：Apache-2.0；固定源码位于 external/patentkit；重点借鉴专利数据对象、特征解析、权利对照和多源一致性检查。其模型调用可选，不属于本系统默认依赖。
- 上游源码可由 scripts/vendor_upstreams.py 复制进入 vendor/ 并在保留版权许可证和变更记录后修改。与已有 EPO OPS 适配器共存，避免重复部署相互冲突的来源。
- 商业数据库仍须另外取得数据使用权；开源 MCP 代码不代表能免费下载全球专利全文。

## 执行步骤

1. 根据公开技术问题选择国家专利库，记录语种、IPC/CPC、专利/申请号与授权限制。
2. 在客户端拥有 MCP 工具且用户明确完成连接授权时，调用实际专利工具进行检索；否则用项目的 EPO 官方适配器或当前 AI 合法联网工具，标明工具缺失。
3. 获取真正的公开号、文档日期、来源、可访问权利要求/说明书、同族及引用信息。
4. 只调用受许可的官方数据 API 或原始开放数据。所有网页 HTML 内容采集必须经 Crawl4AI 并遵守网站规则。
5. 将文献规范化至案卷 02_patents.json，记录原始公开 PDF 在线地址；按 evidence_id 去重并保存缺口。
6. 对创新候选逐特征调用反证检索，保留原文证据和失败结果。

## 保密与合规

Patent Client Agents 的公共托管 MCP 可能需要登录并有速率限制，严禁未授权传输未申请发明全文或机密 CAD。连接外部 MCP 服务需要用户明确同意；不能通过本技能自动替用户安装或连接账户。禁止虚构“116 个来源等于所有来源均已全面接入”。
