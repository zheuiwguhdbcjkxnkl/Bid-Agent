from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import DomainError, install_exception_handlers
from app.core.request_id import REQUEST_ID_HEADER, RequestIdMiddleware


class LoginPayload(BaseModel):
    login_name: str
    password: str
    remember_me: bool


def build_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    install_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise DomainError(
            status_code=403,
            code="FORBIDDEN",
            message="没有访问权限",
        )

    @app.get("/auth-required")
    async def auth_required() -> None:
        raise HTTPException(status_code=401, detail="未登录")

    @app.post("/login")
    async def login(payload: LoginPayload) -> dict[str, str]:
        return {"login_name": payload.login_name}

    @app.get("/items/{item_id}")
    async def read_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("database exploded")

    return app


async def request_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_domain_error_returns_unified_contract_with_request_id() -> None:
    async for client in request_client(build_test_app()):
        response = await client.get(
            "/boom",
            headers={"X-Request-ID": "req-contract-001"},
        )

    assert response.status_code == 403
    assert response.headers["X-Request-ID"] == "req-contract-001"
    assert response.json() == {
        "code": "FORBIDDEN",
        "message": "没有访问权限",
        "request_id": "req-contract-001",
        "details": {},
    }


@pytest.mark.asyncio
async def test_error_response_generates_same_request_id_when_header_missing() -> None:
    async for client in request_client(build_test_app()):
        response = await client.get("/boom")

    body = response.json()
    request_id = response.headers["X-Request-ID"]

    assert response.status_code == 403
    assert request_id
    assert body == {
        "code": "FORBIDDEN",
        "message": "没有访问权限",
        "request_id": request_id,
        "details": {},
    }


@pytest.mark.asyncio
async def test_error_response_replaces_too_long_request_id_header() -> None:
    async for client in request_client(build_test_app()):
        response = await client.get(
            "/boom",
            headers={REQUEST_ID_HEADER: "x" * 200},
        )

    body = response.json()
    request_id = response.headers[REQUEST_ID_HEADER]

    assert response.status_code == 403
    assert request_id == body["request_id"]
    assert request_id != "x" * 200
    assert len(request_id) == 32
    assert all(character in "0123456789abcdef" for character in request_id)


@pytest.mark.asyncio
async def test_error_response_replaces_illegal_request_id_header() -> None:
    async for client in request_client(build_test_app()):
        response = await client.get(
            "/boom",
            headers={REQUEST_ID_HEADER: "req/ bad"},
        )

    body = response.json()
    request_id = response.headers[REQUEST_ID_HEADER]

    assert response.status_code == 403
    assert request_id == body["request_id"]
    assert request_id != "req/ bad"
    assert len(request_id) == 32
    assert all(character in "0123456789abcdef" for character in request_id)


@pytest.mark.asyncio
async def test_error_response_accepts_legal_request_id_at_128_chars() -> None:
    legal_request_id = "a" * 128

    async for client in request_client(build_test_app()):
        response = await client.get(
            "/boom",
            headers={REQUEST_ID_HEADER: legal_request_id},
        )

    assert response.status_code == 403
    assert response.headers[REQUEST_ID_HEADER] == legal_request_id
    assert response.json()["request_id"] == legal_request_id


@pytest.mark.asyncio
async def test_validation_error_returns_standard_contract() -> None:
    async for client in request_client(build_test_app()):
        response = await client.get("/items/not-an-int")

    body = response.json()

    assert response.status_code == 422
    assert response.headers["X-Request-ID"] == body["request_id"]
    assert set(body.keys()) == {"code", "message", "request_id", "details"}
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "请求参数校验失败"
    assert isinstance(body["request_id"], str)
    assert body["request_id"]
    assert isinstance(body["details"], dict)
    assert isinstance(body["details"].get("errors"), list)
    assert body["details"]["errors"]


@pytest.mark.asyncio
async def test_validation_error_does_not_leak_input_values_in_response_text() -> None:
    leaked_password = "SuperSecret-123!"

    async for client in request_client(build_test_app()):
        response = await client.post(
            "/login",
            json={
                "login_name": "alice",
                "password": leaked_password,
            },
            headers={REQUEST_ID_HEADER: "req-validation-redact"},
        )

    body = response.json()
    response_text = response.text

    assert response.status_code == 422
    assert response.headers[REQUEST_ID_HEADER] == "req-validation-redact"
    assert response.headers[REQUEST_ID_HEADER] == body["request_id"]
    assert set(body.keys()) == {"code", "message", "request_id", "details"}
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "请求参数校验失败"
    assert leaked_password not in response_text
    assert isinstance(body["details"], dict)
    assert isinstance(body["details"].get("errors"), list)
    assert body["details"]["errors"]


@pytest.mark.asyncio
async def test_http_exception_returns_unified_contract_with_request_id() -> None:
    async for client in request_client(build_test_app()):
        response = await client.get(
            "/auth-required",
            headers={REQUEST_ID_HEADER: "req-http-401"},
        )

    body = response.json()

    assert response.status_code == 401
    assert response.headers[REQUEST_ID_HEADER] == "req-http-401"
    assert body == {
        "code": "UNAUTHENTICATED",
        "message": "未登录",
        "request_id": "req-http-401",
        "details": {},
    }


@pytest.mark.asyncio
async def test_unknown_route_returns_unified_not_found_contract_with_request_id() -> None:
    async for client in request_client(build_test_app()):
        response = await client.get(
            "/missing-route",
            headers={REQUEST_ID_HEADER: "req-http-404"},
        )

    body = response.json()

    assert response.status_code == 404
    assert response.headers[REQUEST_ID_HEADER] == "req-http-404"
    assert body == {
        "code": "NOT_FOUND",
        "message": "Not Found",
        "request_id": "req-http-404",
        "details": {},
    }


@pytest.mark.asyncio
async def test_internal_error_does_not_leak_exception_details() -> None:
    async for client in request_client(build_test_app()):
        response = await client.get("/crash")

    body = response.json()
    response_text = response.text

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == body["request_id"]
    assert body == {
        "code": "INTERNAL_ERROR",
        "message": "服务器内部错误",
        "request_id": body["request_id"],
        "details": {},
    }
    assert "RuntimeError" not in response_text
    assert "database exploded" not in response_text
    assert "Traceback" not in response_text
    assert "sqlalchemy" not in response_text.lower()
    assert "psycopg" not in response_text.lower()


def test_settings_allows_test_database_suffix_in_test_env() -> None:
    settings = Settings(
        app_env="test", database_url="postgresql+psycopg://user:pass@localhost:5432/bid_agent_test"
    )

    assert settings.database_url.endswith("/bid_agent_test")


def test_settings_rejects_non_test_database_in_test_env() -> None:
    with pytest.raises(ValueError, match="_test"):
        Settings(
            app_env="test", database_url="postgresql+psycopg://user:pass@localhost:5432/bid_agent"
        )


def test_settings_does_not_restrict_database_name_in_development_env() -> None:
    settings = Settings(
        app_env="development",
        database_url="postgresql+psycopg://user:pass@localhost:5432/bid_agent",
    )

    assert settings.database_url.endswith("/bid_agent")


DOMAIN_ERROR_CASES = [
    (401, "INVALID_CREDENTIALS", "登录凭据错误"),
    (401, "UNAUTHENTICATED", "未登录"),
    (401, "SESSION_EXPIRED", "会话已过期"),
    (403, "FORBIDDEN", "无权限"),
    (403, "PASSWORD_CHANGE_REQUIRED", "需修改密码"),
    (403, "ORIGIN_NOT_ALLOWED", "来源不允许"),
    (403, "CSRF_VALIDATION_FAILED", "CSRF 校验失败"),
    (400, "IDEMPOTENCY_KEY_REQUIRED", "缺少幂等键"),
    (409, "IDEMPOTENCY_CONFLICT", "幂等键冲突"),
    (422, "OWNER_ROLE_MISMATCH", "负责人角色不匹配"),
    (422, "OWNER_ORGANIZATION_MISMATCH", "负责人组织不一致"),
    (409, "PROJECT_CODE_CONFLICT", "项目编号冲突"),
    (429, "LOGIN_RATE_LIMITED", "登录过于频繁"),
]


def build_domain_error_app(status_code: int, code: str, message: str) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    install_exception_handlers(app)

    @app.get("/error")
    async def error() -> None:
        raise DomainError(status_code=status_code, code=code, message=message)

    return app


@pytest.mark.asyncio
@pytest.mark.parametrize(("status_code", "code", "message"), DOMAIN_ERROR_CASES)
async def test_domain_error_codes_return_unified_contract(
    status_code: int, code: str, message: str
) -> None:
    async for client in request_client(build_domain_error_app(status_code, code, message)):
        response = await client.get("/error", headers={"X-Request-ID": "req-error-param"})

    body = response.json()

    assert response.status_code == status_code
    assert set(body.keys()) == {"code", "message", "request_id", "details"}
    assert body["code"] == code
    assert body["message"] == message
    assert response.headers["X-Request-ID"] == body["request_id"]
    assert isinstance(body["details"], dict)
