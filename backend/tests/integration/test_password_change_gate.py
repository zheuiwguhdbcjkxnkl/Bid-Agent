from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import Depends, FastAPI

from app.auth.dependencies import require_business_access
from app.core.config import Settings
from app.core.rate_limit import FallbackLoginRateLimiter, InMemoryFailureStore
from app.main import create_app
from tests.factories import MutableClock, create_organization, create_user

TEST_DATABASE_URL = "postgresql+psycopg://bid_agent:bid_agent_test@localhost:55432/bid_agent_test"
VALID_ORIGIN = "http://frontend.localhost"
REQUEST_ID = "req-gate-001"

pytestmark = pytest.mark.asyncio
BUSINESS_ACCESS_DEPENDS = Depends(require_business_access)


@pytest.fixture()
def auth_settings() -> Settings:
    return Settings(
        app_env="test",
        database_url=TEST_DATABASE_URL,
        allowed_origins=[VALID_ORIGIN],
        session_cookie_secure=False,
        login_failure_limit=3,
        login_failure_window_seconds=900,
    )


@pytest.fixture()
def mutable_clock() -> MutableClock:
    return MutableClock(datetime(2026, 8, 21, 9, 0, tzinfo=UTC))


@pytest.fixture()
async def app_client(
    clean_database: None,
    migrated_database: str,
    auth_settings: Settings,
    mutable_clock: MutableClock,
) -> Any:
    limiter = FallbackLoginRateLimiter(
        primary=None,
        fallback=InMemoryFailureStore(),
        limit=auth_settings.login_failure_limit,
        window_seconds=auth_settings.login_failure_window_seconds,
    )
    app = create_app(
        settings=auth_settings,
        rate_limiter=limiter,
        now_provider=mutable_clock.now,
    )

    async def _business_gate_endpoint(_: Any = BUSINESS_ACCESS_DEPENDS) -> dict[str, str]:
        return {"status": "ok"}

    app.add_api_route(
        "/_test/business-gate",
        _business_gate_endpoint,
        methods=["GET"],
    )

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client, app


async def _seed_user(app: FastAPI, *, must_change_password: bool = False) -> Any:
    session_factory = app.state.session_factory
    async with session_factory() as session:
        organization = create_organization(tenant_key="yunqi")
        user = create_user(
            organization_id=organization.id,
            must_change_password=must_change_password,
        )
        session.add(organization)
        session.add(user)
        await session.commit()
        return user


async def _login(client: httpx.AsyncClient, login_name: str) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": login_name, "password": "Password-123!"},
    )
    assert response.status_code == 200


async def test_business_gate_blocks_user_who_must_change_password(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_user(app, must_change_password=True)
    await _login(client, user.login_name)

    response = await client.get("/_test/business-gate", headers={"X-Request-ID": REQUEST_ID})

    assert response.status_code == 403
    assert response.json()["code"] == "PASSWORD_CHANGE_REQUIRED"


async def test_business_gate_allows_normal_user(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_user(app, must_change_password=False)
    await _login(client, user.login_name)

    response = await client.get("/_test/business-gate", headers={"X-Request-ID": REQUEST_ID})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_password_change_reopens_business_access_for_current_session(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_user(app, must_change_password=True)
    await _login(client, user.login_name)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    blocked = await client.get("/_test/business-gate", headers={"X-Request-ID": "gate-before"})
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "PASSWORD_CHANGE_REQUIRED"

    session_response = await client.get(
        "/api/v1/auth/session",
        headers={"X-Request-ID": "session-ok"},
    )
    assert session_response.status_code == 200

    change_response = await client.post(
        "/api/v1/auth/password/change",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": csrf_token,
            "X-Request-ID": "change-password-gate",
        },
        json={"current_password": "Password-123!", "new_password": "NewPassword-123"},
    )
    assert change_response.status_code == 204

    opened = await client.get("/_test/business-gate", headers={"X-Request-ID": "gate-after"})
    assert opened.status_code == 200
    assert opened.json() == {"status": "ok"}
