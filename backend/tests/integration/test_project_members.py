from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import anyio
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.core.config import Settings
from app.core.errors import DomainError
from app.core.rate_limit import FallbackLoginRateLimiter, InMemoryFailureStore
from app.db.models.audit import AuditEvent
from app.db.models.iam import User
from app.db.models.project import BidProject, ProjectMember
from app.main import create_app
from app.projects.members import repository
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


@pytest.fixture()
async def concurrent_app_clients(
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
    app = create_app(settings=auth_settings, rate_limiter=limiter, now_provider=mutable_clock.now)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with (
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as first,
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as second,
        ):
            yield first, second, app


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


def _csrf_token(client: httpx.AsyncClient) -> str:
    token = client.cookies.get("bid_csrf")
    assert token is not None
    return token


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


async def _add_member(
    client: httpx.AsyncClient,
    *,
    project_id: str,
    user_id: str,
    project_role: str,
    idempotency_key: str,
) -> httpx.Response:
    csrf_token = client.cookies.get("bid_csrf")
    assert csrf_token is not None
    return await client.post(
        f"/api/v1/projects/{project_id}/members",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": csrf_token,
            "Idempotency-Key": idempotency_key,
            "X-Request-ID": REQUEST_ID,
        },
        json={"user_id": user_id, "project_role": project_role},
    )


async def test_add_member_success(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)

    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="add-member-1"
    )
    project_id = created.json()["id"]

    writer = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="writer-1",
        display_name="标书编写人",
    )

    response = await _add_member(
        client,
        project_id=project_id,
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="add-member-1-key",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == str(writer.id)
    assert body["project_role"] == "BID_WRITER"
    assert body["display_name"] == "标书编写人"


async def test_add_member_requires_manager(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)

    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="add-member-2"
    )
    project_id = created.json()["id"]

    writer = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="writer-2",
    )
    await _add_member(
        client,
        project_id=project_id,
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="add-member-2-seed",
    )

    await client.post(
        "/api/v1/auth/logout",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
    )
    await _login(client, writer.login_name)

    other = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="TECHNICAL_WRITER",
        login_name="tech-2",
    )
    response = await _add_member(
        client,
        project_id=project_id,
        user_id=str(other.id),
        project_role="TECHNICAL_WRITER",
        idempotency_key="add-member-2-key",
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_add_member_rejects_role_mismatch(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)

    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="add-member-3"
    )
    project_id = created.json()["id"]

    technical = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="TECHNICAL_WRITER",
        login_name="tech-3",
    )
    response = await _add_member(
        client,
        project_id=project_id,
        user_id=str(technical.id),
        project_role="BID_WRITER",
        idempotency_key="add-member-3-key",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "MEMBER_ROLE_MISMATCH"


async def test_add_member_idempotency_isolated_by_project(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)

    first_project = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="add-member-project-1"
    )
    second_project = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="add-member-project-2"
    )
    first_project_id = first_project.json()["id"]
    second_project_id = second_project.json()["id"]

    writer = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="writer-project-scope",
    )

    first = await _add_member(
        client,
        project_id=first_project_id,
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="same-member-key",
    )
    second = await _add_member(
        client,
        project_id=second_project_id,
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="same-member-key",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    listing = await client.get(
        f"/api/v1/projects/{second_project_id}/members",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
    )
    assert {item["user_id"] for item in listing.json()["items"]} == {
        str(actor.id),
        str(writer.id),
    }


async def test_add_member_concurrent_different_keys_returns_conflict(
    app_client: tuple[httpx.AsyncClient, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, app = app_client
    actor = await _seed_user(app)
    writer = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="concurrent-writer",
    )
    project = BidProject(
        organization_id=actor.organization_id,
        project_code="CONCURRENT-MEMBER",
        project_name="并发成员项目",
        procurement_method="PUBLIC_TENDER",
        regime_type="GOVERNMENT_PROCUREMENT",
    )
    session_factory = app.state.session_factory
    async with session_factory() as session:
        session.add(project)
        await session.commit()
        project_id = project.id

    original_load_member = repository.load_member
    entered = 0
    both_entered = anyio.Event()

    async def synchronized_load_member(*args: Any, **kwargs: Any) -> ProjectMember | None:
        nonlocal entered
        entered += 1
        if entered == 2:
            both_entered.set()
        await both_entered.wait()
        return await original_load_member(*args, **kwargs)

    monkeypatch.setattr(repository, "load_member", synchronized_load_member)

    async def add_member_in_session() -> str:
        async with session_factory() as session:
            try:
                await repository.activate_member(
                    session,
                    project_id=project_id,
                    user_id=writer.id,
                    project_role="BID_WRITER",
                    assigned_at=datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
                )
                await session.commit()
                return "created"
            except DomainError as exc:
                await session.rollback()
                assert exc.status_code == 409
                assert exc.code == "MEMBER_ALREADY_EXISTS"
                return "conflict"

    async def submit(results: list[str]) -> None:
        results.append(await add_member_in_session())

    results: list[str] = []
    async with anyio.create_task_group() as task_group:
        task_group.start_soon(submit, results)
        task_group.start_soon(submit, results)

    assert sorted(results) == ["conflict", "created"]


async def test_add_member_idempotent_replay(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)

    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="add-member-4"
    )
    project_id = created.json()["id"]

    writer = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="writer-4",
    )

    first = await _add_member(
        client,
        project_id=project_id,
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="replay-key",
    )
    assert first.status_code == 201

    second = await _add_member(
        client,
        project_id=project_id,
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="replay-key",
    )
    assert second.status_code == 201
    assert second.json() == first.json()


async def test_remove_member_success(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)
    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="remove-1"
    )
    project_id = created.json()["id"]
    writer = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="writer-rm-1",
    )
    added = await _add_member(
        client,
        project_id=project_id,
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="remove-1-add",
    )
    assert added.status_code == 201

    response = await client.delete(
        f"/api/v1/projects/{project_id}/members/{writer.id}",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": _csrf_token(client),
            "X-Request-ID": REQUEST_ID,
        },
    )

    assert response.status_code == 204


async def test_update_member_role_success(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)
    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="role-1"
    )
    project_id = created.json()["id"]
    writer = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="writer-role-1",
    )
    added = await _add_member(
        client,
        project_id=project_id,
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="role-1-add",
    )
    assert added.status_code == 201

    response = await client.patch(
        f"/api/v1/projects/{project_id}/members/{writer.id}",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": _csrf_token(client),
            "X-Request-ID": REQUEST_ID,
        },
        json={"project_role": "PRICING_OWNER"},
    )

    assert response.status_code == 200
    assert response.json()["project_role"] == "PRICING_OWNER"


async def test_remove_manager_rejected(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)
    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="remove-manager"
    )

    response = await client.delete(
        f"/api/v1/projects/{created.json()['id']}/members/{actor.id}",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": _csrf_token(client),
            "X-Request-ID": REQUEST_ID,
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_remove_member_is_idempotent_and_audited(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)
    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="remove-idempotent"
    )
    project_id = created.json()["id"]
    writer = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="writer-rm-idempotent",
    )
    added = await _add_member(
        client,
        project_id=project_id,
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="remove-idempotent-add",
    )
    assert added.status_code == 201
    headers = {
        "Origin": VALID_ORIGIN,
        "X-CSRF-Token": _csrf_token(client),
        "X-Request-ID": REQUEST_ID,
    }
    first = await client.delete(
        f"/api/v1/projects/{project_id}/members/{writer.id}", headers=headers
    )
    second = await client.delete(
        f"/api/v1/projects/{project_id}/members/{writer.id}", headers=headers
    )
    assert first.status_code == 204
    assert second.status_code == 204
    listing = await client.get(
        f"/api/v1/projects/{project_id}/members",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
    )
    assert [item["user_id"] for item in listing.json()["items"]] == [str(actor.id)]
    async with app.state.session_factory() as session:
        events = list((await session.execute(select(AuditEvent))).scalars().all())
    assert [event.event_type for event in events].count("MEMBER_REMOVED") == 1


async def test_update_member_role_rejects_mismatch_and_removed(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)
    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="role-invalid"
    )
    project_id = created.json()["id"]
    technical = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="TECHNICAL_WRITER",
        login_name="writer-role-invalid",
    )
    added = await _add_member(
        client,
        project_id=project_id,
        user_id=str(technical.id),
        project_role="TECHNICAL_WRITER",
        idempotency_key="role-invalid-add",
    )
    assert added.status_code == 201
    response = await client.patch(
        f"/api/v1/projects/{project_id}/members/{technical.id}",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": _csrf_token(client),
            "X-Request-ID": REQUEST_ID,
        },
        json={"project_role": "BID_WRITER"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "MEMBER_ROLE_MISMATCH"
    removed = await client.delete(
        f"/api/v1/projects/{project_id}/members/{technical.id}",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": _csrf_token(client),
            "X-Request-ID": REQUEST_ID,
        },
    )
    assert removed.status_code == 204
    response = await client.patch(
        f"/api/v1/projects/{project_id}/members/{technical.id}",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": _csrf_token(client),
            "X-Request-ID": REQUEST_ID,
        },
        json={"project_role": "TECHNICAL_WRITER"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "MEMBER_NOT_FOUND"


async def test_update_manager_role_rejected(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)
    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="role-manager-rejected"
    )

    response = await client.patch(
        f"/api/v1/projects/{created.json()['id']}/members/{actor.id}",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": _csrf_token(client),
            "X-Request-ID": REQUEST_ID,
        },
        json={"project_role": "BID_WRITER"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_add_active_member_with_different_key_returns_conflict(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)
    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="active-member-conflict"
    )
    writer = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="writer-active-conflict",
    )

    first = await _add_member(
        client,
        project_id=created.json()["id"],
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="active-member-key-1",
    )
    second = await _add_member(
        client,
        project_id=created.json()["id"],
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="active-member-key-2",
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "MEMBER_ALREADY_EXISTS"


async def test_add_member_same_key_with_different_body_returns_idempotency_conflict(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)
    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="idempotency-body-conflict"
    )
    writer = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="writer-idempotency-body",
    )

    first = await _add_member(
        client,
        project_id=created.json()["id"],
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="same-member-body-key",
    )
    second = await _add_member(
        client,
        project_id=created.json()["id"],
        user_id=str(writer.id),
        project_role="PRICING_OWNER",
        idempotency_key="same-member-body-key",
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "IDEMPOTENCY_CONFLICT"


async def test_remove_and_readd_member_restores_active_with_updated_role_and_listing(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)
    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="readd-member"
    )
    project_id = created.json()["id"]
    writer = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="writer-readd",
    )
    added = await _add_member(
        client,
        project_id=project_id,
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="readd-member-first",
    )
    assert added.status_code == 201
    removed = await client.delete(
        f"/api/v1/projects/{project_id}/members/{writer.id}",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": _csrf_token(client),
            "X-Request-ID": REQUEST_ID,
        },
    )
    assert removed.status_code == 204

    readded = await _add_member(
        client,
        project_id=project_id,
        user_id=str(writer.id),
        project_role="PRICING_OWNER",
        idempotency_key="readd-member-second",
    )
    listing = await client.get(
        f"/api/v1/projects/{project_id}/members",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
    )

    assert readded.status_code == 201
    assert readded.json()["project_role"] == "PRICING_OWNER"
    assert {item["user_id"] for item in listing.json()["items"]} == {
        str(actor.id),
        str(writer.id),
    }
    listing_by_user_id = {item["user_id"]: item for item in listing.json()["items"]}
    assert listing_by_user_id[str(writer.id)]["project_role"] == "PRICING_OWNER"


async def test_update_member_role_audit_records_snapshots_actor_and_project(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)
    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="role-audit"
    )
    project_id = created.json()["id"]
    writer = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="writer-role-audit",
    )
    added = await _add_member(
        client,
        project_id=project_id,
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="role-audit-add",
    )
    assert added.status_code == 201

    response = await client.patch(
        f"/api/v1/projects/{project_id}/members/{writer.id}",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": _csrf_token(client),
            "X-Request-ID": REQUEST_ID,
        },
        json={"project_role": "PRICING_OWNER"},
    )
    assert response.status_code == 200

    async with app.state.session_factory() as session:
        events = list((await session.execute(select(AuditEvent))).scalars().all())
    role_events = [event for event in events if event.event_type == "MEMBER_ROLE_CHANGED"]
    assert len(role_events) == 1
    event = role_events[0]
    assert event.before_snapshot == {"project_role": "BID_WRITER"}
    assert event.after_snapshot == {"project_role": "PRICING_OWNER"}
    assert event.actor_user_id == actor.id
    assert event.project_id == UUID(created.json()["id"])


async def test_update_member_role_requires_csrf(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)
    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="role-csrf"
    )
    writer = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="writer-role-csrf",
    )
    added = await _add_member(
        client,
        project_id=created.json()["id"],
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="role-csrf-add",
    )
    assert added.status_code == 201

    response = await client.patch(
        f"/api/v1/projects/{created.json()['id']}/members/{writer.id}",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
        json={"project_role": "PRICING_OWNER"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_VALIDATION_FAILED"


async def test_non_member_cannot_access_member_list(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app, login_name="manager-non-member")
    await _login(client, actor.login_name)
    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="non-member-project"
    )
    outsider = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="outsider-non-member",
    )
    await client.post(
        "/api/v1/auth/logout",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
    )
    await _login(client, outsider.login_name)

    response = await client.get(
        f"/api/v1/projects/{created.json()['id']}/members",
        headers={"Origin": VALID_ORIGIN, "X-Request-ID": REQUEST_ID},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_add_and_readd_member_audit_records_scope_actor_and_object(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app, login_name="manager-audit-add")
    await _login(client, actor.login_name)
    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="audit-add-project"
    )
    project_id = UUID(created.json()["id"])
    writer = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="writer-audit-add",
    )

    first = await _add_member(
        client,
        project_id=str(project_id),
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="audit-add-first",
    )
    assert first.status_code == 201
    removed = await client.delete(
        f"/api/v1/projects/{project_id}/members/{writer.id}",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": _csrf_token(client),
            "X-Request-ID": REQUEST_ID,
        },
    )
    assert removed.status_code == 204
    second = await _add_member(
        client,
        project_id=str(project_id),
        user_id=str(writer.id),
        project_role="PRICING_OWNER",
        idempotency_key="audit-add-second",
    )
    assert second.status_code == 201

    async with app.state.session_factory() as session:
        events = list((await session.execute(select(AuditEvent))).scalars().all())
    added_events = [event for event in events if event.event_type == "MEMBER_ADDED"]
    assert len(added_events) == 2
    for event in added_events:
        assert event.organization_id == actor.organization_id
        assert event.project_id == project_id
        assert event.actor_user_id == actor.id
        assert event.object_type == "PROJECT_MEMBER"
        assert event.object_id == writer.id


async def test_update_same_role_succeeds_without_role_change_audit(
    app_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    actor = await _seed_user(app)
    await _login(client, actor.login_name)
    created = await _post_create_project(
        client, owner_user_id=str(actor.id), idempotency_key="role-same"
    )
    project_id = created.json()["id"]
    writer = await _seed_user_in_organization(
        app,
        organization_id=actor.organization_id,
        system_role="COMMERCIAL_WRITER",
        login_name="writer-role-same",
    )
    added = await _add_member(
        client,
        project_id=project_id,
        user_id=str(writer.id),
        project_role="BID_WRITER",
        idempotency_key="role-same-add",
    )
    assert added.status_code == 201
    response = await client.patch(
        f"/api/v1/projects/{project_id}/members/{writer.id}",
        headers={
            "Origin": VALID_ORIGIN,
            "X-CSRF-Token": _csrf_token(client),
            "X-Request-ID": REQUEST_ID,
        },
        json={"project_role": "BID_WRITER"},
    )
    assert response.status_code == 200
    assert response.json()["project_role"] == "BID_WRITER"
    async with app.state.session_factory() as session:
        events = list((await session.execute(select(AuditEvent))).scalars().all())
    assert all(event.event_type != "MEMBER_ROLE_CHANGED" for event in events)
