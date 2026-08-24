from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.api import api_router
from app.core import RequestIdMiddleware, Settings, get_settings, install_exception_handlers
from app.core.db import create_engine, create_session_factory
from app.core.rate_limit import FallbackLoginRateLimiter, InMemoryFailureStore
from app.projects.documents.storage import ObjectStorage, UnconfiguredObjectStorage
from app.projects.schemas import CreateProjectRequest
from app.projects.service import NoOpProjectCreationHooks, ProjectCreationHooks


def _default_now_provider() -> datetime:
    return datetime.now(UTC)


def _build_default_limiter(settings: Settings) -> FallbackLoginRateLimiter:
    return FallbackLoginRateLimiter(
        primary=None,
        fallback=InMemoryFailureStore(),
        limit=settings.login_failure_limit,
        window_seconds=settings.login_failure_window_seconds,
    )


_PROJECT_CREATE_ERROR_STATUS_CODES = ("400", "401", "403", "409", "422", "500")
_MEMBER_ERROR_STATUS_CODES = ("400", "401", "403", "404", "409", "422", "500")

_PROJECT_CREATE_ERROR_DESCRIPTIONS = {
    "400": "幂等键缺失或非法",
    "401": "未认证",
    "403": "权限不足、Origin 或 CSRF 校验失败",
    "409": "幂等键冲突",
    "422": "请求校验失败",
    "500": "服务器内部错误",
}


def _error_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "message": {"type": "string"},
            "request_id": {"type": "string"},
            "details": {"type": "object"},
        },
        "required": ["code", "message", "request_id", "details"],
    }


def _install_openapi_schema(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema

        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        create_project_schema = CreateProjectRequest.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )
        definitions = create_project_schema.pop("$defs", {})
        components.update(definitions)
        components["CreateProjectRequest"] = create_project_schema
        create_operation = schema["paths"]["/api/v1/projects"]["post"]
        create_operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/CreateProjectRequest"}
                }
            },
        }

        # 声明项目创建所需的请求头、会话认证方案与统一错误响应。
        create_operation["parameters"] = [
            {
                "name": "Idempotency-Key",
                "in": "header",
                "required": True,
                "schema": {"type": "string"},
                "description": "幂等键，用于同请求重放识别",
            },
            {
                "name": "X-CSRF-Token",
                "in": "header",
                "required": True,
                "schema": {"type": "string"},
                "description": "CSRF 防护令牌，须与 csrf Cookie 匹配",
            },
        ]
        schema.setdefault("components", {}).setdefault("securitySchemes", {}).update(
            {
                "sessionCookie": {"type": "apiKey", "in": "cookie", "name": "bid_session"},
                "csrfToken": {"type": "apiKey", "in": "header", "name": "X-CSRF-Token"},
            }
        )
        create_operation["security"] = [{"sessionCookie": [], "csrfToken": []}]

        components["ErrorResponse"] = _error_response_schema()
        for status_code in _PROJECT_CREATE_ERROR_STATUS_CODES:
            create_operation["responses"][status_code] = {
                "description": _PROJECT_CREATE_ERROR_DESCRIPTIONS[status_code],
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
                },
            }

        member_operations = (
            ("/api/v1/projects/{project_id}/members", "get"),
            ("/api/v1/projects/{project_id}/members", "post"),
            ("/api/v1/projects/{project_id}/members/{user_id}", "patch"),
            ("/api/v1/projects/{project_id}/members/{user_id}", "delete"),
        )
        for path, method in member_operations:
            operation = schema["paths"][path][method]
            for parameter in operation.get("parameters", []):
                if parameter.get("in") == "header" and parameter.get("name") in {
                    "Idempotency-Key",
                    "X-CSRF-Token",
                }:
                    parameter["required"] = True
            if method == "post":
                operation["parameters"] = [
                    parameter
                    for parameter in operation.get("parameters", [])
                    if parameter.get("in") != "header"
                    or parameter.get("name") not in {"Idempotency-Key", "X-CSRF-Token"}
                ] + [
                    {
                        "name": "Idempotency-Key",
                        "in": "header",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "幂等键，用于同请求重放识别",
                    },
                    {
                        "name": "X-CSRF-Token",
                        "in": "header",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "CSRF 防护令牌，须与 csrf Cookie 匹配",
                    },
                ]
            elif method == "get":
                operation["parameters"] = operation.get("parameters", [])
            else:
                operation["parameters"] = [
                    parameter
                    for parameter in operation.get("parameters", [])
                    if parameter.get("name") != "X-CSRF-Token"
                ] + [
                    {
                        "name": "X-CSRF-Token",
                        "in": "header",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "CSRF 防护令牌，须与 csrf Cookie 匹配",
                    }
                ]
            for status_code in _MEMBER_ERROR_STATUS_CODES:
                operation["responses"][status_code] = {
                    "description": "统一错误响应",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                        }
                    },
                }

        document_operations = (
            ("/api/v1/projects/{project_id}/documents", "get"),
            ("/api/v1/projects/{project_id}/documents", "post"),
        )
        for path, method in document_operations:
            operation = schema["paths"][path][method]
            if method == "post":
                for parameter in operation.get("parameters", []):
                    if parameter.get("in") == "header" and parameter.get("name") in {
                        "Idempotency-Key",
                        "X-CSRF-Token",
                    }:
                        parameter["required"] = True
                operation["security"] = [{"sessionCookie": [], "csrfToken": []}]
            else:
                operation["security"] = [{"sessionCookie": []}]
            for status_code in ("400", "401", "403", "404", "409", "422", "500"):
                operation["responses"][status_code] = {
                    "description": "统一错误响应",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                        }
                    },
                }

        app.openapi_schema = schema
        return schema

    cast(Any, app).openapi = custom_openapi


def create_app(
    *,
    settings: Settings | None = None,
    rate_limiter: FallbackLoginRateLimiter | None = None,
    now_provider: Callable[[], datetime] | None = None,
    project_creation_hooks: ProjectCreationHooks | None = None,
    document_storage: ObjectStorage | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    engine = create_engine(resolved_settings.database_url)
    session_factory = create_session_factory(engine)
    limiter = rate_limiter or _build_default_limiter(resolved_settings)
    clock = now_provider or _default_now_provider
    creation_hooks = project_creation_hooks or NoOpProjectCreationHooks()
    storage = document_storage or UnconfiguredObjectStorage()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.limiter = limiter
        app.state.clock = clock
        app.state.project_creation_hooks = creation_hooks
        app.state.document_storage = storage
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="bid-agent-ai backend", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    install_exception_handlers(app)
    app.include_router(api_router)
    _install_openapi_schema(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
