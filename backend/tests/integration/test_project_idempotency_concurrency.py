from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import anyio
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
REQUEST_ID = "req-project-concurrency-001"

pytestmark = pytest.mark.asyncio


class PauseAfterClaimHook(NoOpProjectCreationHooks):
    def __init__(self) -> None:
        self.first_claimed = anyio.Event()
        self.release_first = anyio.Event()
        self._claimed = False

    async def after_claim(self) -> None:
        if not self._claimed:
            self._claimed = True
            self.first_claimed.set()
            await self.release_first.wait()


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


@asynccontextmanager
async def _build_clients(
    hooks: NoOpProjectCreationHooks,
    auth_settings: Settings,
    mutable_clock: MutableClock,
) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient, httpx.AsyncClient]]:
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
        async with (
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as c1,
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as c2,
        ):
            yield app, c1, c2


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
            "deadline_at": "2026-09-01T10:00:00+08:00",
            "owner_user_id": owner_user_id,
        },
    )


async def test_concurrent_same_key_same_payload_creates_once(
    clean_database: None,
    migrated_database: str,
    auth_settings: Settings,
    mutable_clock: MutableClock,
) -> None:
    hooks = PauseAfterClaimHook()
    async with _build_clients(hooks, auth_settings, mutable_clock) as (app, c1, c2):
        owner = await _seed_user(app)
        await _login(c1, owner.login_name)
        await _login(c2, owner.login_name)

        results: list[httpx.Response] = []

        async def submit(client: httpx.AsyncClient) -> None:
            response = await _post_create_project(
                client,
                owner_user_id=str(owner.id),
                idempotency_key="concurrent-same-key",
            )
            results.append(response)

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(submit, c1)
            await hooks.first_claimed.wait()
            task_group.start_soon(submit, c2)
            hooks.release_first.set()

        assert len(results) == 2
        first, second = results
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json() == second.json()

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


async def test_concurrent_same_key_different_payload_creates_once(
    clean_database: None,
    migrated_database: str,
    auth_settings: Settings,
    mutable_clock: MutableClock,
) -> None:
    hooks = PauseAfterClaimHook()
    async with _build_clients(hooks, auth_settings, mutable_clock) as (app, c1, c2):
        owner = await _seed_user(app)
        await _login(c1, owner.login_name)
        await _login(c2, owner.login_name)

        results: list[httpx.Response] = []

        async def submit_first(client: httpx.AsyncClient) -> None:
            response = await _post_create_project(
                client,
                owner_user_id=str(owner.id),
                idempotency_key="concurrent-conflict-key",
                project_name="项目A",
            )
            results.append(response)

        async def submit_second(client: httpx.AsyncClient) -> None:
            response = await _post_create_project(
                client,
                owner_user_id=str(owner.id),
                idempotency_key="concurrent-conflict-key",
                project_name="项目B",
            )
            results.append(response)

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(submit_first, c1)
            await hooks.first_claimed.wait()
            task_group.start_soon(submit_second, c2)
            hooks.release_first.set()

        assert len(results) == 2
        statuses = sorted(response.status_code for response in results)
        assert statuses == [201, 409]

        conflict = next(response for response in results if response.status_code == 409)
        assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"

        session_factory = app.state.session_factory
        async with session_factory() as session:
            projects = list((await session.execute(select(BidProject))).scalars().all())
            idem_records = list((await session.execute(select(IdempotencyRecord))).scalars().all())

        assert len(projects) == 1
        assert len(idem_records) == 1
