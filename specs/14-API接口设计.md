# 14 API接口设计

> 版本：v1.2
> 更新日期：2026-08-21
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

认证契约补充如下：

- `POST /api/v1/auth/login`请求体包含`login_name`和`password`；成功后创建PostgreSQL Session并设置安全Cookie。
- `GET /api/v1/auth/session`返回当前用户、平台角色、会话过期时间和允许动作。
- Session Cookie使用`HttpOnly`、生产环境`Secure`和`SameSite=Lax`；写请求通过CSRF Cookie与`X-CSRF-Token`请求头执行双重校验。
- Session默认空闲30分钟过期，绝对最长8小时；退出、修改密码、账号禁用和关键角色变化按规则撤销有效Session。
- `must_change_password=true`时，当前Session只允许查询Session、退出和修改密码；工作台与项目接口返回`PASSWORD_CHANGE_REQUIRED`，改密成功后再开放业务权限。
- 登录接口校验允许的`Origin`或`Referer`并执行账号与来源组合限流；超过限制返回`429 LOGIN_RATE_LIMITED`。

## 四、工作台与项目接口

| 方法 | 路径 | 用途 | 权限 |
|---|---|---|---|
| GET | `/api/v1/me/workbench` | 获取个人待办、最近项目、运行任务和失败摘要 | 已登录 |
| GET | `/api/v1/projects` | 查询有权访问的项目列表 | 已登录 |
| POST | `/api/v1/projects` | 创建投标项目、主标包和负责人成员关系 | 投标经理 |
| PATCH | `/api/v1/projects/{project_id}` | 保存项目草稿或更新允许修改的基本信息 | 投标经理 |
| GET | `/api/v1/projects/{project_id}/overview` | 获取项目阶段、当前行动、阻断和运行摘要 | 项目成员 |
| GET | `/api/v1/projects/{project_id}/context` | 获取有效版本、基线、权限和允许动作 | 项目成员 |
| GET | `/api/v1/projects/{project_id}/members` | 查询当前项目 ACTIVE 成员 | 项目成员 |
| POST | `/api/v1/projects/{project_id}/members` | 添加项目成员 | 项目负责人 |
| PATCH | `/api/v1/projects/{project_id}/members/{user_id}` | 修改成员项目职责 | 项目负责人 |
| DELETE | `/api/v1/projects/{project_id}/members/{user_id}` | 移除项目成员（软删除） | 项目负责人 |
| POST | `/api/v1/projects/{project_id}/decision` | 记录是否参与投标的人工决定 | 投标经理 |

成员接口约定：

- `GET /members` 仅返回 `assignment_status=ACTIVE` 的成员，每项包含 `user_id`、`display_name`、`project_role`、`assigned_at`；调用者必须是项目成员。
- `POST /members` 请求体为 `{ "user_id": "<uuid>", "project_role": "<project_role>" }`，强制使用 `Idempotency-Key`，并校验 CSRF、项目负责人权限、组织归属、账号状态和平台角色与项目职责映射；同键同请求重放首次响应，同键不同请求返回 `409 IDEMPOTENCY_CONFLICT`，ACTIVE 重复成员返回 `409 MEMBER_ALREADY_EXISTS`，REMOVED 成员恢复为 ACTIVE。
- `PATCH /members/{user_id}` 请求体为 `{ "project_role": "<project_role>" }`，校验 CSRF、项目负责人权限、目标成员 ACTIVE 状态和职责映射；负责人不可降级，职责修改天然幂等。
- `DELETE /members/{user_id}` 校验 CSRF 和项目负责人权限，将成员软删除为 `REMOVED`；负责人不可移除，重复移除幂等返回 `204`。
- 成员写操作统一返回错误体 `ErrorResponse`，错误码包括 `FORBIDDEN`、`MEMBER_NOT_FOUND`、`MEMBER_ALREADY_EXISTS`、`MEMBER_ROLE_MISMATCH`、`IDEMPOTENCY_CONFLICT` 和 `CSRF_VALIDATION_FAILED`；成员变更与 `MEMBER_ADDED`、`MEMBER_REMOVED`、`MEMBER_ROLE_CHANGED` 审计事件在同一 PostgreSQL 事务中提交。

创建项目请求采用分步创建口径：

- 第一切片必填：`project_name`、`procurement_method`、`regime_type`、`deadline_at`、`owner_user_id`；
- `project_source`与`external_project_code`不由第一切片的`POST /api/v1/projects`接收，在后续数据连接或采购文件接口中写入`source_record`；
- 后端在同一事务中创建`DRAFT`项目、V1唯一主标包、负责人的`project_member`关系、幂等记录和审计事件；创建人只通过审计事件留痕，若不是负责人则不自动获得项目访问权；
- `owner_user_id`必须属于当前组织、账号有效且平台角色允许承担`BID_MANAGER`；
- 保存项目不启动解析、不创建`task_run`、不运行Agent；
- `POST /api/v1/projects`强制使用`Idempotency-Key`。相同作用域、相同键和相同请求体返回首次状态码与响应；相同键对应不同请求体返回`409 IDEMPOTENCY_CONFLICT`；首次事务失败不缓存成功响应，允许使用同一键安全重试。

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

当前 M1 文件上传子切片只实现文件列表和逻辑文件首个版本上传，契约补充如下：

- `GET /api/v1/projects/{project_id}/documents` 要求有效 PostgreSQL Session 和当前组织内的 ACTIVE 项目成员关系，返回逻辑文件及其版本摘要；不返回文件二进制内容。
- `POST /api/v1/projects/{project_id}/documents` 使用 `multipart/form-data`，字段为 `file`、`document_type` 和 `display_name`；要求有效 Session、`X-CSRF-Token` 和 `Idempotency-Key`，仅当前组织内的 ACTIVE 项目负责人可以上传。
- `document_type` 仅允许 `ANNOUNCEMENT`、`PROCUREMENT_FILE`、`CLARIFICATION`、`CORRECTION`、`ADDENDUM` 和 `BID_TEMPLATE`；本切片支持 PDF、DOCX、XLSX，扩展名必须与 MIME 匹配，单文件最大 200 MB。
- 上传成功创建一个 `procurement_document` 和首个 `document_version`，版本号固定为 `v1`，`parse_status=PENDING`，保存 SHA-256、大小、MIME 和对象存储 URI，并写入 `DOCUMENT_UPLOADED` 审计事件。
- 上传幂等作用域包含实际 `project_id`；请求哈希包含文件类型、显示名、原始文件名、MIME 和内容 SHA-256。同键同请求返回首次 `201` 响应且不重复写对象；同键不同请求返回 `409 IDEMPOTENCY_CONFLICT`；同项目相同内容返回 `409 DOCUMENT_VERSION_EXISTS`。
- 对象写入后若数据库、审计或幂等结果提交失败，服务必须回滚 PostgreSQL 事务并补偿删除对象；对象存储未配置时明确失败，不得默认把生产长期文件保存到进程内存或本地文件系统。
- 本切片上传成功后不启动解析、不创建 `task_run`、不调用 Celery/Redis/Agent。第 10.37 节“上传成功后返回 `task_run_id`”适用于后续接入解析任务后的完整链路；当前阶段由独立 `/parse` 接口创建首次解析任务。

当前 M1 首次解析与任务查询子切片补充如下：

- `POST /api/v1/document-versions/{document_version_id}/parse` 要求有效 Session、`X-CSRF-Token`、`Idempotency-Key` 和当前组织内 ACTIVE 项目负责人；只接受 `parse_status=PENDING` 的版本，成功返回 `202` 和 `StartDocumentParseResponse.task_run`。
- 受理事务在 PostgreSQL 中创建 `document_parse`、`task_run=QUEUED`、幂等成功结果和 `DOCUMENT_PARSE_QUEUED` 审计，并将文件版本改为 `PARSING`；事务提交后才发布 Celery。Broker 发布失败时保留 `QUEUED`，接口仍返回已持久化的 `202` 结果，等待安全补投。
- 同一组织、操作者、版本和幂等键的相同请求重放首次结果且不重复发布；同键不同请求返回 `409 IDEMPOTENCY_CONFLICT`；同一文件版本只允许一个 `QUEUED/DISPATCHED/RUNNING` 的首次解析任务。
- `GET /api/v1/task-runs/{task_run_id}` 和 `GET /api/v1/projects/{project_id}/task-runs` 仅允许当前组织内 ACTIVE 项目成员读取，状态来源只读 PostgreSQL；项目任务列表支持 `task_type`、`task_status` 过滤。
- Celery Worker 原子领取任务后通过内部 Streamable HTTP MCP 调用 `document.ingest`。PDF/图片由内部自托管 MinerU 处理，DOCX 使用 `python-docx`，XLSX 使用 `openpyxl`；输出必须转换和校验为统一 Document IR 后才能持久化。
- 成功时 `document_parse=SUCCEEDED`、`document_version=PARSED`、`task_run=SUCCEEDED`；失败时 `document_parse=FAILED`、`document_version=PARSE_FAILED`、`task_run=FAILED`，原始对象保持不变。

统一错误码包括 `UNAUTHENTICATED`、`FORBIDDEN`、`CSRF_VALIDATION_FAILED`、`IDEMPOTENCY_KEY_REQUIRED`、`IDEMPOTENCY_CONFLICT`、`DOCUMENT_VERSION_EXISTS`、`VALIDATION_ERROR`、`OBJECT_STORAGE_NOT_CONFIGURED` 和 `INTERNAL_ERROR`。

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

四个人工关口固定为`REQUIREMENT_BASELINE_CONFIRMATION`、`RESPONSE_PLAN_CONFIRMATION`、`CHAPTER_DRAFT_CONFIRMATION`和`REVIEW_RESULT_CONFIRMATION`。前端只能调用领域关口查询和动作接口，不得调用任何通用运行时恢复接口绕过领域门禁。

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
- `IDEMPOTENCY_KEY_REQUIRED`：当前写接口要求提供有效的`Idempotency-Key`请求头。
- `INVALID_CREDENTIALS`：登录凭据无效，且不得暴露账号是否存在。
- `VALIDATION_ERROR`：请求字段或业务输入校验失败。
- `PROJECT_CODE_CONFLICT`：内部项目编号唯一约束冲突。
- `OWNER_ROLE_MISMATCH`：项目负责人不存在、不可用或平台角色不兼容。
- `OWNER_ORGANIZATION_MISMATCH`：项目负责人与当前组织不一致。
- `PASSWORD_CHANGE_REQUIRED`：当前账号必须先修改临时密码才能访问业务接口。
- `LOGIN_RATE_LIMITED`：登录失败次数超过账号与来源组合的短期限制。
- `ORIGIN_NOT_ALLOWED`：登录或写请求来源不在允许范围内。
- `SESSION_EXPIRED`：Session超过空闲期限或绝对期限。
- `CSRF_VALIDATION_FAILED`：写请求的CSRF校验失败。
- `INTERNAL_ERROR`：未预期内部错误；响应不得暴露堆栈。

项目创建、创建任务、关口动作、版本确认、风险接受、基线冻结、交接包和递交登记必须支持`Idempotency-Key`。幂等作用域至少包含组织、操作者、HTTP方法和路由；相同键不同请求体返回`IDEMPOTENCY_CONFLICT`。写请求同时校验Session、角色、对象所属项目、当前状态、输入版本和前置门禁。

## 十、与前端契约映射

当前静态前端以`frontend/js/api.js`的数据访问边界和`frontend/js/data.js`的页面场景数据作为接口接入参照，但Mock字段本身不直接决定数据库结构。进入Next.js工程化迁移时，在`frontend/src/contracts`建立Zod Schema，并由后端Pydantic实现同名字段、枚举和错误结构。正式运行后由FastAPI生成OpenAPI，并通过契约测试验证请求字段、响应字段、状态码、权限失败、版本冲突、等待人工和输入失效场景。

API接入和契约迁移不得重新设计当前页面。现有`frontend`中的页面入口、可见功能、布局、主要交互、文案语义和视觉样式为V1前端基线；新增后端状态应映射到现有页面结构，确需调整界面时必须先记录产品与技术决策。
