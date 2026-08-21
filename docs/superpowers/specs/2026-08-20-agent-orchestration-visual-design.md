# Agent 编排架构图设计说明

> 版本：v1.0
> 日期：2026-08-20
> 状态：已确认设计

## 目标

重做 Agent 编排架构图，使读者能够直接看懂投标 Agent 项目中的 Agent 编排、内部 A2A、Skill、MCP 工具、记忆系统和上下文管理，而不是只看到部署组件。

## 已确认边界

- A2A 指平台内部的 Agent-to-Agent 结构化消息协作，运行在统一 LangGraph 主图内。
- V1 不增加独立 A2A Server、外部 A2A 网络协议或动态 Agent 注册中心。
- V1 使用 5 个逻辑 Agent：Supervisor 加 4 个专业 Agent。
- V1 使用 4 个业务 Skill 和 4 个 MCP 工具域，由一个 `bid-tools-mcp` 服务暴露。
- 高风险状态修改仍由 FastAPI 领域服务、PostgreSQL 事务、权限和状态机控制。

## 图中主结构

```text
用户任务
  ↓
Supervisor Agent
  ↓ 内部 A2A 结构化消息
专业 Agent
  ├─ 加载 SkillManifest
  ├─ 获取 Context Envelope
  ├─ 读取短期运行状态与长期业务记忆
  ├─ 通过 MCP Client 调用四类工具域
  └─ 输出结构化结果、引用、阻断或人工关口动作
```

## 视觉节点

- Supervisor Agent：负责路由、重试、暂停、恢复和人工接管。
- 四个专业 Agent：招标理解与合规、响应规划与评分、标书编制、质量与风险复核。
- A2A 消息层：显示任务、上下文引用、结果引用、阻断原因和下一步动作，不表示独立服务。
- Skill Runtime：显示 `SkillManifest`、Prompt、Schema、引用/拒答策略和工具白名单。
- Context Manager：显示 `McpCallContext`、`input_refs`、`input_hash`、权限、版本和人工关口。
- Memory System：区分短期运行记忆与长期项目/企业业务记忆。
- MCP Server：显示 `document.*`、`project.*`、`knowledge.*`、`business.*` 四类工具域。

## 讲解重点

图旁说明必须解释：A2A 不等于 MCP；Skill 不等于 Agent；MCP 工具不拥有最终业务决策权；记忆系统不等于把全部正文塞进上下文；上下文管理负责控制本次运行可见、可引用、可验证的数据范围。
