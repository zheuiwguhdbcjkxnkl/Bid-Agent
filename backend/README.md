# bid-agent-ai 后端（M1 第一纵向切片）

使用 `FastAPI` + `SQLAlchemy 2.x` + `Alembic` + `PostgreSQL` + `pytest` + `Ruff` + `mypy`。

## 环境要求

- Python 3.12（`>=3.12,<3.13`）
- `uv`（依赖管理）
- Docker Desktop（测试 PostgreSQL）

## 安装依赖

```bash
uv sync --dev
```

## 启动测试数据库

```bash
docker compose -f compose.test.yaml up -d --wait
```

测试库连接串：`postgresql+psycopg://bid_agent:bid_agent_test@localhost:55432/bid_agent_test`。

停止测试库：

```bash
docker compose -f compose.test.yaml down
```

## 环境变量

复制 `.env.example` 到 `.env` 并按需修改。关键变量：

| 变量 | 说明 | 测试值 |
|---|---|---|
| `APP_ENV` | 运行环境 | `test`（跑测试必须） |
| `DATABASE_URL` | PostgreSQL 连接串 | 见上 |
| `ALLOWED_ORIGINS` | 允许的 Origin 白名单 | `http://frontend.localhost` |
| `SESSION_COOKIE_SECURE` | 会话 Cookie Secure | `false`（本地测试） |

> 安全约束：当 `APP_ENV=test` 时，`DATABASE_URL` 的数据库名必须包含 `_test`，否则应用启动即报错，防止测试误连开发或生产库。

## 数据库迁移

```bash
uv run alembic upgrade head
uv run alembic downgrade base
```

## 启动应用

```bash
uv run uvicorn app.main:create_app --factory --reload
```

健康检查：`GET /health`。

## 完整验证命令

```bash
uv run pytest -q
uv run ruff check app tests
uv run ruff format --check app tests migrations
uv run mypy app tests
```

## 迁移往返检查

```bash
uv run alembic downgrade base
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
```

## 注意事项

- 不向本文件或代码提交任何真实密码、生产地址或外部 API Key。
- 测试库凭据仅用于本地测试，生产凭据通过环境变量注入。
