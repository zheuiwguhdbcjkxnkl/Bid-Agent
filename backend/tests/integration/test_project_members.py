from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.core.rate_limit import FallbackLoginRateLimiter, InMemoryFailureStore
from app.db.models.iam import User
from app.main import create_app
from tests.factories import MutableClock, create_organization, create_user

TEST_DATABASE_URL = "postgresql+psycopg://bid_agent:bid_agent_test@localhost:55432/bid_agent_test"
VALID_ORIGIN = "http://frontend.localhost"
REQUEST_ID = "req-project-members-001"

pytestmark = pytest.mark.asyncio


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
    return MutableClock(datetime(2026, 8, 24, 9, 0, tzinfo=UTC))


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
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client, app


async def _seed_user(
    app: FastAPI,
    *,
    system_role: str = "BID_MANAGER",
    tenant_key: str = "yunqi",
    login_name: str = "manager",
    display_name: str = "负责人",
) -> User:
    session_factory = app.state.session_factory
    async with session_factory() as session:
        organization = create_organization(tenant_key=tenant_key)
        user = create_user(
            organization_id=organization.id,
            system_role=system_role,
            login_name=login_name,
            display_name=display_name,
        )
        session.add(organization)
        session.add(user)
        await session.commit()
        return user


async def _seed_user_in_organization(
    app: FastAPI,
    *,
    organization_id: Any,
    system_role: str,
    login_name: str,
    display_name: str = "成员",
) -> User:
    session_factory = app.state.session_factory
    async with session_factory() as session:
        user = create_user(
            organization_id=organization_id,
            system_role=system_role,
            login_name=login_name,
            display_name=display_name,
        )
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


async def _post_create_project(
    client: httpx.AsyncClient,
    *,
    owner_user_id: str,
    idempotency_key: str,
    project_name: str = "成员测试项目",
) -> httpx.Response:
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None
    return await client.post(
        "/api/v1/projects",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": csrf_token,
            "Idempotency-Key": idempotency_key,
            "X-Request-ID": REQUEST_ID,
        },
        json={
            "project_name": project_name,
            "procurement_method": "PUBLIC_TENDER",
            "regime_type": "GOVERNMENT_PROCUREMENT",
            "deadline_at": "2026-09-01T10:00:00+08:00",
            "owner_user_id": owner_user_id,
        },
    )


async def test_list_members_returns_manager(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)

    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="list-members-1"
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    response = await client.get(
        f"/api/v1/projects/{project_id}/members",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["user_id"] == str(actor.id)
    assert item["display_name"] == actor.display_name
    assert item["project_role"] == "BID_MANAGER"
