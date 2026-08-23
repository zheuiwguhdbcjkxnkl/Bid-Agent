from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.core.rate_limit import FallbackLoginRateLimiter, InMemoryFailureStore
from app.db.models.iam import User
from app.db.models.project import BidPackage, BidProject, ProjectMember
from app.main import create_app
from tests.factories import MutableClock, create_organization, create_user

TEST_DATABASE_URL = "postgresql+psycopg://bid_agent:bid_agent_test@localhost:55432/bid_agent_test"
VALID_ORIGIN = "http://frontend.localhost"
REQUEST_ID = "req-workbench-001"

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
    tenant_key: str = "yunqi",
    login_name: str = "admin",
    display_name: str = "管理员",
) -> User:
    session_factory = app.state.session_factory
    async with session_factory() as session:
        organization = create_organization(tenant_key=tenant_key)
        user = create_user(
            organization_id=organization.id,
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
    login_name: str,
) -> User:
    session_factory = app.state.session_factory
    async with session_factory() as session:
        user = create_user(organization_id=organization_id, login_name=login_name)
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


async def _insert_project(
    app: FastAPI,
    *,
    organization_id: Any,
    project_code: str,
    owner_user_id: Any,
    project_name: str,
    updated_at: datetime | None = None,
) -> BidProject:
    session_factory = app.state.session_factory
    async with session_factory() as session:
        project = BidProject(
            id=uuid4(),
            organization_id=organization_id,
            project_code=project_code,
            project_name=project_name,
            procurement_method="PUBLIC_TENDER",
            regime_type="GOVERNMENT_PROCUREMENT",
            project_status="DRAFT",
            deadline_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
        )
        if updated_at is not None:
            project.updated_at = updated_at
        session.add(project)
        await session.flush()

        package = BidPackage(
            id=uuid4(),
            project_id=project.id,
            package_code="PKG-01",
            package_name=f"{project_name}主标包",
            package_status="ACTIVE",
            is_v1_primary=True,
        )
        session.add(package)

        member = ProjectMember(
            project_id=project.id,
            user_id=owner_user_id,
            project_role="BID_MANAGER",
            assignment_status="ACTIVE",
            assigned_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
        )
        session.add(member)
        await session.commit()
        return project


async def test_workbench_returns_only_member_projects_and_empty_collections(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)

    created = await _post_create_project(
        client,
        owner_user_id=str(actor.id),
        idempotency_key="workbench-member-key",
        project_name="成员项目",
    )
    assert created.status_code == 201

    same_org_owner = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        login_name="same-org-owner",
    )
    await _insert_project(
        app,
        organization_id=actor.organization_id,
        project_code="BID-2026-0099",
        owner_user_id=same_org_owner.id,
        project_name="同组织非成员项目",
    )

    cross_org_owner = await _seed_user(app, tenant_key="other-tenant", login_name="cross-org-owner")
    await _insert_project(
        app,
        organization_id=cross_org_owner.organization_id,
        project_code="BID-2026-0088",
        owner_user_id=cross_org_owner.id,
        project_name="跨组织项目",
    )

    response = await client.get(
        "/api/v1/me/workbench",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["personal_todos"] == []
    assert body["running_tasks"] == []
    assert body["failed_tasks"] == []
    assert len(body["recent_projects"]) == 1
    assert body["recent_projects"][0]["project_name"] == "成员项目"
    assert body["recent_projects"][0]["owner_user_id"] == str(actor.id)


async def test_workbench_limits_recent_projects_to_five_most_recent(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)

    base = datetime(2026, 8, 21, 10, 0, tzinfo=UTC)
    for index in range(6):
        await _insert_project(
            app,
            organization_id=actor.organization_id,
            project_code=f"BID-2026-{index:04d}",
            owner_user_id=actor.id,
            project_name=f"项目{index}",
            updated_at=base + timedelta(hours=index),
        )

    response = await client.get(
        "/api/v1/me/workbench",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
    )

    assert response.status_code == 200
    recent = response.json()["recent_projects"]
    assert len(recent) == 5
    assert [item["project_name"] for item in recent] == [
        "项目5",
        "项目4",
        "项目3",
        "项目2",
        "项目1",
    ]
