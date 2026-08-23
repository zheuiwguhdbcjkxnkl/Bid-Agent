from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.core.config import Settings
from app.core.rate_limit import FallbackLoginRateLimiter, InMemoryFailureStore
from app.db.models.audit import AuditEvent
from app.db.models.iam import IdempotencyRecord, User
from app.db.models.project import BidProject
from app.main import create_app
from tests.factories import MutableClock, create_organization, create_user

TEST_DATABASE_URL = "postgresql+psycopg://bid_agent:bid_agent_test@localhost:55432/bid_agent_test"
VALID_ORIGIN = "http://frontend.localhost"
REQUEST_ID = "req-project-idempotency-001"

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
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client, app


async def _seed_user(
    app: FastAPI,
    *,
    system_role: str = "BID_MANAGER",
    organization_tenant_key: str = "yunqi",
) -> User:
    session_factory = app.state.session_factory
    async with session_factory() as session:
        organization = create_organization(tenant_key=organization_tenant_key)
        user = create_user(
            organization_id=organization.id,
            system_role=system_role,
        )
        session.add(organization)
        session.add(user)
        await session.commit()
        return user


async def _seed_user_in_existing_organization(
    app: FastAPI,
    *,
    organization_id: Any,
    login_name: str,
    system_role: str = "BID_MANAGER",
) -> User:
    session_factory = app.state.session_factory
    async with session_factory() as session:
        user = create_user(
            organization_id=organization_id,
            login_name=login_name,
            system_role=system_role,
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
    deadline_at: str = "2026-09-01T10:00:00+08:00",
    project_name: str = "滨江市政务云平台",
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
            "deadline_at": deadline_at,
            "owner_user_id": owner_user_id,
        },
    )


async def test_create_project_rejects_blank_idempotency_key(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    owner = await _seed_user(app)
    await _login(client, owner.login_name)

    response = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        idempotency_key="   ",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


async def test_create_project_rejects_too_long_idempotency_key(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    owner = await _seed_user(app)
    await _login(client, owner.login_name)

    response = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        idempotency_key="k" * 256,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


async def test_create_project_replays_same_key_same_payload(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    owner = await _seed_user(app)
    await _login(client, owner.login_name)

    first = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        idempotency_key="same-payload-key",
    )
    second = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        idempotency_key="same-payload-key",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json() == first.json()

    session_factory = app.state.session_factory
    async with session_factory() as session:
        projects = list((await session.execute(select(BidProject))).scalars().all())
        records = list((await session.execute(select(IdempotencyRecord))).scalars().all())
        events = list((await session.execute(select(AuditEvent))).scalars().all())

    project_created_events = [event for event in events if event.event_type == "PROJECT_CREATED"]
    assert len(projects) == 1
    assert len(records) == 1
    assert len(project_created_events) == 1


async def test_create_project_replays_equivalent_deadline_timezones(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    owner = await _seed_user(app)
    await _login(client, owner.login_name)

    first = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        idempotency_key="same-deadline-key",
        deadline_at="2026-09-01T10:00:00+08:00",
    )
    second = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        idempotency_key="same-deadline-key",
        deadline_at="2026-09-01T02:00:00+00:00",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json() == first.json()


async def test_create_project_rejects_same_key_different_payload(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    owner = await _seed_user(app)
    await _login(client, owner.login_name)

    first = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        idempotency_key="conflict-key",
        project_name="项目A",
    )
    second = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        idempotency_key="conflict-key",
        project_name="项目B",
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "IDEMPOTENCY_CONFLICT"


async def test_create_project_rejects_control_character_idempotency_key(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    owner = await _seed_user(app)
    await _login(client, owner.login_name)

    response = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        idempotency_key="bad\nkey",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


async def test_create_project_allows_same_key_for_different_actors(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor_one = await _seed_user(app)
    actor_two = await _seed_user_in_existing_organization(
        app,
        organization_id=actor_one.organization_id,
        login_name="actor-two",
    )

    await _login(client, actor_one.login_name)
    first = await _post_create_project(
        client,
        owner_user_id=str(actor_one.id),
        idempotency_key="shared-key",
        project_name="项目一",
    )

    client.cookies.clear()
    await _login(client, actor_two.login_name)
    second = await _post_create_project(
        client,
        owner_user_id=str(actor_two.id),
        idempotency_key="shared-key",
        project_name="项目二",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]

    session_factory = app.state.session_factory
    async with session_factory() as session:
        projects = list((await session.execute(select(BidProject))).scalars().all())
        records = list((await session.execute(select(IdempotencyRecord))).scalars().all())

    assert len(projects) == 2
    assert len(records) == 2
