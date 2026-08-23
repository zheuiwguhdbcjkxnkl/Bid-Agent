from __future__ import annotations

from datetime import UTC, datetime
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
from app.db.models.audit import AuditEvent
from app.db.models.iam import User, UserSession
from app.main import create_app
from tests.factories import MutableClock, create_organization, create_user

TEST_DATABASE_URL = "postgresql+psycopg://bid_agent:bid_agent_test@localhost:55432/bid_agent_test"
VALID_ORIGIN = "http://frontend.localhost"
SECURE_VALID_ORIGIN = "https://frontend.localhost"
DOMAIN_VALID_ORIGIN = "http://frontend.example.test"
REQUEST_ID = "req-logout-001"

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
def secure_auth_settings() -> Settings:
    return Settings(
        app_env="test",
        database_url=TEST_DATABASE_URL,
        allowed_origins=[SECURE_VALID_ORIGIN],
        session_cookie_secure=True,
        login_failure_limit=3,
        login_failure_window_seconds=900,
    )


@pytest.fixture()
def domain_auth_settings() -> Settings:
    return Settings(
        app_env="test",
        database_url=TEST_DATABASE_URL,
        allowed_origins=[DOMAIN_VALID_ORIGIN],
        session_cookie_secure=False,
        session_cookie_domain=".example.test",
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


@pytest.fixture()
async def secure_app_client(
    clean_database: None,
    migrated_database: str,
    secure_auth_settings: Settings,
    mutable_clock: MutableClock,
) -> Any:
    limiter = FallbackLoginRateLimiter(
        primary=None,
        fallback=InMemoryFailureStore(),
        limit=secure_auth_settings.login_failure_limit,
        window_seconds=secure_auth_settings.login_failure_window_seconds,
    )
    app = create_app(
        settings=secure_auth_settings,
        rate_limiter=limiter,
        now_provider=mutable_clock.now,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            yield client, app


@pytest.fixture()
async def domain_app_client(
    clean_database: None,
    migrated_database: str,
    domain_auth_settings: Settings,
    mutable_clock: MutableClock,
) -> Any:
    limiter = FallbackLoginRateLimiter(
        primary=None,
        fallback=InMemoryFailureStore(),
        limit=domain_auth_settings.login_failure_limit,
        window_seconds=domain_auth_settings.login_failure_window_seconds,
    )
    app = create_app(
        settings=domain_auth_settings,
        rate_limiter=limiter,
        now_provider=mutable_clock.now,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://app.example.test",
        ) as client:
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


def _find_cookie_header(headers: list[str], cookie_name: str) -> str:
    return next(header for header in headers if header.startswith(f"{cookie_name}="))


def _assert_cookie_domain(header: str, expected_domain: str) -> None:
    normalized_domain = expected_domain.lstrip(".").lower()
    rendered_header = header.lower()
    assert (
        f"domain={normalized_domain}" in rendered_header
        or f"domain=.{normalized_domain}" in rendered_header
    )


def _restore_cookie(client: httpx.AsyncClient, name: str, value: str) -> None:
    client.cookies.set(name, value, domain="testserver.local", path="/")


async def _seed_user(app: FastAPI) -> User:
    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        organization = create_organization(tenant_key="yunqi")
        user = create_user(organization_id=organization.id)
        session.add(organization)
        session.add(user)
        await session.commit()
        return user


async def _login(
    client: httpx.AsyncClient,
    user: User,
    *,
    origin: str = VALID_ORIGIN,
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": origin, "X-Request-ID": REQUEST_ID},
        json={"login_name": user.login_name, "password": "Password-123!"},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    return body


async def test_logout_returns_204_revokes_current_session_and_clears_cookies(
    app_client: tuple[httpx.AsyncClient, FastAPI],
    mutable_clock: MutableClock,
) -> None:
    client, app = app_client
    user = await _seed_user(app)
    await _login(client, user)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    mutable_clock.set(datetime(2026, 8, 21, 9, 5, tzinfo=UTC))
    response = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": csrf_token,
            "X-Request-ID": REQUEST_ID,
        },
    )

    assert response.status_code == 204
    clear_headers = response.headers.get_list("set-cookie")
    assert len(clear_headers) == 2
    cleared_session = _find_cookie_header(clear_headers, "bid_session")
    cleared_csrf = _find_cookie_header(clear_headers, "bid_csrf")
    for header in (cleared_session, cleared_csrf):
        assert "Max-Age=0" in header
        assert "Path=/" in header
        assert "SameSite=lax" in header
        assert "Secure" not in header
    assert "HttpOnly" in cleared_session
    assert "HttpOnly" not in cleared_csrf
    assert client.cookies.get("bid_session") is None
    assert client.cookies.get("bid_csrf") is None

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        db_user = await _load_user(session, user.id)
        assert db_user.id == user.id
        sessions = await _load_sessions(session)
        assert len(sessions) == 1
        saved_session = sessions[0]
        assert saved_session.revoked_at == datetime(2026, 8, 21, 9, 5, tzinfo=UTC)
        assert saved_session.revoke_reason == "LOGOUT"

        audit_events = await _load_audit_events(session)
        logout_events = [event for event in audit_events if event.event_type == "LOGOUT"]
        assert len(logout_events) == 1
        assert logout_events[0].object_type == "USER_SESSION"
        assert logout_events[0].object_id == saved_session.id
        assert logout_events[0].actor_user_id == user.id
        assert logout_events[0].organization_id == user.organization_id


async def test_logout_secure_cookies_include_secure_on_login_and_delete(
    secure_app_client: tuple[httpx.AsyncClient, FastAPI],
    mutable_clock: MutableClock,
) -> None:
    client, app = secure_app_client
    user = await _seed_user(app)
    login_response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": SECURE_VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": user.login_name, "password": "Password-123!"},
    )
    assert login_response.status_code == 200
    login_headers = login_response.headers.get_list("set-cookie")
    assert len(login_headers) == 2
    assert all("Secure" in header for header in login_headers)

    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None
    mutable_clock.set(datetime(2026, 8, 21, 9, 5, tzinfo=UTC))
    logout_response = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": SECURE_VALID_ORIGIN,
            "X-CSRF-Token": csrf_token,
            "X-Request-ID": REQUEST_ID,
        },
    )

    assert logout_response.status_code == 204
    clear_headers = logout_response.headers.get_list("set-cookie")
    assert len(clear_headers) == 2
    assert all("Secure" in header for header in clear_headers)


async def test_logout_cookie_domain_matches_login_when_configured(
    domain_app_client: tuple[httpx.AsyncClient, FastAPI],
    mutable_clock: MutableClock,
) -> None:
    client, app = domain_app_client
    user = await _seed_user(app)
    login_response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": DOMAIN_VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": user.login_name, "password": "Password-123!"},
    )
    assert login_response.status_code == 200
    login_headers = login_response.headers.get_list("set-cookie")
    _assert_cookie_domain(_find_cookie_header(login_headers, "bid_session"), ".example.test")
    _assert_cookie_domain(_find_cookie_header(login_headers, "bid_csrf"), ".example.test")

    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None
    mutable_clock.set(datetime(2026, 8, 21, 9, 5, tzinfo=UTC))
    logout_response = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": DOMAIN_VALID_ORIGIN,
            "X-CSRF-Token": csrf_token,
            "X-Request-ID": REQUEST_ID,
        },
    )

    assert logout_response.status_code == 204
    clear_headers = logout_response.headers.get_list("set-cookie")
    assert len(clear_headers) == 2
    _assert_cookie_domain(_find_cookie_header(clear_headers, "bid_session"), ".example.test")
    _assert_cookie_domain(_find_cookie_header(clear_headers, "bid_csrf"), ".example.test")
    assert client.cookies.get("bid_session") is None
    assert client.cookies.get("bid_csrf") is None


async def test_logout_missing_csrf_returns_403(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_user(app)
    await _login(client, user)

    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_VALIDATION_FAILED"


async def test_logout_invalid_origin_returns_403_before_authentication(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_user(app)
    await _login(client, user)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    response = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": "http://evil.localhost",
            "X-CSRF-Token": csrf_token,
            "X-Request-ID": REQUEST_ID,
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "ORIGIN_NOT_ALLOWED"


async def test_logout_repeated_revoked_cookie_is_safe_and_does_not_duplicate_audit(
    app_client: tuple[httpx.AsyncClient, FastAPI],
    mutable_clock: MutableClock,
) -> None:
    client, app = app_client
    user = await _seed_user(app)
    await _login(client, user)
    raw_session_token = client.cookies.get("bid_session")
    csrf_token = client.cookies.get("bid_csrf")
    assert raw_session_token is not None
    assert csrf_token is not None

    first = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": csrf_token,
            "X-Request-ID": "req-logout-first",
        },
    )
    assert first.status_code == 204
    _restore_cookie(client, "bid_session", raw_session_token)
    _restore_cookie(client, "bid_csrf", csrf_token)

    mutable_clock.set(datetime(2026, 8, 21, 9, 6, tzinfo=UTC))
    second = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": csrf_token,
            "X-Request-ID": "req-logout-second",
        },
    )

    assert second.status_code == 204
    second_clear_headers = second.headers.get_list("set-cookie")
    assert len(second_clear_headers) == 2
    second_cleared_session = _find_cookie_header(second_clear_headers, "bid_session")
    second_cleared_csrf = _find_cookie_header(second_clear_headers, "bid_csrf")
    for header in (second_cleared_session, second_cleared_csrf):
        assert "Max-Age=0" in header
        assert "Path=/" in header
        assert "SameSite=lax" in header
    assert client.cookies.get("bid_session") is None
    assert client.cookies.get("bid_csrf") is None

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        logout_events = [
            event for event in await _load_audit_events(session) if event.event_type == "LOGOUT"
        ]
        assert len(logout_events) == 1


async def test_logout_fake_token_returns_401(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = app_client
    client.cookies.set("bid_session", "fake-session-token")
    client.cookies.set("bid_csrf", "fake-csrf-token")

    response = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": "fake-csrf-token",
            "X-Request-ID": REQUEST_ID,
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] in {"UNAUTHENTICATED", "SESSION_EXPIRED"}
