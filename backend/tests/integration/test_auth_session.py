from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import SessionFactory
from app.core.rate_limit import FallbackLoginRateLimiter, InMemoryFailureStore
from app.core.security import hash_session_token
from app.db.models.audit import AuditEvent
from app.db.models.iam import User, UserSession
from app.main import create_app
from tests.factories import MutableClock, create_organization, create_user

TEST_DATABASE_URL = "postgresql+psycopg://bid_agent:bid_agent_test@localhost:55432/bid_agent_test"
VALID_ORIGIN = "http://frontend.localhost"
REQUEST_ID = "req-session-001"

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


async def _get_session_factory(app: FastAPI) -> SessionFactory:
    return app.state.session_factory  # type: ignore[no-any-return]


async def _load_user(session: AsyncSession, user_id: UUID) -> User:
    user = await session.get(User, user_id)
    assert user is not None
    return user


async def _load_sessions(session: AsyncSession) -> list[UserSession]:
    result = await session.execute(select(UserSession))
    return list(result.scalars().all())


async def _load_audit_events(session: AsyncSession) -> list[AuditEvent]:
    result = await session.execute(select(AuditEvent).order_by(AuditEvent.occurred_at.asc()))
    return list(result.scalars().all())


async def _seed_user(
    app: FastAPI,
    *,
    system_role: str = "BID_MANAGER",
    must_change_password: bool = False,
    account_status: str = "ACTIVE",
    login_name: str = "admin",
) -> User:
    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        organization = create_organization(tenant_key="yunqi")
        user = create_user(
            organization_id=organization.id,
            system_role=system_role,
            must_change_password=must_change_password,
            account_status=account_status,
            login_name=login_name,
        )
        session.add(organization)
        session.add(user)
        await session.commit()
        return user


async def _login(client: httpx.AsyncClient, user: User) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": user.login_name, "password": "Password-123!"},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    return body


async def test_session_returns_current_user_and_touches_idle_expiry(
    app_client: tuple[httpx.AsyncClient, FastAPI],
    mutable_clock: MutableClock,
) -> None:
    client, app = app_client
    user = await _seed_user(app)
    login_body = await _login(client, user)

    mutable_clock.advance(minutes=10)
    response = await client.get("/api/v1/auth/session", headers={"X-Request-ID": REQUEST_ID})

    assert response.status_code == 200
    body = response.json()
    assert body["user"] == login_body["user"]
    assert body["must_change_password"] is False
    assert body["allowed_actions"] == [
        "SESSION_READ",
        "LOGOUT",
        "PASSWORD_CHANGE",
        "WORKBENCH_READ",
        "PROJECT_READ",
        "PROJECT_CREATE",
    ]
    assert body["absolute_expires_at"] == "2026-08-21T17:00:00Z"
    assert body["idle_expires_at"] == "2026-08-21T09:40:00Z"

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        sessions = await _load_sessions(session)
        assert len(sessions) == 1
        saved = sessions[0]
        assert saved.last_seen_at == datetime(2026, 8, 21, 9, 10, tzinfo=UTC)
        assert saved.idle_expires_at == datetime(2026, 8, 21, 9, 40, tzinfo=UTC)
        assert saved.absolute_expires_at == datetime(2026, 8, 21, 17, 0, tzinfo=UTC)


async def test_session_caps_idle_expiry_at_absolute_deadline(
    app_client: tuple[httpx.AsyncClient, FastAPI],
    mutable_clock: MutableClock,
) -> None:
    client, app = app_client
    user = await _seed_user(app)
    await _login(client, user)

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        saved = (await _load_sessions(session))[0]
        saved.last_seen_at = datetime(2026, 8, 21, 16, 24, tzinfo=UTC)
        saved.idle_expires_at = datetime(2026, 8, 21, 16, 54, tzinfo=UTC)
        await session.commit()

    mutable_clock.set(datetime(2026, 8, 21, 16, 50, tzinfo=UTC))
    response = await client.get("/api/v1/auth/session", headers={"X-Request-ID": REQUEST_ID})

    assert response.status_code == 200
    body = response.json()
    assert body["idle_expires_at"] == "2026-08-21T17:00:00Z"
    assert body["absolute_expires_at"] == "2026-08-21T17:00:00Z"

    async with session_factory() as session:
        saved = (await _load_sessions(session))[0]
        assert saved.last_seen_at == datetime(2026, 8, 21, 16, 50, tzinfo=UTC)
        assert saved.idle_expires_at == datetime(2026, 8, 21, 17, 0, tzinfo=UTC)


async def test_session_must_change_password_limits_allowed_actions(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_user(app, must_change_password=True)
    await _login(client, user)

    response = await client.get("/api/v1/auth/session", headers={"X-Request-ID": REQUEST_ID})

    assert response.status_code == 200
    assert response.json()["allowed_actions"] == [
        "SESSION_READ",
        "LOGOUT",
        "PASSWORD_CHANGE",
    ]


async def test_session_missing_cookie_returns_unauthenticated(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = app_client

    response = await client.get("/api/v1/auth/session", headers={"X-Request-ID": REQUEST_ID})

    assert response.status_code == 401
    assert response.json() == {
        "code": "UNAUTHENTICATED",
        "message": "未登录",
        "request_id": REQUEST_ID,
        "details": {},
    }


async def test_session_empty_cookie_returns_unauthenticated(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = app_client
    client.cookies.set("bid_session", "")

    response = await client.get("/api/v1/auth/session", headers={"X-Request-ID": REQUEST_ID})

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


async def test_session_unknown_token_returns_unauthenticated(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = app_client
    client.cookies.set("bid_session", "fake-session-token")

    response = await client.get("/api/v1/auth/session", headers={"X-Request-ID": REQUEST_ID})

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


async def test_session_revoked_returns_session_expired_without_duplicate_audit(
    app_client: tuple[httpx.AsyncClient, FastAPI],
    mutable_clock: MutableClock,
) -> None:
    client, app = app_client
    user = await _seed_user(app)
    await _login(client, user)

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        saved = (await _load_sessions(session))[0]
        saved.revoked_at = mutable_clock.now() - timedelta(minutes=1)
        saved.revoke_reason = "LOGOUT"
        await session.commit()
        audit_before = await _load_audit_events(session)

    response = await client.get("/api/v1/auth/session", headers={"X-Request-ID": REQUEST_ID})

    assert response.status_code == 401
    assert response.json()["code"] == "SESSION_EXPIRED"

    async with session_factory() as session:
        saved = (await _load_sessions(session))[0]
        assert saved.revoked_at == datetime(2026, 8, 21, 8, 59, tzinfo=UTC)
        assert saved.revoke_reason == "LOGOUT"
        audit_after = await _load_audit_events(session)
        assert len(audit_after) == len(audit_before)


async def test_session_idle_expiry_revokes_session_once_and_hides_token(
    app_client: tuple[httpx.AsyncClient, FastAPI],
    mutable_clock: MutableClock,
) -> None:
    client, app = app_client
    user = await _seed_user(app)
    await _login(client, user)
    raw_token = client.cookies.get("bid_session")
    assert raw_token is not None

    mutable_clock.set(datetime(2026, 8, 21, 9, 30, tzinfo=UTC))
    response = await client.get("/api/v1/auth/session", headers={"X-Request-ID": REQUEST_ID})

    assert response.status_code == 401
    assert response.json()["code"] == "SESSION_EXPIRED"

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        saved = (await _load_sessions(session))[0]
        assert saved.token_hash == hash_session_token(raw_token)
        assert saved.revoked_at == datetime(2026, 8, 21, 9, 30, tzinfo=UTC)
        assert saved.revoke_reason == "EXPIRED"
        audit_events = await _load_audit_events(session)
        revoke_events = [event for event in audit_events if event.event_type == "SESSION_REVOKED"]
        assert len(revoke_events) == 1
        event = revoke_events[0]
        assert event.organization_id == user.organization_id
        assert event.project_id is None
        assert event.actor_user_id == user.id
        assert event.object_type == "USER_SESSION"
        assert event.object_id == saved.id
        assert event.metadata_json == {"reason": "EXPIRED"}
        rendered = str(event.metadata_json)
        assert raw_token not in rendered


async def test_session_absolute_expiry_revokes_session_once(
    app_client: tuple[httpx.AsyncClient, FastAPI],
    mutable_clock: MutableClock,
) -> None:
    client, app = app_client
    user = await _seed_user(app)
    await _login(client, user)

    mutable_clock.set(datetime(2026, 8, 21, 17, 0, tzinfo=UTC))
    response = await client.get("/api/v1/auth/session", headers={"X-Request-ID": REQUEST_ID})

    assert response.status_code == 401
    assert response.json()["code"] == "SESSION_EXPIRED"

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        saved = (await _load_sessions(session))[0]
        assert saved.revoked_at == datetime(2026, 8, 21, 17, 0, tzinfo=UTC)
        assert saved.revoke_reason == "EXPIRED"
        revoke_events = [
            event
            for event in await _load_audit_events(session)
            if event.event_type == "SESSION_REVOKED"
        ]
        assert len(revoke_events) == 1


async def test_session_disabled_user_revokes_and_returns_unauthenticated(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_user(app)
    await _login(client, user)

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        db_user = await _load_user(session, user.id)
        db_user.account_status = "DISABLED"
        await session.commit()

    response = await client.get("/api/v1/auth/session", headers={"X-Request-ID": REQUEST_ID})

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"

    async with session_factory() as session:
        saved = (await _load_sessions(session))[0]
        assert saved.revoke_reason == "ACCOUNT_DISABLED"
        revoke_events = [
            event
            for event in await _load_audit_events(session)
            if event.event_type == "SESSION_REVOKED"
        ]
        assert len(revoke_events) == 1
        assert revoke_events[0].metadata_json == {"reason": "ACCOUNT_DISABLED"}


async def test_session_does_not_require_origin_or_csrf_headers(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_user(app)
    await _login(client, user)

    response = await client.get("/api/v1/auth/session")

    assert response.status_code == 200


async def test_session_other_non_manager_user_has_no_project_create(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_user(app, system_role="COMMERCIAL_WRITER", login_name="writer")
    await _login(client, user)

    response = await client.get("/api/v1/auth/session", headers={"X-Request-ID": REQUEST_ID})

    assert response.status_code == 200
    assert response.json()["allowed_actions"] == [
        "SESSION_READ",
        "LOGOUT",
        "PASSWORD_CHANGE",
        "WORKBENCH_READ",
        "PROJECT_READ",
    ]
