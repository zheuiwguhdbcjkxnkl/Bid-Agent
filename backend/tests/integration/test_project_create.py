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
from app.db.models.project import BidPackage, BidProject, ProjectMember
from app.main import create_app
from tests.factories import MutableClock, create_organization, create_user

TEST_DATABASE_URL = "postgresql+psycopg://bid_agent:bid_agent_test@localhost:55432/bid_agent_test"
VALID_ORIGIN = "http://frontend.localhost"
REQUEST_ID = "req-project-create-001"

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
    must_change_password: bool = False,
    account_status: str = "ACTIVE",
    organization_tenant_key: str = "yunqi",
) -> User:
    session_factory = app.state.session_factory
    async with session_factory() as session:
        organization = create_organization(tenant_key=organization_tenant_key)
        user = create_user(
            organization_id=organization.id,
            system_role=system_role,
            must_change_password=must_change_password,
            account_status=account_status,
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
    account_status: str = "ACTIVE",
) -> User:
    session_factory = app.state.session_factory
    async with session_factory() as session:
        user = create_user(
            organization_id=organization_id,
            login_name=login_name,
            system_role=system_role,
            account_status=account_status,
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
    idempotency_key: str | None = "project-create-key-001",
    origin: str | None = VALID_ORIGIN,
    csrf_token: str | None = None,
    payload_overrides: dict[str, Any] | None = None,
) -> httpx.Response:
    headers = {"X-Request-ID": REQUEST_ID}
    if origin is not None:
        headers["Origin"] = origin
    if csrf_token is not None:
        headers["X-CSRF-Token"] = csrf_token
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key

    payload = {
        "project_name": "滨江市政务云平台",
        "procurement_method": "PUBLIC_TENDER",
        "regime_type": "GOVERNMENT_PROCUREMENT",
        "deadline_at": "2026-09-01T10:00:00+08:00",
        "owner_user_id": owner_user_id,
    }
    if payload_overrides:
        payload.update(payload_overrides)
    return await client.post("/api/v1/projects", headers=headers, json=payload)


async def test_create_project_route_is_available_for_bid_manager(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    owner = await _seed_user(app)
    await _login(client, owner.login_name)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    response = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        csrf_token=csrf_token,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["project_name"] == "滨江市政务云平台"
    assert body["project_status"] == "DRAFT"
    assert body["owner_user_id"] == str(owner.id)
    assert body["project_code"] == "BID-2026-0001"

    session_factory = app.state.session_factory
    async with session_factory() as session:
        projects = list((await session.execute(select(BidProject))).scalars().all())
        packages = list((await session.execute(select(BidPackage))).scalars().all())
        members = list((await session.execute(select(ProjectMember))).scalars().all())
        idem_records = list((await session.execute(select(IdempotencyRecord))).scalars().all())
        audit_events = list((await session.execute(select(AuditEvent))).scalars().all())

    project_created_events = [
        event for event in audit_events if event.event_type == "PROJECT_CREATED"
    ]

    assert len(projects) == 1
    assert len(packages) == 1
    assert len(members) == 1
    assert len(idem_records) == 1
    assert len(project_created_events) == 1
    assert project_created_events[0].after_snapshot is not None
    assert project_created_events[0].after_snapshot["project_code"] == "BID-2026-0001"
    assert project_created_events[0].after_snapshot["project_status"] == "DRAFT"
    assert packages[0].package_code == "PKG-01"
    assert packages[0].package_status == "ACTIVE"
    assert packages[0].is_v1_primary is True
    assert members[0].user_id == owner.id
    assert members[0].project_role == "BID_MANAGER"
    assert idem_records[0].processing_status == "SUCCEEDED"


async def test_create_project_with_max_length_name_persists_complete_transaction(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    owner = await _seed_user(app)
    await _login(client, owner.login_name)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None
    project_name = "项" * 255

    response = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        csrf_token=csrf_token,
        idempotency_key="project-create-max-name",
        payload_overrides={"project_name": project_name},
    )

    assert response.status_code == 201
    assert response.json()["project_name"] == project_name

    session_factory = app.state.session_factory
    async with session_factory() as session:
        projects = list((await session.execute(select(BidProject))).scalars().all())
        packages = list((await session.execute(select(BidPackage))).scalars().all())
        members = list((await session.execute(select(ProjectMember))).scalars().all())
        idem_records = list((await session.execute(select(IdempotencyRecord))).scalars().all())
        audit_events = list((await session.execute(select(AuditEvent))).scalars().all())

    assert len(projects) == 1
    assert projects[0].project_name == project_name
    assert len(packages) == 1
    assert packages[0].package_name == f"{'项' * 252}主标包"
    assert len(packages[0].package_name) == 255
    assert len(members) == 1
    assert members[0].user_id == owner.id
    assert len(idem_records) == 1
    assert idem_records[0].processing_status == "SUCCEEDED"
    assert len([event for event in audit_events if event.event_type == "PROJECT_CREATED"]) == 1


async def test_create_project_checks_origin_before_authentication(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    owner = await _seed_user(app)

    response = await client.post(
        "/api/v1/projects",
        headers={
            "Origin": "http://evil.localhost",
            "X-Request-ID": REQUEST_ID,
            "Idempotency-Key": "origin-before-auth",
        },
        json={
            "project_name": "滨江市政务云平台",
            "procurement_method": "PUBLIC_TENDER",
            "regime_type": "GOVERNMENT_PROCUREMENT",
            "deadline_at": "2026-09-01T10:00:00+08:00",
            "owner_user_id": str(owner.id),
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "ORIGIN_NOT_ALLOWED"


async def test_create_project_checks_idempotency_before_body_validation(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    owner = await _seed_user(app)
    await _login(client, owner.login_name)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    response = await client.post(
        "/api/v1/projects",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": csrf_token,
            "X-Request-ID": REQUEST_ID,
        },
        json={
            "project_name": "滨江市政务云平台",
            "procurement_method": "PUBLIC_TENDER",
            "regime_type": "GOVERNMENT_PROCUREMENT",
            "deadline_at": "2026-09-01T10:00:00+08:00",
            "owner_user_id": str(owner.id),
            "source": "IMPORT",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


async def test_create_project_rejects_non_bid_manager_actor(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app, system_role="COMMERCIAL_WRITER")
    owner = await _seed_user_in_existing_organization(
        app,
        organization_id=actor.organization_id,
        login_name="owner",
    )
    await _login(client, actor.login_name)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    response = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        csrf_token=csrf_token,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_create_project_blocks_actor_who_must_change_password(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app, must_change_password=True)
    await _login(client, actor.login_name)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    response = await _post_create_project(
        client,
        owner_user_id=str(actor.id),
        csrf_token=csrf_token,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PASSWORD_CHANGE_REQUIRED"


async def test_create_project_rejects_cross_organization_owner(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app, organization_tenant_key="yunqi")
    owner = await _seed_user(app, organization_tenant_key="other-tenant")
    await _login(client, actor.login_name)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    response = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        csrf_token=csrf_token,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "OWNER_ORGANIZATION_MISMATCH"


async def test_create_project_rejects_owner_with_wrong_role(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    owner = await _seed_user_in_existing_organization(
        app,
        organization_id=actor.organization_id,
        login_name="writer",
        system_role="COMMERCIAL_WRITER",
    )
    await _login(client, actor.login_name)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    response = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        csrf_token=csrf_token,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "OWNER_ROLE_MISMATCH"


async def test_create_project_rejects_origin_violation(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    owner = await _seed_user(app)
    await _login(client, owner.login_name)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    response = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        origin="http://evil.localhost",
        csrf_token=csrf_token,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "ORIGIN_NOT_ALLOWED"


async def test_create_project_rejects_csrf_violation(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    owner = await _seed_user(app)
    await _login(client, owner.login_name)

    response = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        csrf_token="wrong-token",
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_VALIDATION_FAILED"


async def test_create_project_rejects_extra_source_field_with_validation_error(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    owner = await _seed_user(app)
    await _login(client, owner.login_name)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    response = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        csrf_token=csrf_token,
        payload_overrides={"source": "IMPORT"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


async def test_create_project_maps_malformed_json_to_validation_error(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    owner = await _seed_user(app)
    await _login(client, owner.login_name)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    response = await client.post(
        "/api/v1/projects",
        content=b"{",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": csrf_token,
            "X-Request-ID": REQUEST_ID,
            "Idempotency-Key": "malformed-json-001",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert set(body.keys()) == {"code", "message", "request_id", "details"}


async def test_create_project_failure_does_not_persist_idempotency_record(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None

    bad_response = await _post_create_project(
        client,
        owner_user_id="00000000-0000-0000-0000-000000000001",
        csrf_token=csrf_token,
        idempotency_key="same-key-after-failure",
    )

    assert bad_response.status_code == 422
    assert bad_response.json()["code"] == "OWNER_ROLE_MISMATCH"

    good_response = await _post_create_project(
        client,
        owner_user_id=str(actor.id),
        csrf_token=csrf_token,
        idempotency_key="same-key-after-failure",
    )

    assert good_response.status_code == 201

    session_factory = app.state.session_factory
    async with session_factory() as session:
        idem_records = list((await session.execute(select(IdempotencyRecord))).scalars().all())
    assert len(idem_records) == 1
