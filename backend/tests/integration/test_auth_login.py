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
from app.db.models.audit import AuditEvent
from app.db.models.iam import Organization, User, UserSession
from app.main import create_app
from tests.factories import MutableClock, create_organization, create_user

TEST_DATABASE_URL = "postgresql+psycopg://bid_agent:bid_agent_test@localhost:55432/bid_agent_test"
VALID_ORIGIN = "http://frontend.localhost"
SECURE_VALID_ORIGIN = "https://frontend.localhost"
DOMAIN_VALID_ORIGIN = "http://frontend.example.test"
REQUEST_ID = "req-login-001"


async def _count_sessions(session: AsyncSession) -> int:
    result = await session.execute(select(UserSession))
    return len(result.scalars().all())


async def _load_sessions(session: AsyncSession) -> list[UserSession]:
    result = await session.execute(select(UserSession))
    return list(result.scalars().all())


async def _load_user(session: AsyncSession, user_id: UUID) -> User:
    user = await session.get(User, user_id)
    assert user is not None
    return user


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


async def _seed_active_user(app: FastAPI) -> User:
    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        organization = create_organization(tenant_key="yunqi")
        user = create_user(organization_id=organization.id)
        session.add(organization)
        session.add(user)
        await session.commit()
        return user


async def _seed_disabled_user(app: FastAPI) -> User:
    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        organization = create_organization(tenant_key="yunqi")
        user = create_user(organization_id=organization.id, account_status="DISABLED")
        session.add(organization)
        session.add(user)
        await session.commit()
        return user


async def _seed_single_organization(app: FastAPI) -> Organization:
    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        organization = create_organization(tenant_key="yunqi")
        session.add(organization)
        await session.commit()
        return organization


async def _seed_organization(app: FastAPI, organization: Organization) -> Organization:
    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        session.add(organization)
        await session.commit()
        return organization


async def _seed_user_in_existing_organization(app: FastAPI, user: User) -> User:
    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        session.add(user)
        await session.commit()
        return user


@pytest.mark.asyncio
async def test_login_success_sets_cookies_returns_session_and_persists_hashed_token_only(
    app_client: tuple[httpx.AsyncClient, FastAPI],
    mutable_clock: MutableClock,
) -> None:
    client, app = app_client
    user = await _seed_active_user(app)

    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": user.login_name, "password": "Password-123!"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == str(user.id)
    assert body["user"]["organization_id"] == str(user.organization_id)
    assert body["user"]["login_name"] == user.login_name
    assert body["must_change_password"] is False
    assert body["allowed_actions"] == [
        "SESSION_READ",
        "LOGOUT",
        "PASSWORD_CHANGE",
        "WORKBENCH_READ",
        "PROJECT_READ",
        "PROJECT_CREATE",
    ]
    assert body["idle_expires_at"] == "2026-08-21T09:30:00Z"
    assert body["absolute_expires_at"] == "2026-08-21T17:00:00Z"

    set_cookie_headers = response.headers.get_list("set-cookie")
    assert len(set_cookie_headers) == 2
    session_cookie = _find_cookie_header(set_cookie_headers, "bid_session")
    csrf_cookie = _find_cookie_header(set_cookie_headers, "bid_csrf")
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Path=/" in session_cookie
    assert "Max-Age=28800" in session_cookie
    assert "Secure" not in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "SameSite=lax" in csrf_cookie
    assert "Path=/" in csrf_cookie
    assert "Max-Age=28800" in csrf_cookie
    assert "Secure" not in csrf_cookie

    session_token = client.cookies.get("bid_session")
    csrf_token = client.cookies.get("bid_csrf")
    assert session_token is not None
    assert csrf_token is not None
    assert session_token != csrf_token
    assert len(session_token) >= 43
    assert len(csrf_token) >= 43

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        db_user = await _load_user(session, user.id)
        assert db_user.last_login_at == mutable_clock.now()

        sessions = await _load_sessions(session)
        assert len(sessions) == 1
        saved_session = sessions[0]
        assert saved_session.user_id == user.id
        assert saved_session.token_hash != session_token
        assert session_token not in saved_session.token_hash
        assert csrf_token not in saved_session.token_hash
        assert saved_session.idle_expires_at == mutable_clock.now() + timedelta(minutes=30)
        assert saved_session.absolute_expires_at == mutable_clock.now() + timedelta(hours=8)

        audit_events = await _load_audit_events(session)
        assert len(audit_events) == 1
        event = audit_events[0]
        assert event.event_type == "LOGIN_SUCCEEDED"
        assert event.project_id is None
        assert event.actor_user_id == user.id
        assert event.organization_id == user.organization_id
        assert event.metadata_json is not None
        rendered_metadata = str(event.metadata_json)
        assert user.login_name not in rendered_metadata
        assert "Password-123!" not in rendered_metadata
        assert session_token not in rendered_metadata
        assert csrf_token not in rendered_metadata


@pytest.mark.asyncio
async def test_login_success_sets_secure_cookie_when_configured(
    secure_app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = secure_app_client
    user = await _seed_active_user(app)

    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": SECURE_VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": user.login_name, "password": "Password-123!"},
    )

    assert response.status_code == 200
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert all("Secure" in header for header in set_cookie_headers)


@pytest.mark.asyncio
async def test_login_success_sets_cookie_domain_when_configured(
    domain_app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = domain_app_client
    user = await _seed_active_user(app)

    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": DOMAIN_VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": user.login_name, "password": "Password-123!"},
    )

    assert response.status_code == 200
    set_cookie_headers = response.headers.get_list("set-cookie")
    session_cookie = _find_cookie_header(set_cookie_headers, "bid_session")
    csrf_cookie = _find_cookie_header(set_cookie_headers, "bid_csrf")
    _assert_cookie_domain(session_cookie, ".example.test")
    _assert_cookie_domain(csrf_cookie, ".example.test")
    assert client.cookies.get("bid_session") is not None
    assert client.cookies.get("bid_csrf") is not None


@pytest.mark.asyncio
async def test_login_unknown_user_returns_same_invalid_credentials_and_writes_failure_audit(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    organization = await _seed_single_organization(app)

    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": "missing-user", "password": "Password-123!"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        assert await _count_sessions(session) == 0
        audit_events = await _load_audit_events(session)
        assert len(audit_events) == 1
        event = audit_events[0]
        assert event.event_type == "LOGIN_FAILED"
        assert event.organization_id == organization.id
        assert event.project_id is None
        assert event.actor_user_id is None
        assert event.metadata_json is not None
        assert "login_identifier_hash" in event.metadata_json
        assert "source_hash" in event.metadata_json
        rendered_metadata = str(event.metadata_json)
        assert "missing-user" not in rendered_metadata
        assert "Password-123!" not in rendered_metadata


@pytest.mark.asyncio
async def test_login_unknown_user_uses_configured_auth_tenant_when_multiple_organizations_exist(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    auth_organization = create_organization(name="云启客户", tenant_key="yunqi")
    vendor_organization = create_organization(name="供应商组织", tenant_key="vendor")
    await _seed_organization(app, auth_organization)
    await _seed_organization(app, vendor_organization)

    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": "missing-user", "password": "Password-123!"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        assert await _count_sessions(session) == 0
        audit_events = await _load_audit_events(session)
        assert len(audit_events) == 1
        event = audit_events[0]
        assert event.event_type == "LOGIN_FAILED"
        assert event.organization_id == auth_organization.id
        assert event.actor_user_id is None


@pytest.mark.asyncio
async def test_login_prefers_auth_tenant_user_when_same_login_name_exists_in_other_organization(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    auth_organization = create_organization(name="云启客户", tenant_key="yunqi")
    vendor_organization = create_organization(name="供应商组织", tenant_key="vendor")
    await _seed_organization(app, auth_organization)
    await _seed_organization(app, vendor_organization)
    auth_user = create_user(organization_id=auth_organization.id, login_name="admin")
    vendor_user = create_user(
        organization_id=vendor_organization.id,
        login_name="admin",
        password="Vendor-Password-123!",
    )
    await _seed_user_in_existing_organization(app, auth_user)
    await _seed_user_in_existing_organization(app, vendor_user)

    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": "admin", "password": "Password-123!"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == str(auth_user.id)
    assert body["user"]["organization_id"] == str(auth_organization.id)


@pytest.mark.asyncio
async def test_login_returns_internal_error_without_fake_audit_when_auth_tenant_missing(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    await _seed_organization(app, create_organization(name="供应商组织", tenant_key="vendor"))

    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": "missing-user", "password": "Password-123!"},
    )

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        assert await _count_sessions(session) == 0
        assert await _load_audit_events(session) == []


@pytest.mark.asyncio
async def test_login_accepts_normalized_whitespace_wrapped_login_name(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    auth_organization = create_organization(name="云启客户", tenant_key="yunqi")
    await _seed_organization(app, auth_organization)
    auth_user = create_user(organization_id=auth_organization.id, login_name="admin")
    await _seed_user_in_existing_organization(app, auth_user)

    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": " Admin ", "password": "Password-123!"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(auth_user.id)


@pytest.mark.asyncio
async def test_login_invalid_request_id_header_falls_back_to_generated_hex_for_response_and_audit(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    await _seed_single_organization(app)
    invalid_request_id = "bad/request/id"

    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": invalid_request_id},
        json={"login_name": "missing-user", "password": "Password-123!"},
    )

    assert response.status_code == 401
    request_id = response.headers["X-Request-ID"]
    assert request_id != invalid_request_id
    assert len(request_id) == 32
    assert all(character in "0123456789abcdef" for character in request_id)
    assert response.json()["request_id"] == request_id

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        audit_events = await _load_audit_events(session)
        assert len(audit_events) == 1
        assert audit_events[0].request_id == request_id


@pytest.mark.asyncio
async def test_login_accepts_legal_request_id_at_128_char_boundary(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_active_user(app)
    request_id = "a" * 128

    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": request_id},
        json={"login_name": user.login_name, "password": "Password-123!"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    assert response.json()["user"]["id"] == str(user.id)


@pytest.mark.asyncio
async def test_login_wrong_password_returns_invalid_credentials_and_creates_no_session(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_active_user(app)

    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": user.login_name, "password": "Wrong-Password!"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        assert await _count_sessions(session) == 0


@pytest.mark.asyncio
async def test_login_disabled_user_returns_same_invalid_credentials_and_creates_no_session(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_disabled_user(app)

    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": user.login_name, "password": "Password-123!"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        assert await _count_sessions(session) == 0


@pytest.mark.asyncio
async def test_login_rejects_invalid_origin_before_authentication(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    await _seed_active_user(app)

    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": "http://evil.localhost", "X-Request-ID": REQUEST_ID},
        json={"login_name": "admin", "password": "Password-123!"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "ORIGIN_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_login_returns_rate_limited_on_threshold_attempt(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    user = await _seed_active_user(app)

    first = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": "req-login-1"},
        json={"login_name": user.login_name, "password": "Wrong-Password!"},
    )
    second = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": "req-login-2"},
        json={"login_name": user.login_name, "password": "Wrong-Password!"},
    )
    third = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": "req-login-3"},
        json={"login_name": user.login_name, "password": "Wrong-Password!"},
    )

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert third.json()["code"] == "LOGIN_RATE_LIMITED"

    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        assert await _count_sessions(session) == 0
        audit_events = await _load_audit_events(session)
        assert len(audit_events) == 3
        assert all(event.event_type == "LOGIN_FAILED" for event in audit_events)


@pytest.mark.asyncio
async def test_login_must_change_password_limits_allowed_actions(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    session_factory = await _get_session_factory(app)
    async with session_factory() as session:
        organization = create_organization()
        user = create_user(organization_id=organization.id, must_change_password=True)
        session.add(organization)
        session.add(user)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"login_name": "admin", "password": "Password-123!"},
    )

    assert response.status_code == 200
    assert response.json()["allowed_actions"] == [
        "SESSION_READ",
        "LOGOUT",
        "PASSWORD_CHANGE",
    ]
