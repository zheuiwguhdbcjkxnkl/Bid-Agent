# Deep Agents 架构迁移设计

> 状态：待团队评审
> 日期：2026-08-21
> 决策范围：V1 Agent 运行框架与编排方式
> 上游基线：`specs/11-产品需求文档（PRD）.md`、`specs/09-业务流程与项目状态机.md`、`specs/10-核心业务对象与数据字典.md`

## 一、决策结论

V1不再由项目代码直接编写和维护LangGraph主图、节点、边、共享State和恢复逻辑，改用官方Deep Agents SDK作为Agent Harness。

```text
FastAPI + 领域服务 + PostgreSQL
负责确定性业务流程、权限、版本、人工关口、基线和审计

Celery Worker + Deep Agents
负责复杂语义任务、任务规划、Subagents委派、Skills加载和MCP工具调用
```

允许Deep Agents内部使用LangGraph runtime，但项目业务代码不直接构建LangGraph工作流图。业务状态不得依赖Deep Agents或其底层运行时作为唯一事实源。

## 二、迁移目标

1. 直接复用Deep Agents提供的任务规划、上下文管理、Subagents、Skills、Memory、工具和人工批准机制；
2. 减少团队自行开发Agent编排框架、共享状态、节点协议和上下文压缩的工作量；
3. 保留现有5个逻辑Agent、4个业务Skill和4个MCP工具域的业务边界；
4. 保持PostgreSQL为唯一业务事实源；
5. 保持现有权限、风险、版本、人工确认和审计底线不变；
6. 不修改已经冻结的前端页面功能、布局、交互和视觉风格。

## 三、不属于本次迁移的内容

- 不改变PRD中的V1范围；
- 不把Deep Agents变成通用工作流引擎；
- 不让Agent直接修改项目主状态；
- 不让Agent自动确认要求、报价、章节、审核结论或交接基线；
- 不让Agent绕过FastAPI权限和领域门禁直接调用数据库；
- 不在第一阶段启用可自我修改的Skill；
- 不在第一阶段使用预览状态的异步Subagents；
- 不因为更换Agent框架重新设计当前前端。

## 四、总体架构

```text
浏览器
  ↓
冻结UI基线对应的正式前端
  ↓
FastAPI API
  ├── 身份、权限与Session
  ├── 项目、文件、要求、章节、审核与交接领域服务
  ├── 人工关口与状态转换
  ├── 幂等、版本校验与审计
  └── 创建task_run / agent_run
            ↓
         Celery Worker
            ↓
     DeepAgentRuntimeAdapter
            ↓
        主Deep Agent
        ├── 招标理解与合规Subagent
        ├── 响应规划与评分Subagent
        ├── 标书编制Subagent
        └── 质量与风险复核Subagent
            ↓
      Skills + MCP Tools
            ↓
 PostgreSQL / MinIO / Redis / 外部模型
```

Deep Agents只在Agent运行层承担智能规划与委派。FastAPI领域服务仍控制合法状态和业务事实写入。

## 五、Agent与Subagents设计

### 5.1 主Deep Agent

主Deep Agent替代原Supervisor Agent的智能协调部分，负责：

- 理解当前Agent任务目标；
- 生成和维护本次运行的任务计划；
- 根据任务类型选择专业Subagent；
- 汇总Subagent结构化结果；
- 判断需要补充工具调用、再次委派或结束本次Agent运行；
- 在工具失败、输入不足或结果不确定时返回结构化阻断原因。

主Deep Agent不负责：

- 判断项目状态转换是否合法；
- 直接写入业务表；
- 直接确认人工关口；
- 关闭高风险问题；
- 批准风险豁免；
- 冻结基线；
- 自动外部递交。

### 5.2 结构化A2A与七种决策契约

Deep Agents内部可以使用SDK的自由任务规划和Subagent委派，但自由规划不是业务A2A消息，也不能直接驱动状态变化。所有跨Agent委派和阶段退出必须经过代码层Pydantic契约，并写入运行记录和审计事件。

七种决策继续保留：

```text
DISPATCH_AGENT
WAITING_HUMAN
RETRY_TASK
EXPAND_REVIEW_SCOPE
INVALIDATE_OUTPUTS
BLOCK_WORKFLOW
COMPLETE_STAGE
```

正式契约包括：

- `OrchestrationDecision`：记录主Agent对本阶段下一步的结构化建议；
- `AgentDelegationEnvelope`：记录向Subagent派发的任务、输入引用、Skill版本和工具白名单；
- `SubagentResultEnvelope`：记录Subagent产物引用、发现项、风险信号、未解决事项和建议决策。

`OrchestrationDecision`至少包含`decision_type`、`workflow_run_id`、`agent_run_id`、`project_id`、`current_stage`、`target_agent`、`task_type`、`input_refs`、`input_hash`、`reason_code`、`pending_gate`和`idempotency_key`。

`AgentDelegationEnvelope`至少包含`delegation_id`、`parent_agent_run_id`、`target_subagent`、`task_type`、`input_refs`、`allowed_tools`、`skill_versions`、`expected_output_schema`和`idempotency_key`。

模型生成的计划、todo和自由文本只能用于运行期推理与诊断。只有Schema校验通过的结构化Envelope才能进入A2A审计；只有领域服务再次校验通过后，决策才能产生业务效果。

### 5.3 四个专业Subagent

| Subagent | 主要职责 | 绑定Skill | 主要MCP域 |
|---|---|---|---|
| 招标理解与合规 | 理解采购文件、抽取要求、评分项、时间节点和冲突 | 招标文件理解 | `document.*`、`project.*`、`knowledge.*`、`business.validate_structure` |
| 响应规划与评分 | 建立响应矩阵、匹配证据、规划章节和评分覆盖 | 响应规划与证据匹配 | `project.*`、`knowledge.*`、`business.validate_structure`、`business.validate_quote` |
| 标书编制 | 按确认规划生成带引用的章节候选内容 | 带引用标书编制 | `document.read`、`document.render`、`knowledge.*`、`business.*` |
| 质量与风险复核 | 检查资格、引用、报价、一致性、风险和返工范围 | 质量与风险复核 | `document.*`、`project.*`、`knowledge.*`、`business.*` |

每个自定义Subagent必须显式配置：

- 唯一名称；
- 清晰、可判定的委派描述；
- 独立系统提示词；
- 最小工具白名单；
- 自己的Skill目录；
- Pydantic结构化输出；
- 必要的工具人工批准规则。

自定义Subagent不默认继承主Agent的全部Skills和工具，避免权限范围随着主Agent扩大。

## 六、Skills设计

V1保留4个业务Skill：

```text
backend/agent/skills/
├── tender-understanding/SKILL.md
├── response-planning/SKILL.md
├── cited-authoring/SKILL.md
└── quality-risk-review/SKILL.md
```

每个Skill至少包含：

- 适用任务和禁止用途；
- 输入对象和前置基线；
- 执行步骤；
- MCP工具调用规则；
- 来源引用要求；
- 无证据拒答规则；
- 风险升级和转人工条件；
- 结构化输出Schema说明；
- 失败和重试规则；
- 对应L1、L2和L3评估项。

V1 Skills由开发人员维护并设为只读。Agent不得在生产运行中创建、修改或覆盖正式Skill。

## 七、MCP接入设计

Deep Agents可以直接接收工具列表，但MCP仍需通过客户端配置和适配器加载。V1继续使用1个内部MCP Server、4个工具域和14个方法：

```text
document.ingest
document.read
document.render
document.export

project.get_context
project.validate_inputs
project.validate_transition

knowledge.search
knowledge.read_sources
knowledge.validate_citations

business.validate_structure
business.validate_quote
business.check_consistency
business.evaluate_gate
```

接入流程：

```text
Worker创建MCP Client
→ 加载允许的MCP工具
→ 按Subagent白名单过滤
→ 转换为Deep Agents可用Tools
→ 创建主Agent与Subagents
→ 调用工具时携带项目、用户、版本和幂等上下文
→ MCP Server再次执行权限与输入版本校验
```

禁止事项：

- 不把全部MCP工具无差别提供给所有Subagent；
- 不提供万能`execute_business_operation`工具；
- 不允许Agent直接拼接SQL；
- 不以MCP Session保存项目业务状态；
- 不允许模型参数决定调用者身份、项目权限或输入版本。

## 八、确定性业务状态与人工关口

以下内容继续由FastAPI、领域服务和PostgreSQL控制：

- 项目主状态；
- 文件有效版本；
- 要求、响应规划、章节、审核和交接基线；
- 报价确认；
- 风险接受与豁免；
- 审核问题关闭；
- 交接包接收；
- 人工递交记录；
- 权限、幂等和审计。

四个人工关口保持不变：

1. `REQUIREMENT_BASELINE_CONFIRMATION`；
2. `RESPONSE_PLAN_CONFIRMATION`；
3. `CHAPTER_DRAFT_CONFIRMATION`；
4. `REVIEW_RESULT_CONFIRMATION`。

Deep Agents可以在敏感工具调用前请求批准，但该批准只控制Agent工具执行，不能替代领域人工关口。领域关口仍通过现有HTTP接口提交，并由后端检查角色、状态、输入版本和必确认项。

### 8.1 多段短运行续接语义

一个`workflow_run`贯穿整条业务流程，但每个阶段使用新的短期`agent_run`。Agent完成阶段产物后结束本次运行，领域层将`workflow_run`置为`WAITING_HUMAN`；人工确认后不是恢复旧Agent上下文，而是在同一业务流程中创建下一段`agent_run`和`task_run`。

```text
workflow_run长期存在
→ 阶段agent_run执行并结束
→ 写入DRAFT产物
→ workflow_run进入WAITING_HUMAN
→ 人工接口确认并冻结基线
→ 创建下一阶段agent_run与task_run
→ workflow_run继续RUNNING
```

人工确认事务必须同时完成权限、预期关口、`expected_input_hash`、DRAFT版本和幂等键校验，并写入`workflow_gate_action`、业务基线、下一阶段运行记录和审计事件。事务提交后才发布Celery消息。重复提交同一`Idempotency-Key`返回首次结果，不创建重复运行。

## 九、运行、任务与数据模型

保留：

- `workflow.workflow_run`：业务阶段编排运行；
- `workflow.agent_run`：一次真实Deep Agents调用；
- `workflow.task_run`：Celery异步任务；
- `workflow.workflow_gate_action`：人工关口动作；
- `workflow.project_baseline`和`baseline_item`：冻结业务输入。

调整：

- `workflow_run`不再把LangGraph `thread_id`作为核心语义；
- 新增`runtime_type=DEEP_AGENTS`；
- `agent_run`记录主Agent或Subagent名称、模型、Skill版本、工具清单、输入引用、输出引用、Token、耗时和错误；
- 可选保存SDK运行引用`runtime_run_ref`，但该字段不是业务主键；
- 不单独保存完整模型上下文和长工具输出，使用MinIO对象或业务结果引用；
- Deep Agents内部Checkpoint只用于运行恢复，不作为业务事实源。

状态语义固定为：`workflow_run`表示长期业务流程；`agent_run`表示一次短期Deep Agents调用，完成后不跨领域人工关口恢复；`task_run`表示一次Celery执行尝试，可以按幂等规则重试。

新增`workflow.agent_delegation`或等价追加记录，用于保存`AgentDelegationEnvelope`、接收方、输入哈希、Skill版本、工具白名单、输出引用和最终状态。七种`OrchestrationDecision`作为追加记录保存，不覆盖历史决策。

## 九点一、依赖版本锁定与升级治理

首个实现版本精确锁定：

```text
deepagents==0.7.8
```

使用`uv.lock`锁定完整Python依赖树，CI必须从锁文件安装。不得使用`deepagents>=0.7.8`，不得自动合并Deep Agents及其核心运行时升级。

每次升级必须使用独立PR，记录旧版、新版、发布说明、兼容影响和回滚方式，并执行：主Agent构建、Subagent委派、结构化A2A、Skills按需加载、MCP适配、工具白名单、人工关口续接、异常重试、输入失效和固定评测集回归。升级通过前保留旧锁文件和可回滚部署产物。

## 十、上下文与Memory边界

运行上下文只传递最小控制信息：

```text
request_id
user_id
organization_id
project_id
workflow_run_id
agent_run_id
current_stage
input_refs
input_hash
allowed_actions
```

要求、证据、章节、报价、风险和审核问题通过MCP按需读取，不把整个项目一次性注入主Agent提示词。

V1长期Memory只保存经过批准的稳定规则、术语或项目无关偏好，不保存：

- 未脱敏企业证据；
- 项目报价；
- 尚未确认的要求和结论；
- 审核意见和风险豁免；
- 可替代PostgreSQL业务记录的事实。

## 十一、Celery执行流程

```text
FastAPI校验请求和输入版本
→ 创建task_run与agent_run
→ 提交Celery任务
→ Worker重新读取有效输入
→ 构建MCP工具白名单
→ 创建或取得Deep Agent实例
→ 调用主Agent
→ 主Agent按需委派Subagent
→ 结构化结果通过领域服务校验
→ 写入新业务版本和审计
→ 更新agent_run与task_run
→ 前端轮询获得结果
```

Agent实例可以按模型、Skill版本和工具版本缓存，但每次运行必须重新校验用户、项目、输入版本和允许动作。

## 十二、失败与恢复

| 场景 | 处理方式 |
|---|---|
| 模型限流或临时网络错误 | Celery指数退避，最多按任务策略重试 |
| MCP瞬时错误 | 记录方法和错误码，在允许范围内重试 |
| MCP权限、版本或业务阻断 | 不重试，返回领域错误或转人工 |
| Subagent结构化输出失败 | 进行有限结构修复；持续失败转人工 |
| Worker重启 | 根据PostgreSQL中的任务和运行记录恢复或重新创建幂等任务 |
| 输入版本变化 | 原Agent结果标记`STALE`，基于新输入创建新运行 |
| Agent无法判断影响范围 | 扩大复核范围，不自动缩小范围 |
| Deep Agents运行时不可用 | 保留确定性业务功能，Agent任务显示失败或等待人工 |

## 十三、安全边界

- Deep Agents不能获得数据库直连凭据；
- MCP调用必须使用服务端生成的调用上下文；
- Skills、系统提示词和Subagent配置必须版本化；
- 敏感工具通过白名单和必要的人工批准控制；
- 文件系统Backend默认只允许Agent工作目录，不允许访问服务器任意路径；
- 不默认启用Shell执行工具；确需启用时必须使用隔离Sandbox且不进入V1首个纵向切片；
- 外部模型数据出域规则保持原技术方案要求；
- 所有业务写入仍通过领域服务并产生审计事件。

## 十四、四人团队分工影响

| 成员 | 第一阶段职责 |
|---|---|
| A：集成负责人 | FastAPI骨架、配置、Celery、DeepAgentRuntimeAdapter、公共测试和合并审核 |
| B：账号与项目 | Session、用户角色、项目、成员、权限和工作台项目接口 |
| C：文件与任务 | MinIO、文件版本、哈希、task_run、解析任务骨架和审计 |
| D：Deep Agents基础 | 主Agent、4个Subagent配置、4个Skill目录、MCP适配器和结构化输出契约 |

第一阶段D只建立可测试的Deep Agents运行骨架，不立即实现完整文档理解、检索和标书生成。B、C先完成确定性主链，D使用Fake Tools和受控样例验证Agent委派、Skill加载、工具白名单和结构化输出。

## 十五、迁移顺序

1. 更新项目开发宪法，冻结Deep Agents与确定性领域边界；
2. 更新技术方案、状态机、数据字典、数据库设计和决策记录；
3. 更新Agent编排、总体架构和上下文流转图；
4. 建立FastAPI、Celery和数据库工程骨架；
5. 建立`DeepAgentRuntimeAdapter`和Fake MCP工具测试；
6. 配置主Agent、4个Subagent和4个只读Skill；
7. 接入真实MCP Client和工具白名单；
8. 接入项目—文件—任务确定性主链；
9. 逐步实现要求、规划、编制和复核能力；
10. 按L1、L2、L3评估体系执行回归。

## 十六、验收条件

迁移设计实施完成必须满足：

- 项目代码不直接创建LangGraph `StateGraph`；
- 主Deep Agent可以调用4个专业Subagent；
- 每个Subagent只能访问自己的Skill和MCP工具白名单；
- Skills能够按需加载，而不是全部注入初始提示词；
- MCP工具能携带服务端身份、项目、版本和幂等上下文；
- Agent不能越过领域服务修改项目状态；
- 四个人工关口仍由后端领域接口控制；
- Worker重启、任务重试和输入版本变化不会产生重复业务事实；
- 当前前端页面功能和视觉样式不因迁移而改变；
- 现有L1、L2和L3零容忍门禁不降低。

## 十七、需要同步修订的正式产物

- `specs/07-客户画像与场景设定.md`；
- `specs/09-业务流程与项目状态机.md`；
- `specs/10-核心业务对象与数据字典.md`；
- `specs/13-项目决策与工作记录.md`；
- `specs/15-评估体系与测试计划.md`中的技术运行表述；
- `specs/17-技术方案与系统架构设计.md`；
- `specs/18-数据库设计与实现方案.md`；
- `specs/19-产品经理讲解稿-剥洋葱版.md`；
- `specs/20-讲解稿-业务紧贴版.md`；
- `docs/diagrams/V1总体架构图.html`；
- `docs/diagrams/投标Agent编排架构图.html`；
- `docs/diagrams/记忆与上下文流转图.html`；
- 后续四人协作方案和M1开发计划。

早期`specs/research`继续保留历史研究性质，不逐条改写；正式技术选型以本设计、技术方案和最新项目决策记录为准。

## 十八、讲解口径

在正式代码尚未实施完成前，统一表述为：项目已确认从自维护LangGraph主图迁移到Deep Agents Harness，迁移设计已冻结，代码正在实施。保留结构化A2A、七种调度决策、确定性领域状态机和四个人工关口；不宣称Deep Agents已经完成生产接入，也不表述为完全移除LangGraph依赖，因为Deep Agents内部仍使用LangGraph runtime。
