from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service as auth_service_module
from app.core.config import Settings
from app.core.db import SessionFactory
from app.core.rate_limit import FallbackLoginRateLimiter, InMemoryFailureStore
from app.core.security import PasswordHasher
from app.db.models.audit import AuditEvent
from app.db.models.iam import User, UserSession
from app.main import create_app
from tests.factories import MutableClock, create_organization, create_user

TEST_DATABASE_URL = "postgresql+psycopg://bid_agent:bid_agent_test@localhost:55432/bid_agent_test"
VALID_ORIGIN = "http://frontend.localhost"
REQUEST_ID = "req-password-001"

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
    result = await session.execute(select(UserSession).order_by(UserSession.created_at.asc()))
    return list(result.scalars().all())


async def _load_audit_events(session: AsyncSession) -> list[AuditEvent]:
    result = await session.execute(select(AuditEvent).order_by(AuditEvent.occurred_at.asc()))
    return list(result.scalars().all())


async def _seed_user(
    app: FastAPI,
    *,
    must_change_password: bool = False,
    password: str = "Password-123!",
) -> User:
    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        organization = create_organization(tenant_key="yunqi")
        user = create_user(
            organization_id=organization.id,
            must_change_password=must_change_password,
            password=password,
        )
        session.add(organization)
        session.add(user)
        await session.commit()
        return user


async def _login(
    client: httpx.AsyncClient,
    user: User,
    *,
    password: str = "Password-123!",
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": user.login_name, "password": password},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    return body


async def _login_with_fresh_client(
    app: FastAPI,
    login_name: str,
    password: str,
) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": f"login-{login_name}"},
        json={"login_name": login_name, "password": password},
    )
    assert response.status_code == 200
    return client


async def test_password_change_wrong_current_password_returns_401_and_changes_nothing(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_user(app)
    await _login(client, user)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    response = await client.post(
        "/api/v1/auth/password/change",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": csrf_token,
            "X-Request-ID": REQUEST_ID,
        },
        json={"current_password": "Wrong-Password!", "new_password": "NewPassword-123"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


async def test_password_change_rejects_invalid_new_password_shapes(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_user(app)
    await _login(client, user)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    invalid_payloads = [
        {"current_password": "Password-123!", "new_password": "short1A"},
        {"current_password": "Password-123!", "new_password": "OnlyLettersOnly"},
        {"current_password": "Password-123!", "new_password": "123456789012"},
        {"current_password": "Password-123!", "new_password": "Password-123!"},
        {"current_password": "Password-123!", "new_password": "            "},
    ]

    for index, payload in enumerate(invalid_payloads):
        response = await client.post(
            "/api/v1/auth/password/change",
            headers={
                "Origin": VALID_ORIGIN,
                "X-CSRF-Token": csrf_token,
                "X-Request-ID": f"invalid-password-{index}",
            },
            json=payload,
        )

        assert response.status_code in {400, 422}


async def test_password_change_success_updates_password_and_revokes_other_sessions(
    app_client: tuple[httpx.AsyncClient, FastAPI],
    mutable_clock: MutableClock,
) -> None:
    client, app = app_client
    user = await _seed_user(app, must_change_password=True)
    await _login(client, user)
    other_client = await _login_with_fresh_client(app, user.login_name, "Password-123!")
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    mutable_clock.set(datetime(2026, 8, 21, 9, 7, tzinfo=UTC))
    response = await client.post(
        "/api/v1/auth/password/change",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": csrf_token,
            "X-Request-ID": REQUEST_ID,
        },
        json={"current_password": "Password-123!", "new_password": "NewPassword-123"},
    )

    assert response.status_code == 204

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        db_user = await _load_user(session, user.id)
        assert db_user.must_change_password is False
        assert db_user.password_changed_at == datetime(2026, 8, 21, 9, 7, tzinfo=UTC)
        assert PasswordHasher().verify_password("NewPassword-123", db_user.password_hash) is True
        assert PasswordHasher().verify_password("Password-123!", db_user.password_hash) is False

        sessions = await _load_sessions(session)
        assert len(sessions) == 2
        active_sessions = [saved for saved in sessions if saved.revoked_at is None]
        revoked_sessions = [saved for saved in sessions if saved.revoked_at is not None]
        assert len(active_sessions) == 1
        assert len(revoked_sessions) == 1
        assert revoked_sessions[0].revoke_reason == "PASSWORD_CHANGED"

        audit_events = await _load_audit_events(session)
        password_events = [
            event for event in audit_events if event.event_type == "PASSWORD_CHANGED"
        ]
        revoke_events = [event for event in audit_events if event.event_type == "SESSION_REVOKED"]
        assert len(password_events) == 1
        assert len(revoke_events) >= 1

    other_session_response = await other_client.get(
        "/api/v1/auth/session",
        headers={"X-Request-ID": "session-after-password-change"},
    )
    assert other_session_response.status_code == 401
    assert other_session_response.json()["code"] == "SESSION_EXPIRED"
    await other_client.aclose()


async def test_password_change_missing_csrf_returns_403(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_user(app)
    await _login(client, user)

    response = await client.post(
        "/api/v1/auth/password/change",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"current_password": "Password-123!", "new_password": "NewPassword-123"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_VALIDATION_FAILED"


async def test_password_change_invalid_origin_returns_403(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_user(app)
    await _login(client, user)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    response = await client.post(
        "/api/v1/auth/password/change",
        headers={
            "Origin": "http://evil.localhost",
            "X-CSRF-Token": csrf_token,
            "X-Request-ID": REQUEST_ID,
        },
        json={"current_password": "Password-123!", "new_password": "NewPassword-123"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "ORIGIN_NOT_ALLOWED"


async def test_password_change_audit_failure_rolls_back_user_and_sessions(
    app_client: tuple[httpx.AsyncClient, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = app_client
    user = await _seed_user(app, must_change_password=True)
    await _login(client, user)
    other_client = await _login_with_fresh_client(app, user.login_name, "Password-123!")
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    async def _failing_append_audit_event(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(auth_service_module, "append_audit_event", _failing_append_audit_event)

    response = await client.post(
        "/api/v1/auth/password/change",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": csrf_token,
            "X-Request-ID": "rollback-password-change",
        },
        json={"current_password": "Password-123!", "new_password": "NewPassword-123"},
    )

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        db_user = await _load_user(session, user.id)
        assert db_user.must_change_password is True
        assert PasswordHasher().verify_password("Password-123!", db_user.password_hash) is True
        assert PasswordHasher().verify_password("NewPassword-123", db_user.password_hash) is False

        sessions = await _load_sessions(session)
        assert len(sessions) == 2
        assert all(saved.revoked_at is None for saved in sessions)
        assert all(saved.revoke_reason is None for saved in sessions)

        audit_events = await _load_audit_events(session)
        assert all(event.event_type != "PASSWORD_CHANGED" for event in audit_events)
        assert all(event.metadata_json != {"reason": "PASSWORD_CHANGED"} for event in audit_events)

    other_session_response = await other_client.get(
        "/api/v1/auth/session",
        headers={"X-Request-ID": "session-after-rollback"},
    )
    assert other_session_response.status_code == 200
    await other_client.aclose()
