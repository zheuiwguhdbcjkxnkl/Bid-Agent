# M1 认证与项目第一纵向切片实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 建立可运行、可迁移、可测试的 FastAPI 后端，完成登录会话、个人工作台、项目创建、项目列表和项目总览的第一条真实 PostgreSQL 纵向切片。

**架构：** FastAPI 只负责 HTTP 契约与依赖注入，确定性领域服务负责权限、Session、幂等、事务和审计，SQLAlchemy/Alembic 负责 PostgreSQL 持久化。Session Token 原文只进入安全 Cookie，PostgreSQL 保存哈希；项目创建将项目、主标包、负责人成员关系、幂等成功结果和审计事件放在同一事务中。Redis 只作为登录失败限流的可选快速存储，失败时退化到进程内保守限流，绝不承载 Session 或业务幂等事实。

**技术栈：** Python 3.12、uv、FastAPI、Pydantic Settings、SQLAlchemy 2.x、Alembic、psycopg 3、PostgreSQL、argon2-cffi、redis-py、pytest、pytest-asyncio、HTTPX、Ruff、mypy。Python 3.12 与下述密码规则在现有正式规格中尚未单独冻结，本计划将其作为实现基线提交审查；计划获批即视为同意该实现基线，若正式规格在实施前给出不同约束则暂停并同步计划。

---

## 0. 实施前提与硬边界

- 权威设计：`docs/development/2026-08-21-M1认证与项目纵向切片设计.md`。
- 相关正式规格：`specs/10-核心业务对象与数据字典.md`、`specs/14-API接口设计.md`、`specs/15-评估体系与测试计划.md`、`specs/17-技术方案与系统架构设计.md`、`specs/18-数据库设计与实现方案.md`。
- 只实现以下 8 个接口：
  - `POST /api/v1/auth/login`
  - `GET /api/v1/auth/session`
  - `POST /api/v1/auth/logout`
  - `POST /api/v1/auth/password/change`
  - `GET /api/v1/me/workbench`
  - `GET /api/v1/projects`
  - `POST /api/v1/projects`
  - `GET /api/v1/projects/{project_id}/overview`
- 不实现管理员账号接口、采购文件、Celery、Deep Agents、MCP、MinIO、人工关口或前端真实 API 接入。
- 不使用 SQLite；数据库测试一律连接独立 PostgreSQL 测试库。
- 不改变 `frontend/` 冻结基线。
- 新增依赖只服务本切片：FastAPI/Pydantic/SQLAlchemy/Alembic/psycopg 为宪法指定后端栈，argon2-cffi 实现 Argon2id，redis-py 实现已批准的登录限流快速存储，HTTPX/pytest/Ruff/mypy 只用于测试和质量门禁；这些依赖采用其上游开源许可证，实施时必须由 `uv.lock` 精确锁定并在 `backend/README.md` 记录许可证核对结果。部署仅新增 FastAPI 进程和 PostgreSQL 连接；Redis 故障可降级，不新增 Celery、Agent 或对象存储服务。
- 每次进入编码前按项目约束输出：本次任务、实际读取章节、准备修改文件、预计验证方式。
- 计划中的 Commit 步骤是检查点，不构成本次 Git 授权。只有用户明确授权后才能执行 `git add`/`git commit`；未授权时跳过并在进度中如实说明。

## 1. 目标文件结构与职责

```text
backend/
├── .python-version                         # 固定 Python 3.12
├── .env.example                            # 仅非敏感示例，不含真实凭据
├── README.md                               # 本地启动、测试库与验证命令
├── pyproject.toml                          # 依赖与 Ruff/mypy/pytest 配置
├── uv.lock                                 # 完整 Python 依赖锁
├── compose.test.yaml                       # 独立 PostgreSQL 测试库
├── alembic.ini                             # Alembic 配置
├── migrations/
│   ├── env.py                              # 加载 metadata 与 DATABASE_URL
│   ├── script.py.mako
│   └── versions/
│       └── 0001_m1_foundation.py           # IAM、项目、审计初始结构
├── app/
│   ├── __init__.py
│   ├── main.py                             # 应用工厂、中间件、路由注册
│   ├── api/router.py                       # `/api/v1` 总路由
│   ├── core/
│   │   ├── config.py                       # 环境配置与测试库防误连
│   │   ├── db.py                           # AsyncEngine/AsyncSession
│   │   ├── errors.py                       # 统一领域错误与响应映射
│   │   ├── request_id.py                   # 请求追踪中间件
│   │   ├── security.py                     # Argon2id、随机 Token、SHA-256
│   │   ├── origin.py                       # Origin/Referer 校验
│   │   ├── csrf.py                         # 双提交 Cookie 校验
│   │   └── rate_limit.py                   # Redis + 进程内降级限流
│   ├── db/
│   │   ├── base.py                         # DeclarativeBase 与 metadata
│   │   └── models/
│   │       ├── iam.py                      # organization/user/session/idempotency
│   │       ├── project.py                  # project/package/member
│   │       ├── audit.py                    # 追加式 audit_event
│   │       └── __init__.py                 # Alembic 模型聚合导入
│   ├── audit/service.py                    # 审计事件追加写
│   ├── auth/
│   │   ├── schemas.py                      # 登录、Session、改密契约
│   │   ├── repository.py                   # 用户与 Session 数据访问
│   │   ├── service.py                      # 登录、会话、退出、改密
│   │   ├── dependencies.py                 # 当前 Session、CSRF、首次改密门禁
│   │   └── api.py                          # 四个认证接口
│   └── projects/
│       ├── schemas.py                      # 创建、列表、总览、工作台契约
│       ├── repository.py                   # 项目写入与成员查询
│       ├── idempotency.py                  # 请求摘要、占位、重放与冲突
│       ├── service.py                      # 项目创建事务
│       ├── queries.py                      # 工作台、列表、总览只读聚合
│       └── api.py                          # 四个业务接口
└── tests/
    ├── conftest.py                         # PostgreSQL、迁移、事务、HTTP 客户端
    ├── factories.py                        # 组织、用户、Session 测试数据
    ├── unit/
    │   ├── test_security.py
    │   ├── test_origin_csrf.py
    │   ├── test_rate_limit.py
    │   ├── test_session_policy.py
    │   └── test_project_policy.py
    ├── db/
    │   ├── test_migrations.py
    │   └── test_constraints.py
    ├── integration/
    │   ├── test_auth_login.py
    │   ├── test_auth_session_logout.py
    │   ├── test_password_change.py
    │   ├── test_password_change_gate.py
    │   ├── test_project_create.py
    │   ├── test_project_idempotency.py
    │   ├── test_project_idempotency_concurrency.py
    │   ├── test_project_transaction_rollback.py
    │   ├── test_project_queries.py
    │   └── test_workbench.py
    └── contract/
        ├── test_error_contract.py
        └── test_openapi.py
```

---

### 任务 1：建立可验证的后端工程基座

**文件：**
- 创建：`backend/.python-version`
- 创建：`backend/.env.example`
- 创建：`backend/README.md`
- 创建：`backend/pyproject.toml`
- 创建：`backend/compose.test.yaml`
- 创建：`backend/app/__init__.py`
- 创建：`backend/app/main.py`
- 创建：`backend/tests/conftest.py`
- 创建：`backend/tests/contract/test_openapi.py`
- 生成：`backend/uv.lock`

测试隔离统一采用“独立 `_test` 数据库 + 会话开始升级迁移 + 每个用例前后 `TRUNCATE ... RESTART IDENTITY CASCADE`”。不要用包裹整个测试的单连接回滚，因为任务 10 必须让多个独立连接看到同一已提交的 PostgreSQL 状态。

- [ ] **步骤 1：创建依赖清单和独立测试数据库**

`backend/pyproject.toml` 使用以下最小依赖，不加入 Celery、Deep Agents、MCP 或 MinIO：

```toml
[project]
name = "bid-agent-ai-backend"
version = "0.1.0"
description = "bid-agent-ai V1 后端"
requires-python = ">=3.12,<3.13"
dependencies = [
  "alembic",
  "argon2-cffi",
  "fastapi",
  "httpx",
  "psycopg[binary,pool]",
  "pydantic-settings",
  "redis",
  "sqlalchemy[asyncio]",
  "uvicorn[standard]",
]

[dependency-groups]
dev = [
  "mypy",
  "pytest",
  "pytest-asyncio",
  "ruff",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy", "sqlalchemy.ext.mypy.plugin"]

[tool.uv]
package = false
```

`backend/compose.test.yaml`：

```yaml
services:
  postgres-test:
    image: postgres:17.6-alpine
    environment:
      POSTGRES_DB: bid_agent_test
      POSTGRES_USER: bid_agent
      POSTGRES_PASSWORD: bid_agent_test
    ports:
      - "55432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bid_agent -d bid_agent_test"]
      interval: 2s
      timeout: 2s
      retries: 30
```

`.env.example` 只放示例值：

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+psycopg://bid_agent:change-me@localhost:5432/bid_agent
ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
SESSION_COOKIE_SECURE=false
REDIS_URL=redis://localhost:6379/0
```

- [ ] **步骤 2：先写失败的应用契约测试**

`backend/tests/contract/test_openapi.py`：

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_endpoint_is_available() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **步骤 3：安装并运行测试，确认因应用工厂不存在而失败**

运行：

```bash
cd backend
uv lock
uv sync --dev
uv run pytest tests/contract/test_openapi.py::test_health_endpoint_is_available -q
```

预期：FAIL，错误包含 `ModuleNotFoundError` 或 `cannot import name 'create_app'`。

- [ ] **步骤 4：实现最小应用工厂**

`backend/app/main.py`：

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="bid-agent-ai API", version="0.1.0")

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **步骤 5：验证基座通过**

运行：

```bash
cd backend
docker compose -f compose.test.yaml up -d --wait
uv run pytest tests/contract/test_openapi.py -q
uv run ruff check app tests
uv run ruff format --check app tests
```

预期：1 个测试 PASS，Ruff 两条命令均退出码 0。

- [ ] **步骤 6：Commit 检查点（仅在获得 Git 授权后）**

```bash
git add backend/.python-version backend/.env.example backend/README.md backend/pyproject.toml backend/uv.lock backend/compose.test.yaml backend/app backend/tests
git commit -m "chore: 建立M1后端测试基座"
```

---

### 任务 2：统一配置、请求追踪和错误契约

**文件：**
- 创建：`backend/app/core/config.py`
- 创建：`backend/app/core/errors.py`
- 创建：`backend/app/core/request_id.py`
- 修改：`backend/app/main.py`
- 测试：`backend/tests/contract/test_error_contract.py`

- [ ] **步骤 1：编写失败的错误契约测试**

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import DomainError, install_exception_handlers
from app.core.request_id import RequestIdMiddleware


def build_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    install_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise DomainError(status_code=403, code="FORBIDDEN", message="没有访问权限")

    return app


def test_domain_error_has_request_id_and_stable_shape() -> None:
    response = TestClient(build_test_app()).get(
        "/boom", headers={"X-Request-ID": "req-contract-001"}
    )

    assert response.status_code == 403
    assert response.headers["X-Request-ID"] == "req-contract-001"
    assert response.json() == {
        "code": "FORBIDDEN",
        "message": "没有访问权限",
        "request_id": "req-contract-001",
        "details": {},
    }
```

- [ ] **步骤 2：运行测试确认失败**

运行：`cd backend && uv run pytest tests/contract/test_error_contract.py -q`

预期：FAIL，错误包含 `No module named 'app.core'`。

- [ ] **步骤 3：实现统一错误和 request_id 中间件**

核心接口必须固定为：

```python
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

@dataclass(slots=True)
class DomainError(Exception):
    status_code: int
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)
```

`RequestIdMiddleware` 按以下规则实现：优先接受非空 `X-Request-ID`，否则生成 `uuid4().hex`；写入 `request.state.request_id`；所有响应返回同值的 `X-Request-ID`。`install_exception_handlers()` 同时映射 `DomainError`、FastAPI 请求校验错误和未预期异常；后两者分别返回 `VALIDATION_ERROR` 和 `INTERNAL_ERROR`，内部错误体不得包含异常类名、堆栈或数据库信息。

`backend/app/core/config.py` 使用 `BaseSettings`，至少定义：

```python
class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str
    allowed_origins: list[str] = ["http://localhost:8000"]
    session_cookie_name: str = "bid_session"
    csrf_cookie_name: str = "bid_csrf"
    session_cookie_secure: bool = False
    session_idle_minutes: int = 30
    session_absolute_hours: int = 8
    login_failure_limit: int = 5
    login_failure_window_seconds: int = 900
    redis_url: str | None = None
```

当 `app_env == "test"` 时，解析后的数据库名不包含 `_test` 必须抛出 `ValueError`，防止测试误连开发或生产库。

- [ ] **步骤 4：注册中间件和异常处理器并验证**

运行：

```bash
cd backend
uv run pytest tests/contract/test_error_contract.py -q
uv run ruff check app/core tests/contract
uv run mypy app/core
```

预期：测试 PASS，静态检查退出码 0。

- [ ] **步骤 5：Commit 检查点（仅在获得 Git 授权后）**

```bash
git add backend/app/core backend/app/main.py backend/tests/contract/test_error_contract.py
git commit -m "feat: 统一请求追踪与错误契约"
```

---

### 任务 3：建立 PostgreSQL 模型、迁移和约束

**文件：**
- 创建：`backend/alembic.ini`
- 创建：`backend/migrations/env.py`
- 创建：`backend/migrations/script.py.mako`
- 创建：`backend/migrations/versions/0001_m1_foundation.py`
- 创建：`backend/app/core/db.py`
- 创建：`backend/app/db/base.py`
- 创建：`backend/app/db/models/iam.py`
- 创建：`backend/app/db/models/project.py`
- 创建：`backend/app/db/models/audit.py`
- 创建：`backend/app/db/models/__init__.py`
- 测试：`backend/tests/db/test_migrations.py`
- 测试：`backend/tests/db/test_constraints.py`

- [ ] **步骤 1：编写失败的迁移冒烟测试**

`test_migrations.py` 通过子进程依次执行迁移，并查询 `information_schema.tables`：

```python
import os
import subprocess

import psycopg

EXPECTED_TABLES = {
    ("iam", "organization"),
    ("iam", "user"),
    ("iam", "user_session"),
    ("iam", "idempotency_record"),
    ("project", "bid_project"),
    ("project", "bid_package"),
    ("project", "project_member"),
    ("audit", "audit_event"),
}


def run_alembic(*args: str) -> None:
    subprocess.run(["uv", "run", "alembic", *args], check=True, env=os.environ.copy())


def test_migration_up_down_up(test_database_dsn: str) -> None:
    run_alembic("downgrade", "base")
    run_alembic("upgrade", "head")
    with psycopg.connect(test_database_dsn) as connection:
        rows = connection.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema IN ('iam', 'project', 'audit')"
        ).fetchall()
    assert EXPECTED_TABLES <= set(rows)
    run_alembic("downgrade", "base")
    run_alembic("upgrade", "head")
```

- [ ] **步骤 2：运行迁移测试确认失败**

运行：`cd backend && uv run pytest tests/db/test_migrations.py -q`

预期：FAIL，Alembic 配置或 revision 不存在。

- [ ] **步骤 3：定义精确 ORM 字段和数据库约束**

使用 UUID 主键、UTC `TIMESTAMP WITH TIME ZONE`、JSONB 和字符串枚举检查约束。必须实现以下模型字段：

```text
iam.organization:
  id, name, organization_type, tenant_key, data_classification, created_at
  UNIQUE(tenant_key)

iam.user:
  id, organization_id, login_name, display_name, account_status, system_role,
  password_hash, must_change_password, password_changed_at, last_login_at, created_at
  UNIQUE(organization_id, login_name)

iam.user_session:
  id, user_id, token_hash, created_at, last_seen_at, idle_expires_at,
  absolute_expires_at, reauthenticated_at, revoked_at, revoke_reason,
  client_fingerprint_hash
  UNIQUE(token_hash)

iam.idempotency_record:
  id, organization_id, actor_user_id, http_method, route_template,
  idempotency_key, request_hash, processing_status, response_status,
  response_body, resource_type, resource_id, created_at, completed_at
  UNIQUE(organization_id, actor_user_id, http_method, route_template, idempotency_key)
  CHECK(processing_status IN ('PROCESSING', 'SUCCEEDED'))
  CHECK(SUCCEEDED 时 response_status/response_body/completed_at 均非空)

project.bid_project:
  id, organization_id, project_code, project_name, procurement_method,
  regime_type, project_status, deadline_at, external_ai_policy, created_at, updated_at
  UNIQUE(organization_id, project_code)
  DEFAULT project_status='DRAFT'
  DEFAULT external_ai_policy='PUBLIC_ONLY'

project.bid_package:
  id, project_id, package_code, package_name, package_status, is_v1_primary, created_at
  UNIQUE(project_id, package_code)
  部分唯一索引 UNIQUE(project_id) WHERE is_v1_primary IS TRUE

project.project_member:
  project_id, user_id, project_role, assignment_status, assigned_at
  PRIMARY KEY(project_id, user_id)

audit.audit_event:
  id, organization_id, project_id, event_type, object_type, object_id,
  before_snapshot, after_snapshot, actor_user_id, actor_type, reason,
  metadata_json, request_id, occurred_at
```

迁移还必须创建：

```sql
CREATE SEQUENCE project.project_code_seq START WITH 1;

CREATE FUNCTION audit.prevent_audit_event_mutation()
RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_event is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_event_no_update
BEFORE UPDATE OR DELETE ON audit.audit_event
FOR EACH ROW EXECUTE FUNCTION audit.prevent_audit_event_mutation();
```

`project_code` 使用序列生成 `BID-{UTC年份}-{序列至少四位补零}`，序列只负责避免并发碰撞，组织内唯一约束仍是最终门禁。

- [ ] **步骤 4：生成并人工核对初始迁移**

运行：

```bash
cd backend
uv run alembic revision --autogenerate -m "m1 foundation"
```

将生成文件改名为 `0001_m1_foundation.py`，确认 `upgrade()` 创建三个 schema、八张表、项目编号 sequence、部分唯一索引和审计只追加触发器；`downgrade()` 以相反顺序完整删除。

- [ ] **步骤 5：编写并运行约束测试**

`test_constraints.py` 至少直接插入并断言：

```python
import pytest
from sqlalchemy.exc import IntegrityError

@pytest.mark.asyncio
async def test_only_one_v1_primary_package_per_project(db_session, project_factory) -> None:
    project = await project_factory()
    db_session.add_all([
        BidPackage(project_id=project.id, package_code="PKG-01", package_name="主标包", package_status="ACTIVE", is_v1_primary=True),
        BidPackage(project_id=project.id, package_code="PKG-02", package_name="重复主标包", package_status="ACTIVE", is_v1_primary=True),
    ])
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

另覆盖：组织内登录名唯一、Session Token 哈希唯一、幂等作用域唯一、组织内项目编号唯一、项目成员唯一、审计 `organization_id` 非空、审计记录 UPDATE/DELETE 被触发器拒绝。

运行：

```bash
cd backend
uv run pytest tests/db/test_migrations.py tests/db/test_constraints.py -q
```

预期：全部 PASS。

- [ ] **步骤 6：Commit 检查点（仅在获得 Git 授权后）**

```bash
git add backend/alembic.ini backend/migrations backend/app/core/db.py backend/app/db backend/tests/db backend/tests/conftest.py
git commit -m "feat: 建立M1数据库模型与迁移"
```

---

### 任务 4：实现密码、Session Token 与会话时限纯规则

**文件：**
- 创建：`backend/app/core/security.py`
- 创建：`backend/app/auth/schemas.py`
- 创建：`backend/tests/unit/test_security.py`
- 创建：`backend/tests/unit/test_session_policy.py`

- [ ] **步骤 1：编写失败的安全原语测试**

```python
from datetime import UTC, datetime, timedelta

from app.core.security import (
    SessionDeadlines,
    build_session_deadlines,
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)


def test_password_hash_is_argon2id_and_verifiable() -> None:
    encoded = hash_password("correct-horse-battery-staple")
    assert encoded.startswith("$argon2id$")
    assert verify_password("correct-horse-battery-staple", encoded) is True
    assert verify_password("wrong-password", encoded) is False


def test_session_token_is_random_and_database_value_is_hash_only() -> None:
    first = generate_session_token()
    second = generate_session_token()
    assert first != second
    assert len(first) >= 43
    assert len(hash_session_token(first)) == 64
    assert first not in hash_session_token(first)


def test_session_deadlines_are_30_minutes_and_8_hours() -> None:
    now = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)
    deadlines = build_session_deadlines(now)
    assert deadlines == SessionDeadlines(
        idle_expires_at=now + timedelta(minutes=30),
        absolute_expires_at=now + timedelta(hours=8),
    )
```

- [ ] **步骤 2：运行测试确认失败**

运行：`cd backend && uv run pytest tests/unit/test_security.py -q`

预期：FAIL，`app.core.security` 不存在。

- [ ] **步骤 3：实现最少安全原语**

实现以下完整安全原语：

```python
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

_PASSWORD_HASHER = PasswordHasher()


@dataclass(frozen=True, slots=True)
class SessionDeadlines:
    idle_expires_at: datetime
    absolute_expires_at: datetime


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Session 时间必须包含时区")


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(encoded_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_session_deadlines(now: datetime) -> SessionDeadlines:
    _require_aware(now)
    return SessionDeadlines(
        idle_expires_at=now + timedelta(minutes=30),
        absolute_expires_at=now + timedelta(hours=8),
    )


def next_idle_expiry(now: datetime, absolute_expires_at: datetime) -> datetime:
    _require_aware(now)
    _require_aware(absolute_expires_at)
    return min(now + timedelta(minutes=30), absolute_expires_at)


def is_session_expired(
    *, now: datetime, idle_expires_at: datetime, absolute_expires_at: datetime
) -> bool:
    _require_aware(now)
    _require_aware(idle_expires_at)
    _require_aware(absolute_expires_at)
    return now >= idle_expires_at or now >= absolute_expires_at
```

实现要求：Argon2 `PasswordHasher`；Token 使用 `secrets.token_urlsafe(32)`；Token 哈希使用 SHA-256 十六进制；所有时间必须是带时区 UTC；续期后的空闲期限不得超过绝对期限。

- [ ] **步骤 4：补会话过期测试并验证**

覆盖：恰好达到空闲期限、恰好达到绝对期限、已撤销、正常续期、续期不越过绝对期限。

运行：

```bash
cd backend
uv run pytest tests/unit/test_security.py tests/unit/test_session_policy.py -q
uv run ruff check app/core/security.py tests/unit
```

预期：全部 PASS。

- [ ] **步骤 5：Commit 检查点（仅在获得 Git 授权后）**

```bash
git add backend/app/core/security.py backend/app/auth/schemas.py backend/tests/unit
git commit -m "feat: 实现服务端Session安全原语"
```

---

### 任务 5：实现 Origin、CSRF 与登录失败限流

**文件：**
- 创建：`backend/app/core/origin.py`
- 创建：`backend/app/core/csrf.py`
- 创建：`backend/app/core/rate_limit.py`
- 测试：`backend/tests/unit/test_origin_csrf.py`
- 测试：`backend/tests/unit/test_rate_limit.py`

- [ ] **步骤 1：编写失败的 Origin 与 CSRF 测试**

```python
import pytest

from app.core.csrf import assert_csrf_valid, generate_csrf_token
from app.core.errors import DomainError
from app.core.origin import assert_request_origin_allowed


def test_origin_or_referer_must_match_allowlist() -> None:
    assert_request_origin_allowed(
        origin="https://bid.example.com",
        referer=None,
        allowed_origins={"https://bid.example.com"},
    )
    with pytest.raises(DomainError, match="请求来源不受信任"):
        assert_request_origin_allowed(
            origin="https://evil.example.net",
            referer=None,
            allowed_origins={"https://bid.example.com"},
        )


def test_csrf_cookie_and_header_must_match() -> None:
    token = generate_csrf_token()
    assert_csrf_valid(cookie_token=token, header_token=token)
    with pytest.raises(DomainError, match="CSRF"):
        assert_csrf_valid(cookie_token=token, header_token="forged")
```

- [ ] **步骤 2：编写失败的限流降级测试**

```python
from datetime import UTC, datetime

from app.core.rate_limit import FallbackLoginRateLimiter, InMemoryFailureStore


class BrokenPrimaryStore:
    async def current_count(self, *, key: str, now: datetime) -> int:
        raise ConnectionError("redis unavailable")

    async def register_failure(
        self, *, key: str, now: datetime, window_seconds: int
    ) -> int:
        raise ConnectionError("redis unavailable")

    async def clear(self, *, key: str) -> None:
        raise ConnectionError("redis unavailable")


async def test_redis_failure_degrades_to_local_conservative_limit() -> None:
    limiter = FallbackLoginRateLimiter(
        primary=BrokenPrimaryStore(),
        fallback=InMemoryFailureStore(),
        failure_limit=2,
        window_seconds=900,
    )
    now = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)
    assert await limiter.record_failure(login_name="demo", source="127.0.0.1", now=now) is False
    assert await limiter.record_failure(login_name="demo", source="127.0.0.1", now=now) is True
```

- [ ] **步骤 3：运行测试确认失败**

运行：`cd backend && uv run pytest tests/unit/test_origin_csrf.py tests/unit/test_rate_limit.py -q`

预期：FAIL，三个模块尚不存在。

- [ ] **步骤 4：实现安全规则**

实现要求：

```text
assert_request_origin_allowed(origin, referer, allowed_origins):
  Origin 非空时只判断 Origin；否则从 Referer 提取 scheme://host[:port]；两者都缺失或不在白名单时抛 ORIGIN_NOT_ALLOWED。

assert_csrf_valid(cookie_token, header_token):
  任一缺失或 secrets.compare_digest 不匹配时抛 403 CSRF_VALIDATION_FAILED。

FallbackLoginRateLimiter:
  键 = SHA-256(normalized_login_name + "\0" + source)，不得在 Redis 键或日志保存原始账号；
  优先 Redis INCR + 首次 EXPIRE；Redis 异常时使用带锁的进程内窗口计数；
  达到第 5 次失败即返回受限；成功登录清理该组合计数；
  限流不修改 iam.user.account_status。
```

实现类的方法签名固定如下，并按上面的 Redis/进程内规则填写函数体；这里给出编排层的完整逻辑，存储实现分别封装 Redis 原子递增和带锁的本地窗口：

```python
import hashlib
from datetime import datetime
from typing import Protocol


class FailureStore(Protocol):
    async def current_count(self, *, key: str, now: datetime) -> int:
        raise NotImplementedError

    async def register_failure(
        self, *, key: str, now: datetime, window_seconds: int
    ) -> int:
        raise NotImplementedError

    async def clear(self, *, key: str) -> None:
        raise NotImplementedError


class FallbackLoginRateLimiter:
    def __init__(
        self,
        *,
        primary: FailureStore | None,
        fallback: FailureStore,
        failure_limit: int,
        window_seconds: int,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._failure_limit = failure_limit
        self._window_seconds = window_seconds

    def _key(self, login_name: str, source: str) -> str:
        normalized = login_name.strip().casefold()
        material = f"{normalized}\0{source}".encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    async def is_limited(self, *, login_name: str, source: str, now: datetime) -> bool:
        key = self._key(login_name, source)
        store = self._primary or self._fallback
        try:
            count = await store.current_count(key=key, now=now)
        except ConnectionError:
            count = await self._fallback.current_count(key=key, now=now)
        return count >= self._failure_limit

    async def record_failure(self, *, login_name: str, source: str, now: datetime) -> bool:
        key = self._key(login_name, source)
        store = self._primary or self._fallback
        try:
            count = await store.register_failure(
                key=key, now=now, window_seconds=self._window_seconds
            )
        except ConnectionError:
            count = await self._fallback.register_failure(
                key=key, now=now, window_seconds=self._window_seconds
            )
        return count >= self._failure_limit

    async def clear_after_success(self, *, login_name: str, source: str) -> None:
        key = self._key(login_name, source)
        if self._primary is not None:
            try:
                await self._primary.clear(key=key)
            except ConnectionError:
                pass
        await self._fallback.clear(key=key)
```

- [ ] **步骤 5：验证规则通过**

运行：

```bash
cd backend
uv run pytest tests/unit/test_origin_csrf.py tests/unit/test_rate_limit.py -q
uv run mypy app/core/origin.py app/core/csrf.py app/core/rate_limit.py
```

预期：全部 PASS，mypy 退出码 0。

- [ ] **步骤 6：Commit 检查点（仅在获得 Git 授权后）**

```bash
git add backend/app/core/origin.py backend/app/core/csrf.py backend/app/core/rate_limit.py backend/tests/unit/test_origin_csrf.py backend/tests/unit/test_rate_limit.py
git commit -m "feat: 增加登录来源与CSRF防护"
```

---

### 任务 6：实现登录与 Session 查询

**文件：**
- 创建：`backend/app/audit/service.py`
- 创建：`backend/app/auth/repository.py`
- 创建：`backend/app/auth/service.py`
- 创建：`backend/app/auth/dependencies.py`
- 创建：`backend/app/auth/api.py`
- 创建：`backend/app/api/router.py`
- 修改：`backend/app/main.py`
- 修改：`backend/tests/conftest.py`
- 创建：`backend/tests/factories.py`
- 测试：`backend/tests/integration/test_auth_login.py`

- [ ] **步骤 1：编写失败的登录成功测试**

```python
async def test_login_creates_hashed_server_session_and_safe_cookies(
    client, db_session, active_bid_manager
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"login_name": active_bid_manager.login_name, "password": "ValidPass123!"},
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == str(active_bid_manager.id)
    assert body["user"]["system_role"] == "BID_MANAGER"
    assert body["must_change_password"] is False
    session_cookie = response.cookies["bid_session"]
    assert session_cookie
    session = await db_session.scalar(select(UserSession).where(UserSession.user_id == active_bid_manager.id))
    assert session is not None
    assert session.token_hash == hash_session_token(session_cookie)
    assert session_cookie not in session.token_hash
    assert "HttpOnly" in response.headers.get_list("set-cookie")[0]
    assert response.cookies["bid_csrf"]
```

- [ ] **步骤 2：编写失败的匿名与错误凭据测试**

同一测试文件加入：不存在账号和错误密码都返回完全相同的 `401 INVALID_CREDENTIALS`；禁用账号也不泄露账号状态；非法 Origin 返回 `403 ORIGIN_NOT_ALLOWED`；达到失败阈值返回 `429 LOGIN_RATE_LIMITED`；数据库审计记录登录成功/失败，但 `metadata_json` 不含密码、Session Token 或 Cookie。

- [ ] **步骤 3：运行测试确认失败**

运行：`cd backend && uv run pytest tests/integration/test_auth_login.py -q`

预期：FAIL，路由返回 404。

- [ ] **步骤 4：实现登录服务与接口**

Pydantic 契约固定为：

```python
class LoginRequest(BaseModel):
    login_name: str = Field(min_length=1, max_length=128)
    password: SecretStr

class UserView(BaseModel):
    id: UUID
    organization_id: UUID
    login_name: str
    display_name: str
    system_role: str

class SessionResponse(BaseModel):
    user: UserView
    idle_expires_at: datetime
    absolute_expires_at: datetime
    must_change_password: bool
    allowed_actions: list[str]
```

登录顺序必须固定：来源校验 → 限流预检查 → 组织内单账号查询（V1 单组织）→ 恒定风格密码校验 → 账号状态校验 → 创建 Session → 更新 `last_login_at` → 追加审计 → 同事务提交 → 设置 Cookie。账号不存在时也验证一个应用启动时生成的 dummy Argon2id 哈希，减少账号枚举时序差异。

Cookie 规则：

```text
bid_session: HttpOnly=true, Secure=配置值, SameSite=Lax, Path=/, Max-Age=28800
bid_csrf:    HttpOnly=false, Secure=配置值, SameSite=Lax, Path=/, Max-Age=28800
```

Session 原文不得写入日志、数据库、错误详情或审计。登录失败审计无法关联真实用户时 `actor_user_id=NULL`，只保存登录名 SHA-256 摘要。

- [ ] **步骤 5：实现 Session 查询与活动续期**

`GET /api/v1/auth/session`：缺 Cookie 返回 `401 UNAUTHENTICATED`；Token 哈希找不到返回同错误；撤销或过期返回 `401 SESSION_EXPIRED`；有效访问更新 `last_seen_at` 和 `idle_expires_at=min(now+30分钟, absolute_expires_at)`；账号已禁用时撤销 Session 并拒绝。`allowed_actions` 在首次改密时只能是 `SESSION_READ`、`LOGOUT`、`PASSWORD_CHANGE`。

- [ ] **步骤 6：运行认证集成测试**

运行：

```bash
cd backend
uv run pytest tests/integration/test_auth_login.py -q
uv run pytest tests/unit tests/integration/test_auth_login.py -q
```

预期：全部 PASS。

- [ ] **步骤 7：Commit 检查点（仅在获得 Git 授权后）**

```bash
git add backend/app/audit backend/app/auth backend/app/api backend/app/main.py backend/tests/factories.py backend/tests/conftest.py backend/tests/integration/test_auth_login.py
git commit -m "feat: 实现登录与服务端Session查询"
```

---

### 任务 7：实现退出、改密和首次改密门禁

**文件：**
- 修改：`backend/app/auth/schemas.py`
- 修改：`backend/app/auth/service.py`
- 修改：`backend/app/auth/dependencies.py`
- 修改：`backend/app/auth/api.py`
- 测试：`backend/tests/integration/test_auth_session_logout.py`
- 测试：`backend/tests/integration/test_password_change.py`
- 测试：`backend/tests/integration/test_password_change_gate.py`

- [ ] **步骤 1：编写失败的退出测试**

```python
async def test_logout_revokes_current_session_and_clears_cookies(authenticated_client, db_session) -> None:
    response = await authenticated_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://testserver", "X-CSRF-Token": authenticated_client.cookies["bid_csrf"]},
    )
    assert response.status_code == 204
    session = await db_session.scalar(select(UserSession))
    assert session is not None
    assert session.revoked_at is not None
    assert session.revoke_reason == "LOGOUT"
    assert authenticated_client.cookies.get("bid_session") is None
```

另加：缺失/错误 CSRF 返回 `CSRF_VALIDATION_FAILED`；重复退出不产生 500；审计写 `LOGOUT`。

- [ ] **步骤 2：编写失败的改密测试**

改密请求契约：

```python
class PasswordChangeRequest(BaseModel):
    current_password: SecretStr
    new_password: SecretStr
```

测试固定行为：当前密码错误返回 `INVALID_CREDENTIALS`；新密码规则采用本计划的安全实现基线——至少 12 个字符、至少包含字母和数字、不得等于当前密码；成功后更新 Argon2id 哈希、`password_changed_at`、`must_change_password=false`；保留当前 Session，撤销其他有效 Session，原因 `PASSWORD_CHANGED`；追加 `PASSWORD_CHANGED` 与对应 `SESSION_REVOKED` 审计。该密码规则尚未在正式规格中单独冻结，若计划未获批准不得自行写入产品事实。

- [ ] **步骤 3：编写首次改密门禁测试**

使用 `must_change_password=true` 的账号登录后：

```text
GET  /api/v1/auth/session             -> 200
POST /api/v1/auth/logout              -> 204
POST /api/v1/auth/password/change     -> 204
GET  /api/v1/me/workbench             -> 403 PASSWORD_CHANGE_REQUIRED
GET  /api/v1/projects                 -> 403 PASSWORD_CHANGE_REQUIRED
POST /api/v1/projects                 -> 403 PASSWORD_CHANGE_REQUIRED
```

改密成功后，同一当前 Session 再访问工作台不再返回 `PASSWORD_CHANGE_REQUIRED`。

- [ ] **步骤 4：运行测试确认失败**

运行：

```bash
cd backend
uv run pytest tests/integration/test_auth_session_logout.py tests/integration/test_password_change.py tests/integration/test_password_change_gate.py -q
```

预期：FAIL，退出/改密接口或业务门禁尚未实现。

- [ ] **步骤 5：实现最少逻辑并验证**

所有写接口先校验 Origin/Referer，再校验当前 Session 与 CSRF。改密在单事务中完成用户更新、其他 Session 撤销和审计；当前 Session 不撤销。退出清理 Cookie 时保持与登录相同的 Path/SameSite/Secure 配置。

运行：

```bash
cd backend
uv run pytest tests/integration/test_auth_session_logout.py tests/integration/test_password_change.py tests/integration/test_password_change_gate.py -q
uv run ruff check app/auth tests/integration
```

预期：全部 PASS。

- [ ] **步骤 6：Commit 检查点（仅在获得 Git 授权后）**

```bash
git add backend/app/auth backend/tests/integration/test_auth_session_logout.py backend/tests/integration/test_password_change.py backend/tests/integration/test_password_change_gate.py
git commit -m "feat: 实现退出改密与首次改密门禁"
```

---

### 任务 8：定义项目契约与负责人权限规则

**文件：**
- 创建：`backend/app/projects/schemas.py`
- 创建：`backend/app/projects/repository.py`
- 创建：`backend/tests/unit/test_project_policy.py`

- [ ] **步骤 1：编写失败的请求契约测试**

```python
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.projects.schemas import CreateProjectRequest


def test_create_project_accepts_only_first_slice_fields() -> None:
    command = CreateProjectRequest(
        project_name="政务云平台运维服务采购项目",
        procurement_method="PUBLIC_TENDER",
        regime_type="GOVERNMENT_PROCUREMENT",
        deadline_at=datetime(2026, 9, 15, 17, 0, tzinfo=UTC),
        owner_user_id=uuid4(),
    )
    assert command.project_name.startswith("政务云")


def test_source_fields_are_rejected_in_first_slice() -> None:
    with pytest.raises(ValidationError):
        CreateProjectRequest.model_validate({
            "project_name": "项目",
            "procurement_method": "PUBLIC_TENDER",
            "regime_type": "GOVERNMENT_PROCUREMENT",
            "deadline_at": "2026-09-15T17:00:00+08:00",
            "owner_user_id": str(uuid4()),
            "project_source": "政府采购网",
        })
```

- [ ] **步骤 2：编写失败的负责人规则测试**

测试服务函数 `assert_owner_eligible(actor, owner)`：负责人不存在/禁用/角色不是 `BID_MANAGER` 返回 `OWNER_ROLE_MISMATCH`；跨组织返回 `OWNER_ORGANIZATION_MISMATCH`；创建人平台角色不是 `BID_MANAGER` 返回 `FORBIDDEN`。

- [ ] **步骤 3：运行测试确认失败**

运行：`cd backend && uv run pytest tests/unit/test_project_policy.py -q`

预期：FAIL，项目 schema 与规则函数不存在。

- [ ] **步骤 4：实现项目契约与规则**

`CreateProjectRequest` 使用 `extra="forbid"`，五个字段全部必填；`deadline_at` 必须带时区。采购方式只允许正式数据字典中的 7 个值，制度只允许 `GOVERNMENT_PROCUREMENT` 或 `TENDER_BIDDING`。

响应契约至少包含：

```python
class ProjectCreatedResponse(BaseModel):
    id: UUID
    project_code: str
    project_name: str
    project_status: Literal["DRAFT"]
    owner_user_id: UUID
    package_id: UUID
    created_at: datetime
```

- [ ] **步骤 5：验证通过**

运行：

```bash
cd backend
uv run pytest tests/unit/test_project_policy.py -q
uv run mypy app/projects/schemas.py app/projects/repository.py
```

预期：全部 PASS。

- [ ] **步骤 6：Commit 检查点（仅在获得 Git 授权后）**

```bash
git add backend/app/projects/schemas.py backend/app/projects/repository.py backend/tests/unit/test_project_policy.py
git commit -m "feat: 定义项目创建契约与负责人规则"
```

---

### 任务 9：实现 PostgreSQL 幂等占位与项目创建事务

**文件：**
- 创建：`backend/app/projects/idempotency.py`
- 创建：`backend/app/projects/service.py`
- 创建：`backend/app/projects/api.py`
- 修改：`backend/app/api/router.py`
- 测试：`backend/tests/integration/test_project_create.py`
- 测试：`backend/tests/integration/test_project_idempotency.py`

- [ ] **步骤 1：编写失败的创建成功测试**

```python
async def test_create_project_commits_all_business_facts(
    bid_manager_client, db_session, eligible_owner
) -> None:
    payload = {
        "project_name": "政务云平台运维服务采购项目",
        "procurement_method": "PUBLIC_TENDER",
        "regime_type": "GOVERNMENT_PROCUREMENT",
        "deadline_at": "2026-09-15T17:00:00+08:00",
        "owner_user_id": str(eligible_owner.id),
    }
    response = await bid_manager_client.post(
        "/api/v1/projects",
        json=payload,
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": bid_manager_client.cookies["bid_csrf"],
            "Idempotency-Key": "create-project-001",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["project_status"] == "DRAFT"
    assert body["owner_user_id"] == str(eligible_owner.id)
    assert await count_rows(db_session, BidProject) == 1
    assert await count_rows(db_session, BidPackage) == 1
    assert await count_rows(db_session, ProjectMember) == 1
    assert await count_rows(db_session, IdempotencyRecord) == 1
    assert await count_project_created_audits(db_session) == 1
```

再断言：主标包 `PKG-01`、`ACTIVE`、`is_v1_primary=true`；成员只属于 `owner_user_id`、职责 `BID_MANAGER`；创建人若不是负责人，不自动获得成员关系。

- [ ] **步骤 2：编写失败的幂等测试**

覆盖三条精确行为：

```text
缺少 Idempotency-Key              -> 400 IDEMPOTENCY_KEY_REQUIRED
同作用域同键同请求第二次提交       -> 返回首次 201 与完全相同响应体，所有业务表计数不增加
同作用域同键不同请求体             -> 409 IDEMPOTENCY_CONFLICT
```

- [ ] **步骤 3：运行测试确认失败**

运行：

```bash
cd backend
uv run pytest tests/integration/test_project_create.py tests/integration/test_project_idempotency.py -q
```

预期：FAIL，创建路由返回 404。

- [ ] **步骤 4：实现规范化请求哈希与并发安全占位**

公开类型固定为：

```python
@dataclass(frozen=True, slots=True)
class IdempotencyScope:
    organization_id: UUID
    actor_user_id: UUID
    http_method: str
    route_template: str
    idempotency_key: str

@dataclass(frozen=True, slots=True)
class IdempotencyReplay:
    response_status: int
    response_body: dict[str, object]
```

请求哈希对 `CreateProjectRequest.model_dump(mode="json")` 使用 `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` 后做 SHA-256。占位算法必须在外层业务事务中：

```text
1. 在 savepoint 中 INSERT processing_status='PROCESSING' 并 flush。
2. INSERT 成功者拥有执行权。
3. 唯一冲突者回滚 savepoint，再 SELECT 同作用域记录 FOR UPDATE。
4. request_hash 不同 -> IDEMPOTENCY_CONFLICT。
5. processing_status='SUCCEEDED' -> 重放 response_status/response_body。
6. 首事务失败时占位随外层事务回滚，不留下可重放结果，同键可重新 INSERT。
```

不得把 Redis 或进程内锁用于项目业务幂等。

- [ ] **步骤 5：实现项目创建单事务**

顺序固定为：Session/首次改密/创建人角色 → 幂等占位/重放 → 负责人校验 → `nextval('project.project_code_seq')` → 项目 → 主标包 → 负责人成员 → `PROJECT_CREATED` 审计 → 幂等记录改 `SUCCEEDED` 并保存 `201` 与响应体 → 单次 commit。

任何数据库唯一冲突不得暴露 SQL；项目编号唯一冲突映射 `PROJECT_CODE_CONFLICT`。响应体保存 JSON 可序列化值，不保存 Cookie、Token 或请求头。

- [ ] **步骤 6：验证创建和重放**

运行：

```bash
cd backend
uv run pytest tests/integration/test_project_create.py tests/integration/test_project_idempotency.py -q
uv run ruff check app/projects tests/integration/test_project_create.py tests/integration/test_project_idempotency.py
```

预期：全部 PASS。

- [ ] **步骤 7：Commit 检查点（仅在获得 Git 授权后）**

```bash
git add backend/app/projects backend/app/api/router.py backend/tests/integration/test_project_create.py backend/tests/integration/test_project_idempotency.py
git commit -m "feat: 实现幂等项目创建事务"
```

---

### 任务 10：证明并发幂等和失败回滚

**文件：**
- 创建：`backend/tests/integration/test_project_idempotency_concurrency.py`
- 创建：`backend/tests/integration/test_project_transaction_rollback.py`
- 修改：`backend/app/projects/service.py`
- 修改：`backend/app/projects/idempotency.py`

- [ ] **步骤 1：编写真实多连接并发测试**

使用两个独立 HTTPX client、两个独立连接和 `anyio.create_task_group()` 同时提交同一用户、同一键、同一请求。用 `anyio.Event` 测试钩子让首请求在占位 flush 后暂停，第二请求开始后再释放，不使用任意 `sleep()` 猜测时序。

精确断言：两个响应均为 201；JSON 完全相同；`bid_project`、`bid_package`、`project_member`、`idempotency_record` 和 `PROJECT_CREATED` 审计各只增加一条。

- [ ] **步骤 2：编写同键不同请求并发测试**

两个请求共享键但 `project_name` 不同；断言一个 201、一个 `409 IDEMPOTENCY_CONFLICT`，且只产生一个项目。不得接受两个 201 或两个项目。

- [ ] **步骤 3：编写四个事务故障注入测试**

通过测试专用 `ProjectCreationHooks` 协议注入异常，生产默认实现为空操作：

```python
class NoOpProjectCreationHooks:
    async def after_project(self) -> None:
        return None

    async def after_package(self) -> None:
        return None

    async def after_member(self) -> None:
        return None

    async def after_audit(self) -> None:
        return None
```

测试使用实现相同四个方法的 `FailAtHook`，构造时接收 `fail_at: Literal["project", "package", "member", "audit"]`，只在对应方法抛 `InjectedFailure`；生产服务默认注入 `NoOpProjectCreationHooks`。

分别在项目、主标包、成员、审计写入后抛 `InjectedFailure`。每例断言五类业务事实都未提交，幂等记录不存在或不处于 `SUCCEEDED`；然后使用同一 `Idempotency-Key` 再次请求必须成功且只创建一次。

- [ ] **步骤 4：运行测试确认至少一个失败**

运行：

```bash
cd backend
uv run pytest tests/integration/test_project_idempotency_concurrency.py tests/integration/test_project_transaction_rollback.py -q
```

预期：在并发协调或故障钩子接入前 FAIL；不得通过扩大超时掩盖竞态。

- [ ] **步骤 5：修正事务边界并验证**

确保 `AsyncSession.begin()` 只包围一次完整项目创建，API 层不进行第二次 commit；唯一冲突在 savepoint 内处理；审计和幂等成功回写与业务对象共享同一 Session。

运行：

```bash
cd backend
uv run pytest tests/integration/test_project_idempotency_concurrency.py tests/integration/test_project_transaction_rollback.py -q
uv run pytest tests/integration/test_project_create.py tests/integration/test_project_idempotency.py -q
```

预期：全部 PASS，且无死锁或超时。

- [ ] **步骤 6：Commit 检查点（仅在获得 Git 授权后）**

```bash
git add backend/app/projects backend/tests/integration/test_project_idempotency_concurrency.py backend/tests/integration/test_project_transaction_rollback.py
git commit -m "test: 验证项目并发幂等与事务回滚"
```

---

### 任务 11：实现项目列表与项目总览

**文件：**
- 创建：`backend/app/projects/queries.py`
- 修改：`backend/app/projects/schemas.py`
- 修改：`backend/app/projects/api.py`
- 测试：`backend/tests/integration/test_project_queries.py`

- [ ] **步骤 1：编写失败的列表权限测试**

准备同组织成员项目、同组织非成员项目、跨组织项目。当前用户的列表只能出现存在 `assignment_status='ACTIVE'` 成员关系的项目；不得仅按 `organization_id` 暴露整个组织项目。

分页契约固定为：

```python
class ProjectListItem(BaseModel):
    id: UUID
    project_code: str
    project_name: str
    procurement_method: str
    regime_type: str
    project_status: str
    deadline_at: datetime | None
    owner_user_id: UUID
    owner_display_name: str
    updated_at: datetime


class ProjectListResponse(BaseModel):
    items: list[ProjectListItem]
    page: int
    page_size: int
    total: int
```

查询参数固定为 `page`、`page_size`、`keyword`、`status`、`owner_user_id`、`only_my_projects`、`sort`；默认 `page=1`、`page_size=20`、`sort=-created_at`，最大页大小 100。

- [ ] **步骤 2：编写失败的总览权限与空动态集合测试**

成员访问返回项目基础信息、负责人摘要、`stage_progress`、`current_action`、`allowed_actions`；非成员即使知道 UUID 也返回 `403 FORBIDDEN`。第一切片尚无运行对象，因此必须返回：

```json
{
  "blocking_items": [],
  "member_tasks": [],
  "recent_changes": [],
  "running_tasks": []
}
```

不得根据 Mock 数据伪造 Agent、任务或人工关口状态。

- [ ] **步骤 3：运行测试确认失败**

运行：`cd backend && uv run pytest tests/integration/test_project_queries.py -q`

预期：FAIL，查询路由或 schema 尚未实现。

- [ ] **步骤 4：实现只读聚合查询**

列表从 `project_member` 主动关系出发连接 `bid_project` 和负责人成员；总览先用当前用户成员关系做权限查询，再聚合项目、主标包和负责人。`DRAFT` 项目的最小稳定值：

```text
stage_progress = {"stage": "PROJECT_SETUP", "status": "NOT_STARTED", "percent": 0}
current_action = {"code": "COMPLETE_PROJECT_SETUP", "label": "完善项目基础信息"}
allowed_actions = ["PROJECT_READ"]，如果当前用户同时是负责人则追加 "PROJECT_UPDATE"
```

- [ ] **步骤 5：验证查询行为**

运行：

```bash
cd backend
uv run pytest tests/integration/test_project_queries.py -q
uv run mypy app/projects/queries.py app/projects/schemas.py
```

预期：全部 PASS。

- [ ] **步骤 6：Commit 检查点（仅在获得 Git 授权后）**

```bash
git add backend/app/projects/queries.py backend/app/projects/schemas.py backend/app/projects/api.py backend/tests/integration/test_project_queries.py
git commit -m "feat: 实现项目列表与总览查询"
```

---

### 任务 12：实现个人工作台最小真实聚合

**文件：**
- 修改：`backend/app/projects/queries.py`
- 修改：`backend/app/projects/schemas.py`
- 修改：`backend/app/projects/api.py`
- 测试：`backend/tests/integration/test_workbench.py`

- [ ] **步骤 1：编写失败的工作台测试**

当前用户工作台只使用真实项目成员数据：最近项目按 `updated_at DESC` 最多 5 个；第一切片未实现的个人待办、运行任务和失败摘要返回空数组；跨组织或非成员项目不得出现。

响应契约固定为：

```python
class WorkbenchTodo(BaseModel):
    project_id: UUID
    code: str
    label: str
    deadline_at: datetime | None


class WorkbenchTask(BaseModel):
    task_run_id: UUID
    state: str
    stage: str
    progress: int
    failed_reason: str | None


class WorkbenchResponse(BaseModel):
    personal_todos: list[WorkbenchTodo]
    recent_projects: list[ProjectListItem]
    running_tasks: list[WorkbenchTask]
    failed_tasks: list[WorkbenchTask]
```

第一切片查询只填充 `recent_projects`；另外三个字段返回类型化空列表，因此不会制造不存在的 todo 或 task_run。

- [ ] **步骤 2：运行测试确认失败**

运行：`cd backend && uv run pytest tests/integration/test_workbench.py -q`

预期：FAIL，工作台路由返回 404 或 schema 不匹配。

- [ ] **步骤 3：实现工作台查询与接口**

`GET /api/v1/me/workbench` 使用业务访问依赖，因此首次改密门禁生效；空动态集合必须由空查询结果产生，不读取 `frontend/js/data.js`，不写假任务。

- [ ] **步骤 4：验证工作台和门禁**

运行：

```bash
cd backend
uv run pytest tests/integration/test_workbench.py tests/integration/test_password_change_gate.py -q
```

预期：全部 PASS。

- [ ] **步骤 5：Commit 检查点（仅在获得 Git 授权后）**

```bash
git add backend/app/projects/queries.py backend/app/projects/schemas.py backend/app/projects/api.py backend/tests/integration/test_workbench.py
git commit -m "feat: 实现个人工作台真实聚合"
```

---

### 任务 13：锁定 OpenAPI、错误映射与安全回归

**文件：**
- 修改：`backend/tests/contract/test_openapi.py`
- 修改：`backend/tests/contract/test_error_contract.py`
- 修改：`backend/app/core/errors.py`
- 修改：`backend/app/main.py`

- [ ] **步骤 1：编写失败的 OpenAPI 路由测试**

```python
EXPECTED_OPERATIONS = {
    ("post", "/api/v1/auth/login"),
    ("get", "/api/v1/auth/session"),
    ("post", "/api/v1/auth/logout"),
    ("post", "/api/v1/auth/password/change"),
    ("get", "/api/v1/me/workbench"),
    ("get", "/api/v1/projects"),
    ("post", "/api/v1/projects"),
    ("get", "/api/v1/projects/{project_id}/overview"),
}


def test_openapi_contains_exact_first_slice_operations(client) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    actual = {(method, path) for path, methods in paths.items() for method in methods}
    assert EXPECTED_OPERATIONS <= actual
```

并断言 `CreateProjectRequest` schema 不包含 `project_source` 或 `external_project_code`，错误 schema 必含四字段。

- [ ] **步骤 2：添加安全错误映射参数化测试**

逐一触发并断言：`INVALID_CREDENTIALS`、`UNAUTHENTICATED`、`FORBIDDEN`、`VALIDATION_ERROR`、`PROJECT_CODE_CONFLICT`、`OWNER_ROLE_MISMATCH`、`OWNER_ORGANIZATION_MISMATCH`、`PASSWORD_CHANGE_REQUIRED`、`LOGIN_RATE_LIMITED`、`ORIGIN_NOT_ALLOWED`、`IDEMPOTENCY_KEY_REQUIRED`、`IDEMPOTENCY_CONFLICT`、`SESSION_EXPIRED`、`CSRF_VALIDATION_FAILED`、`INTERNAL_ERROR`。每个错误必须含 `code/message/request_id/details`，响应头 request ID 与错误体一致。

- [ ] **步骤 3：运行契约测试并修正遗漏**

运行：

```bash
cd backend
uv run pytest tests/contract -q
```

预期：第一次若有契约遗漏则 FAIL；只修正路由/schema/错误映射，不改变正式业务语义。

- [ ] **步骤 4：运行认证和项目安全回归**

运行：

```bash
cd backend
uv run pytest tests/unit tests/db tests/integration tests/contract -q
```

预期：全部 PASS。

- [ ] **步骤 5：Commit 检查点（仅在获得 Git 授权后）**

```bash
git add backend/app backend/tests/contract
git commit -m "test: 锁定M1接口与错误契约"
```

---

### 任务 14：完成质量门禁、文档同步与历史记录

**文件：**
- 修改：`backend/README.md`
- 修改：`specs/13-项目决策与工作记录.md`（仅记录实施中经用户确认的新决策；没有新决策则不改）
- 修改：`项目开发对话历史.md`
- 检查：`docs/development/2026-08-21-M1认证与项目纵向切片设计.md`
- 检查：`specs/10-核心业务对象与数据字典.md`
- 检查：`specs/14-API接口设计.md`
- 检查：`specs/15-评估体系与测试计划.md`
- 检查：`specs/18-数据库设计与实现方案.md`

- [ ] **步骤 1：补本地运行与测试说明**

`backend/README.md` 必须写明：Python 3.12、`uv sync --dev`、测试 PostgreSQL 启停命令、`DATABASE_URL`/`APP_ENV=test`、迁移命令、启动命令、完整验证命令，以及“测试环境数据库名必须包含 `_test`”。不得写真实密码、生产地址或外部 API Key。

- [ ] **步骤 2：运行格式化与静态检查**

运行：

```bash
cd backend
uv run ruff format app tests migrations
uv run ruff check app tests migrations
uv run mypy app
```

预期：Ruff 与 mypy 全部退出码 0。

- [ ] **步骤 3：从空库执行迁移往返**

运行：

```bash
cd backend
uv run alembic downgrade base
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
```

预期：四条命令全部退出码 0。

- [ ] **步骤 4：运行完整第一切片测试**

运行：

```bash
cd backend
uv run pytest -q
```

预期：全部测试 PASS；报告真实测试数和耗时。局部通过不得表述为完整 M1、L1 或 L2 通过。

- [ ] **步骤 5：执行文档与 Git 差异检查**

运行：

```bash
git diff --check
git diff --stat
git status --short
git diff -- backend specs/13-项目决策与工作记录.md 项目开发对话历史.md
```

预期：`git diff --check` 退出码 0；确认没有修改 `frontend/`、没有敏感信息、没有超出第一切片的依赖或模块。

- [ ] **步骤 6：追加对话历史**

只有完整验证完成后，按项目固定模板向 `项目开发对话历史.md` 追加：来源、记录日期、任务主题、用户要求、完成工作、修改文件、验证命令与真实结果、未解决问题与后续事项。不得改写历史记录。

如果实施过程中确认了 Python 版本、安全参数或其他会影响后续成员的正式决策，在用户确认后追加 `specs/13-项目决策与工作记录.md`；否则不要把实现细节擅自升级为正式决策。

- [ ] **步骤 7：最终 Commit 检查点（仅在获得 Git 授权后）**

```bash
git add backend 项目开发对话历史.md
git add specs/13-项目决策与工作记录.md  # 仅当该文件确有经确认的新决策
git commit -m "feat: 完成M1认证与项目第一纵向切片"
```

---

## 2. 规格覆盖自检

| 已批准要求 | 计划任务 |
|---|---|
| PostgreSQL 服务端 Session，不使用 JWT | 3、4、6 |
| Argon2id、Token 原文只在 Cookie | 4、6 |
| 空闲 30 分钟、绝对 8 小时 | 4、6 |
| Cookie HttpOnly/Secure/SameSite=Lax | 6 |
| CSRF Cookie + X-CSRF-Token | 5、7 |
| Origin/Referer 与登录限流、Redis 降级 | 5、6 |
| 首次改密只放行三个认证动作 | 7 |
| 改密撤销其他 Session | 7 |
| 工作台、列表、创建、总览 | 9、11、12 |
| 创建请求只含五个字段 | 8、13 |
| 负责人同组织、有效、角色兼容 | 8、9 |
| 创建人不自动获得项目访问权 | 9 |
| 项目、主标包、成员、审计同事务 | 9、10 |
| 强制 Idempotency-Key | 9 |
| 同键重放、异体冲突、并发互斥 | 9、10 |
| 失败事务同键可重试 | 10 |
| 组织与项目成员权限隔离 | 8、11、12 |
| 审计组织必填、项目/操作者可空 | 3、6、9 |
| 审计只追加且不含敏感原文 | 3、6 |
| 统一错误体和 request_id | 2、13 |
| 真实 PostgreSQL 约束与迁移测试 | 1、3、10、14 |
| 不修改冻结前端 | 全计划硬边界、14 |
| 不建设 Celery/Agent/MCP/MinIO | 1 与全计划硬边界 |

## 3. 计划执行纪律

1. 每个任务开始前只读取该任务列出的文件和直接依赖，不无差别读取全部规格。
2. 每条行为严格执行红—绿—重构：先写失败测试并记录预期失败，再写最少实现，再运行同一测试确认通过。
3. 遇到测试失败先使用 `systematic-debugging`，不得删除权限、版本、幂等、审计或安全校验换取通过。
4. 每完成一个任务，运行该任务的聚焦测试；任务 13、14 才运行完整第一切片套件。
5. 实现完成后使用 `requesting-code-review`，再使用 `verification-before-completion`。
6. 未经用户明确授权，不执行任何 `git add`、`git commit`、`git push` 或分支操作。
