<!--
Sync Impact Report
Version change: [TEMPLATE] → 1.0.0（首次正式批准，MAJOR：从空模板首次填充完整原则集）
Modified principles: 无（首次制定，非修订）
Added sections:
  - Core Principles I~VII（证据约束生成 / 人工关口与分段短运行 / 结构化契约驱动 / 单一事实源与领域层边界 /
    Deep Agents 架构边界 / 测试先行与真实验证 / 前端冻结基线）
  - 技术栈与基础设施铁律（不可变更）
  - V1 范围边界（Scope）
  - Governance（权威顺序 / 修订流程 / 版本规则 / 合规审查 / 违反后果三级制）
Removed sections: 无
Templates requiring updates:
  - .specify/templates/plan-template.md — ✅ 无需改动（Constitution Check 段落已通用引用宪法文件，
    由 /speckit-plan 按功能填充，不需要硬编码本项目原则）
  - .specify/templates/spec-template.md — ✅ 无需改动（本次宪法未新增强制 spec 章节）
  - .specify/templates/tasks-template.md — ✅ 无需改动（本次宪法未新增强制任务分类）
  - .claude/skills/speckit-plan/SKILL.md — ✅ 已核对，正确引用 .specify/memory/constitution.md
  - .claude/skills/speckit-analyze/SKILL.md — ✅ 已核对，Constitution Authority 描述与本宪法治理规则一致
  - .claude/skills/speckit-checklist/SKILL.md — ✅ 已核对
  - .claude/skills/speckit-clarify/SKILL.md — ✅ 已核对
  - .claude/skills/speckit-converge/SKILL.md — ✅ 已核对
  - .claude/skills/speckit-implement/SKILL.md — ✅ 已核对
  - .claude/skills/speckit-specify/SKILL.md — ✅ 已核对
  - .claude/skills/speckit-taskstoissues/SKILL.md — ✅ 已核对
  - CLAUDE.md — ✅ 已补充本宪法权威关系，并精简为按任务读取的执行层开发约束
  - 项目文件夹导览.md — ✅ 已补充 `.specify/memory/constitution.md` 的目录说明和权威关系
Follow-up TODOs: 无遗留占位符
-->

# 投标文件智能编制与合规审核平台（bid-agent-ai）Constitution

## Core Principles

### I. 证据约束生成，禁止杜撰（Evidence-Constrained Generation）

面向业务的 AI 生成内容（标书章节、要求提取、风险结论、合规判断）MUST 携带可追溯来源引用（招标文件片段、企业证据、历史标书或规则工具输出）；没有来源支撑时 MUST NOT 生成确定性业务结论。报价、金额、税率等商务字段 MUST 由 `QuoteDataBlock` 等确定性工具锁定填充，MUST NOT 由大模型直接生成金额。检索或规则解析失败时 MUST 转为“证据缺口”或转人工处理，MUST NOT 静默编造或忽略缺口。

**Rationale**: 这是产品核心价值主张“证据约束生成 + 人工最终确认”的直接落地，也是 PRD 中“AI 生成内容缺少事实依据、来源定位和可信审核机制”这一业务痛点的对策。招投标场景下一旦允许模型编造业务事实，产品即不可信、不可用。

### II. 人工关口与分段短运行（Human-in-the-Loop Gates）

每个业务阶段 MUST 由 Agent 产出 DRAFT 产物后结束当前 `agent_run`，MUST NOT 由 Agent 自主推进到下一阶段。四个正式人工关口 MUST 只能通过领域 API（`GET/POST .../pending-gate`）处理；前端和 Agent MUST NOT 绕过关口直接修改流程状态。MUST NOT 跨人工关口恢复旧 Agent 对话上下文；每个新阶段 MUST 创建新的 `agent_run`/`task_run`。

**Rationale**: 招投标业务要求人工对关键节点（资格判断、报价确认、审核结论、递交交接）承担最终责任；多段短运行避免长时间挂起的 Agent 会话演变成第二套隐性流程状态。

### III. 结构化契约驱动，禁止自由文本驱动业务状态（Structured Contracts Over Free Text）

七种结构化调度决策（`DISPATCH_AGENT`、`WAITING_HUMAN`、`RETRY_TASK`、`EXPAND_REVIEW_SCOPE`、`INVALIDATE_OUTPUTS`、`BLOCK_WORKFLOW`、`COMPLETE_STAGE`）MUST 是驱动业务流程的唯一决策集合。`OrchestrationDecision`、`AgentDelegationEnvelope`、`SubagentResultEnvelope` MUST 具备 Schema 校验、业务规则校验和审计记录；MUST NOT 使用模型自由文本、未校验的 Subagent 输出或任意字符串直接驱动业务状态。

**Rationale**: 保证 Agent 编排过程可测试、可审计、可回放，避免大模型的不确定输出直接改变生产业务事实。

### IV. 单一事实源与领域层边界（Single Source of Truth）

PostgreSQL MUST 是唯一业务事实源；Redis、Celery 状态、Deep Agents Checkpoint、向量索引/缓存、Agent 记忆 MUST NOT 替代或覆盖 PostgreSQL 业务状态。业务状态、项目状态、流程状态、权限、输入/输出版本、`input_hash`、人工关口、幂等、事务、审计、阶段门禁 MUST 只能通过 FastAPI 领域服务变更；Agent、Skill、MCP、前端 MUST NOT 绕过领域服务直接写入业务主状态。

**Rationale**: 多组件（Agent、Worker、前端、缓存）并存场景下，唯一事实源和单一写入入口是保证一致性、可审计性和可恢复性的底线。

### V. Deep Agents 架构边界（NON-NEGOTIABLE）

V1 MUST 使用 `deepagents==0.7.8` 作为 Agent Harness 并精确锁定版本（`uv.lock`）；项目代码 MUST NOT 直接构建或维护 LangGraph `StateGraph`、主图、节点/边、Checkpoint 业务恢复逻辑或 `interrupt`/`resume` 工作流。Deep Agents 内部依赖 LangGraph runtime 属于 SDK 内部实现；项目业务代码 MUST 通过 Deep Agents Harness 和自研确定性领域层实现业务流程。

**Rationale**: 这是 2026-08-21 记录在案的架构决策（见 `specs/17-技术方案与系统架构设计.md`），用 SDK 能力换取团队规模下的可维护性，同时保留结构化 A2A 和领域层门禁的可测试性、可解释性。

### VI. 测试先行与真实验证（Test-First & Verified Completion）

功能实现前 MUST 先定义接口和数据契约，MUST 编写或更新对应测试；测试覆盖 MUST 包含异常路径（权限不足、输入版本冲突、幂等重复请求、结构化输出失败、Agent 委派失败、MCP 权限拒绝、人工关口未完成等）。MUST 只在真实执行验证命令并确认通过后，才能声称功能完成；MUST NOT 将“代码已写完”表述为“功能已完成”，MUST NOT 伪造或臆测未执行过的测试结果。

**Rationale**: 招投标结果直接关系企业商务利益，未经验证的“完成”声明会掩盖真实风险；真实验证是本项目对交付质量的最低要求。

### VII. 前端冻结基线（Frontend Baseline Freeze）

`frontend/` 目录当前的页面结构、页面功能、交互流程、视觉风格、配色、导航结构、重要文案、用户操作路径 MUST 保持已确认基线不变；MUST NOT 在未经明确批准的情况下新增页面、删除页面或重新设计页面。允许的改动仅限于：内部代码重构、组件化、类型化、接入真实 API、接入统一状态管理、增加契约校验与测试、修复明确的功能缺陷、替换静态 Mock 数据。

**Rationale**: 前端 UI/UX 已完成独立确认，重新设计会引入不可控的产品体验回归和额外评审成本，与 V1“场景做窄、核心做深”的原则冲突。

## 技术栈与基础设施铁律（不可变更）

| 层级 | 技术选型 | 禁止 |
|---|---|---|
| 后端框架 | FastAPI（Pydantic + SQLAlchemy + Alembic） | ❌ Django / Flask / Node.js 承担后端职责 |
| Agent Harness | Deep Agents `deepagents==0.7.8`（版本精确锁定） | ❌ 直接构建 LangGraph StateGraph / 主图 / Checkpoint 业务恢复逻辑 |
| 业务数据库 | PostgreSQL（+ pgvector） | ❌ MongoDB；❌ 用 Redis / Celery / 向量索引替代业务事实源 |
| 对象存储 | MinIO | ❌ 用本地文件系统承载长期业务文件 |
| 异步任务 | Celery + Redis（仅排队、执行、重试，不承载业务事实） | ❌ 用 Celery 状态覆盖 PostgreSQL 业务状态；❌ MCP Server 内嵌套第二层 Celery 任务 |
| 前端框架 | Next.js（App Router + TypeScript）；当前基线为静态 HTML/CSS/JS，迁移只替换工程实现 | ❌ 重新设计页面结构/交互/视觉；❌ 引入与当前基线冲突的新前端框架 |
| MCP 通信 | 内部 Streamable HTTP，单一 `bid-tools-mcp` 服务 | ❌ 每 Worker 独立 stdio 子进程；❌ 用普通函数调用代替 MCP 协议；❌ MCP 暴露公网端口 |
| 密钥管理 | Docker Compose Secrets + 宿主机受保护文件 | ❌ 硬编码密钥；❌ 提交含密钥的 `.env` 到仓库；❌ V1 阶段引入 Vault/云 KMS |
| 部署 | 单机 Docker Compose | ❌ V1 阶段引入 Kubernetes 或多机编排 |

## V1 范围边界（Scope）

| 维度 | 属于 V1 范围 | 不属于 V1 范围 |
|---|---|---|
| 服务对象 | 投标企业内部团队 | 采购人、招标代理机构、评标委员会、其他供应商 |
| 项目粒度 | 单个政府采购信息化服务项目、单个采购包 | 多项目并行调度、跨企业协同（属于 V2/V3） |
| Agent 数量 | 主 Deep Agent + 4 个专业 Subagent | 新增 Agent、动态 Prompt/Skill/MCP 管理页面 |
| 生成范围 | 证据约束的标书初稿、要求提取、风险提示 | 具有法律效力的最终投标文件、无人工确认的一键直接提交 |
| 认证方式 | Argon2id 密码哈希 + 服务端 Session | 自助注册、短信/邮箱验证码、Refresh Token、JWT 黑名单、多因素认证 |
| 检索能力 | PostgreSQL 词法检索 + pgvector + 有限重排 | 独立搜索引擎（Elasticsearch / OpenSearch） |

以下情形 MUST 暂停编码并报告，不得自行决定：新需求没有对应 PRD 范围；需要新增 Agent 或人工关口；需要改变前端页面；需要引入新的基础设施；需要改变数据库事实源；需要修改已冻结契约；需要直接使用 LangGraph；需要绕过领域层；需要新增动态 Prompt/Skill/MCP 管理能力；需要进行大规模重构。

## Governance

**权威顺序**：本宪法是项目最高开发原则；`CLAUDE.md` 是宪法之下的执行层开发约束（文档读取顺序、上下文管理、回复格式等操作细则）；`specs/` 下的正式产品与技术文档（尤其 `11-产品需求文档（PRD）.md`、`13-项目决策与工作记录.md`、`17-技术方案与系统架构设计.md`、`18-数据库设计与实现方案.md`）是本宪法各原则的业务和技术事实来源。三者出现冲突时，MUST 优先修订本宪法或对应正式文档，MUST NOT 在代码中自行选择性实现或静默调和冲突。

**修订流程**：任何人可提出修订；修订 MUST 更新版本号与“Last Amended”日期，MUST 说明修订原因，并同步检查 `.specify/templates/plan-template.md`、`spec-template.md`、`tasks-template.md` 与已安装 `speckit-*` 技能文件是否需要联动更新。

**版本规则**：MAJOR＝原则被移除或做不兼容重新定义（例如替换 Deep Agents 架构、移除人工关口）；MINOR＝新增原则或对现有原则做实质性扩展（例如新增技术栈铁律条目）；PATCH＝措辞澄清、错别字修正、非语义性调整。

**合规审查**：`/speckit-plan`、`/speckit-tasks`、`/speckit-analyze`、`/speckit-converge` 等命令 MUST 在生成或校验产物时对照本宪法执行 Constitution Check；发现违反 MUST 原则的产物 MUST 被列为 CRITICAL 问题并要求调整 spec/plan/tasks，MUST NOT 通过弱化或重新解释宪法条款来放行。

**违反后果**（三级制）：

- 🟢 轻微（格式、措辞、错别字）→ Review 时提醒修正，不阻塞合并；
- 🟡 一般（原则理解偏差，如遗漏异常路径测试、遗漏审计记录）→ Review 指出，修改后合并；
- 🔴 严重（违反技术栈铁律、绕过人工关口或领域层、破坏前端冻结基线、直接构建 LangGraph、以自由文本驱动业务状态）→ PR 打回，重新设计。

**Version**: 1.0.0 | **Ratified**: 2026-08-21 | **Last Amended**: 2026-08-21
