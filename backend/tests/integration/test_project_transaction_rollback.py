from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

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
from app.projects.service import NoOpProjectCreationHooks
from tests.factories import MutableClock, create_organization, create_user

TEST_DATABASE_URL = "postgresql+psycopg://bid_agent:bid_agent_test@localhost:55432/bid_agent_test"
VALID_ORIGIN = "http://frontend.localhost"
REQUEST_ID = "req-project-rollback-001"

pytestmark = pytest.mark.asyncio


class InjectedFailure(Exception):
    pass


class FailAtHook(NoOpProjectCreationHooks):
    def __init__(self, fail_at: str) -> None:
        self._fail_at = fail_at
        self._failed = False

    async def _maybe_fail(self, hook: str) -> None:
        if self._fail_at == hook and not self._failed:
            self._failed = True
            raise InjectedFailure

    async def after_project(self) -> None:
        await self._maybe_fail("project")

    async def after_package(self) -> None:
        await self._maybe_fail("package")

    async def after_member(self) -> None:
        await self._maybe_fail("member")

    async def after_audit(self) -> None:
        await self._maybe_fail("audit")


@pytest.fixture(params=["project", "package", "member", "audit"])
def fail_at(request: pytest.FixtureRequest) -> str:
    return cast(str, request.param)


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
async def failing_app_client(
    clean_database: None,
    migrated_database: str,
    auth_settings: Settings,
    mutable_clock: MutableClock,
    fail_at: str,
) -> Any:
    hooks = FailAtHook(fail_at)
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
        project_creation_hooks=hooks,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client, app


async def _seed_user(app: FastAPI) -> User:
    session_factory = app.state.session_factory
    async with session_factory() as session:
        organization = create_organization(tenant_key="yunqi")
        user = create_user(organization_id=organization.id, system_role="BID_MANAGER")
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


async def _post_create_project(
    client: httpx.AsyncClient,
    *,
    owner_user_id: str,
    idempotency_key: str,
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
            "project_name": "滨江市政务云平台",
            "procurement_method": "PUBLIC_TENDER",
            "regime_type": "GOVERNMENT_PROCUREMENT",
            "deadline_at": "2026-09-01T10:00:00+08:00",
            "owner_user_id": owner_user_id,
        },
    )


async def test_create_project_failure_rolls_back_all_facts_and_allows_retry(
    failing_app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = failing_app_client
    owner = await _seed_user(app)
    await _login(client, owner.login_name)

    failed = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        idempotency_key="rollback-key",
    )

    assert failed.status_code == 500
    assert failed.json()["code"] == "INTERNAL_ERROR"

    session_factory = app.state.session_factory
    async with session_factory() as session:
        projects = list((await session.execute(select(BidProject))).scalars().all())
        packages = list((await session.execute(select(BidPackage))).scalars().all())
        members = list((await session.execute(select(ProjectMember))).scalars().all())
        idem_records = list((await session.execute(select(IdempotencyRecord))).scalars().all())
        audit_events = list((await session.execute(select(AuditEvent))).scalars().all())

    assert len(projects) == 0
    assert len(packages) == 0
    assert len(members) == 0
    assert len(idem_records) == 0
    project_created_events = [
        event for event in audit_events if event.event_type == "PROJECT_CREATED"
    ]
    assert len(project_created_events) == 0

    retried = await _post_create_project(
        client,
        owner_user_id=str(owner.id),
        idempotency_key="rollback-key",
    )

    assert retried.status_code == 201

    async with session_factory() as session:
        projects = list((await session.execute(select(BidProject))).scalars().all())
        idem_records = list((await session.execute(select(IdempotencyRecord))).scalars().all())

    assert len(projects) == 1
    assert len(idem_records) == 1
