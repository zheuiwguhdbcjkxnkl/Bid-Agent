# 14 API接口设计

> 版本：v1.1
> 更新日期：2026-08-20
> 文档状态：V1 API契约基线
> 上游文档：`11-产品需求文档（PRD）.md`、`09-业务流程与项目状态机.md`、`10-核心业务对象与数据字典.md`、`17-技术方案与系统架构设计.md`

## 一、文档职责

本文档定义V1前后端共享的HTTP资源、路径、权限、异步任务和人工关口契约。产品范围以PRD为准，字段语义以数据字典为准，工作流和部署边界以技术方案为准。

## 二、统一约定

- 基础路径：`/api/v1`，本文所有接口均写完整路径。
- 认证方式：PostgreSQL Session与安全Cookie，不使用前端持久化JWT。
- 内容类型：除文件上传、下载外统一使用`application/json`。
- 请求追踪：每个请求返回或记录`request_id`；异步任务返回`task_run_id`。
- 时间格式：ISO 8601带时区时间。
- 主键格式：UUID；分页使用`page`、`page_size`、`total`。
- 成功响应直接返回契约对象；错误响应统一为`code`、`message`、`request_id`、`details`。
- 长任务创建返回`202 Accepted`，客户端通过任务接口轮询，不保持长连接。

## 三、认证与账号接口

| 方法 | 路径 | 用途 | 权限 |
|---|---|---|---|
| POST | `/api/v1/auth/login` | 账号密码登录 | 匿名 |
| GET | `/api/v1/auth/session` | 查询当前会话和允许动作 | 已登录 |
| POST | `/api/v1/auth/logout` | 撤销当前会话 | 已登录 |
| POST | `/api/v1/auth/password/change` | 修改本人密码并撤销其他有效Session | 已登录 |
| POST | `/api/v1/admin/users` | 创建正式账号 | 系统管理员 |
| PATCH | `/api/v1/admin/users/{user_id}` | 修改用户状态和平台角色 | 系统管理员 |
| POST | `/api/v1/admin/users/{user_id}/password-reset` | 管理员重置密码并要求首次修改 | 系统管理员 |
| POST | `/api/v1/admin/users/{user_id}/sessions/revoke` | 撤销用户全部有效Session | 系统管理员 |

登录失败返回`401 INVALID_CREDENTIALS`，不得暴露账号是否存在。V1不开放自行注册、短信登录、社交登录或密码找回邮件。

## 四、工作台与项目接口

| 方法 | 路径 | 用途 | 权限 |
|---|---|---|---|
| GET | `/api/v1/me/workbench` | 获取个人待办、最近项目、运行任务和失败摘要 | 已登录 |
| GET | `/api/v1/projects` | 查询有权访问的项目列表 | 已登录 |
| POST | `/api/v1/projects` | 创建投标项目、主标包和创建人成员关系 | 投标经理 |
| PATCH | `/api/v1/projects/{project_id}` | 保存项目草稿或更新允许修改的基本信息 | 投标经理 |
| GET | `/api/v1/projects/{project_id}/overview` | 获取项目阶段、当前行动、阻断和运行摘要 | 项目成员 |
| GET | `/api/v1/projects/{project_id}/context` | 获取有效版本、基线、权限和允许动作 | 项目成员 |
| POST | `/api/v1/projects/{project_id}/members` | 添加项目成员 | 投标经理 |
| POST | `/api/v1/projects/{project_id}/decision` | 记录是否参与投标的人工决定 | 投标经理 |

创建项目请求至少包含`project_name`、`procurement_mode`、`regime_type`和`deadline_at`。后端在同一事务中创建项目、唯一主标包、创建人成员关系和审计事件。

## 五、文件、解析与任务接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/projects/{project_id}/documents` | 查询采购文件、澄清文件及版本 |
| POST | `/api/v1/projects/{project_id}/documents` | 上传文件并创建文件逻辑对象与版本 |
| POST | `/api/v1/projects/{project_id}/documents/{document_id}/versions` | 上传已存在文件的新版本 |
| GET | `/api/v1/document-versions/{document_version_id}` | 查询文件版本和解析状态 |
| POST | `/api/v1/document-versions/{document_version_id}/parse` | 创建首次解析任务 |
| POST | `/api/v1/document-versions/{document_version_id}/reparse` | 基于修正或解析策略重新解析 |
| GET | `/api/v1/document-versions/{document_version_id}/segments` | 查询可定位文档片段 |
| POST | `/api/v1/document-segments/{segment_id}/corrections` | 提交人工修正 |
| POST | `/api/v1/document-corrections/{correction_id}/review` | 审核人工修正 |
| GET | `/api/v1/task-runs/{task_run_id}` | 查询解析、OCR、Agent或导出任务进度 |
| GET | `/api/v1/projects/{project_id}/task-runs` | 查询项目运行任务 |

原文件进入MinIO，PostgreSQL保存对象键、SHA-256、版本、分类、权限、解析状态和来源关系。上传、解析、OCR、复杂图表理解和导出均使用`task_run`记录最终状态。

## 六、要求、响应规划与人工关口接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/projects/{project_id}/requirements` | 查询资格条件、实质性要求、评分项和时间节点 |
| PATCH | `/api/v1/requirements/{requirement_id}` | 人工修正确认要求 |
| POST | `/api/v1/requirements/{requirement_id}/split` | 拆分混合要求 |
| POST | `/api/v1/requirements/{requirement_id}/merge` | 合并重复要求 |
| POST | `/api/v1/requirement-baselines/validation` | 校验要求基线门禁 |
| POST | `/api/v1/requirement-baselines/confirmation` | 确认要求基线 |
| GET | `/api/v1/projects/{project_id}/response-plan` | 查询响应矩阵、评分映射和章节任务 |
| POST | `/api/v1/projects/{project_id}/response-plan/generate` | 创建响应规划任务 |
| PATCH | `/api/v1/response-matrix-entries/{entry_id}` | 修改响应方式、证据用途和章节映射 |
| POST | `/api/v1/response-plan-baselines/validation` | 校验响应规划门禁 |
| POST | `/api/v1/response-plan-baselines/confirmation` | 确认响应规划 |
| GET | `/api/v1/workflow-runs/{workflow_run_id}/pending-gate` | 查询当前阶段级人工关口 |
| POST | `/api/v1/workflow-runs/{workflow_run_id}/pending-gate/actions` | 提交确认、退回或取消动作 |

四个人工关口固定为`REQUIREMENT_BASELINE_CONFIRMATION`、`RESPONSE_PLAN_CONFIRMATION`、`CHAPTER_DRAFT_CONFIRMATION`和`REVIEW_RESULT_CONFIRMATION`。前端不得调用通用LangGraph Resume接口绕过领域门禁。

## 七、证据、编制、审核与风险接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/projects/{project_id}/evidence-items` | 查询项目可用企业证据及引用状态 |
| GET | `/api/v1/projects/{project_id}/quotation-versions` | 查询已确认报价版本和校验结果 |
| GET | `/api/v1/projects/{project_id}/sections` | 查询章节、负责人、内容块和生成状态 |
| POST | `/api/v1/sections/{section_id}/generate` | 基于确认规划创建章节生成任务 |
| PATCH | `/api/v1/content-blocks/{block_id}` | 保存人工编辑并维护锁定和版本信息 |
| POST | `/api/v1/content-blocks/{block_id}/regenerate` | 定向重写未锁定内容块 |
| POST | `/api/v1/chapter-draft-baselines/validation` | 校验章节初稿门禁 |
| POST | `/api/v1/chapter-draft-baselines/confirmation` | 确认章节初稿 |
| GET | `/api/v1/projects/{project_id}/reviews` | 查询审核任务、问题和风险 |
| POST | `/api/v1/projects/{project_id}/review-runs` | 创建审核与风险复核任务 |
| PATCH | `/api/v1/review-issues/{issue_id}` | 修改审核问题处理状态 |
| POST | `/api/v1/review-issues/{issue_id}/submit-fix` | 提交结构化修改结果 |
| POST | `/api/v1/review-issues/{issue_id}/review` | 审核修改结果 |
| POST | `/api/v1/risks/{risk_id}/acceptance` | 记录有权限人员的风险接受或豁免 |
| POST | `/api/v1/review-result-baselines/validation` | 校验审核结果门禁 |
| POST | `/api/v1/review-result-baselines/confirmation` | 确认审核结果 |

Agent只能生成建议和新版本，不能静默覆盖人工锁定内容、确认报价、关闭高风险问题或通过人工关口。

## 八、交接、导出与递交接口

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/v1/handover-baselines/validation` | 校验交接门禁和冻结输入版本 |
| POST | `/api/v1/handover-baselines/confirmation` | 创建有效Handover Baseline |
| POST | `/api/v1/projects/{project_id}/handover-packages` | 创建DOCX/PDF导出和交接包任务 |
| GET | `/api/v1/projects/{project_id}/handover-packages` | 查询交接包、文件清单和哈希 |
| POST | `/api/v1/handover-packages/{package_id}/acceptance` | 递交责任人确认接收交接包 |
| POST | `/api/v1/projects/{project_id}/submissions` | 登记人工外部递交 |
| PATCH | `/api/v1/submissions/{submission_id}` | 修正允许修改的递交记录 |
| POST | `/api/v1/submissions/{submission_id}/receipts` | 添加人工取得的回执记录 |
| GET | `/api/v1/projects/{project_id}/baselines` | 查询要求、规划、章节、审核和交接基线 |
| GET | `/api/v1/projects/{project_id}/timeline` | 查询项目业务时间线 |
| GET | `/api/v1/projects/{project_id}/audit-events` | 查询项目审计事件 |
| GET | `/api/v1/projects/{project_id}/audit-events/export` | 导出脱敏审计记录 |

交付链固定为“审核结果确认 → 交接门禁 → Handover Baseline → 交接包 → 责任人接收 → 人工递交登记”。系统不连接电子交易平台自动递交。

## 九、错误码、版本与幂等

- `UNAUTHENTICATED`：未登录。
- `FORBIDDEN`：没有资源或动作权限。
- `INVALID_STATE_TRANSITION`：项目或工作流状态不允许当前动作。
- `VERSION_CONFLICT`：客户端引用版本落后或输入已失效。
- `GATE_NOT_READY`：人工关口仍存在未处理必确认项或阻断问题。
- `PARSE_FAILED`：解析失败，需要人工处理或有限重试。
- `TASK_NOT_FOUND`：任务不存在或不属于当前项目。
- `IDEMPOTENCY_CONFLICT`：幂等键已对应另一份请求。

创建任务、关口动作、版本确认、风险接受、基线冻结、交接包和递交登记必须支持`Idempotency-Key`。写请求同时校验Session、角色、对象所属项目、当前状态、输入版本和前置门禁。

## 十、与前端契约映射

当前静态前端以`frontend/js/api.js`的数据访问边界和`frontend/js/data.js`的页面场景数据作为接口接入参照，但Mock字段本身不直接决定数据库结构。进入Next.js工程化迁移时，在`frontend/src/contracts`建立Zod Schema，并由后端Pydantic实现同名字段、枚举和错误结构。正式运行后由FastAPI生成OpenAPI，并通过契约测试验证请求字段、响应字段、状态码、权限失败、版本冲突、等待人工和输入失效场景。

API接入和契约迁移不得重新设计当前页面。现有`frontend`中的页面入口、可见功能、布局、主要交互、文案语义和视觉样式为V1前端基线；新增后端状态应映射到现有页面结构，确需调整界面时必须先记录产品与技术决策。
