from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_db_session, require_business_access
from app.auth.service import AuthenticatedContext
from app.core.config import Settings
from app.main import create_app
from app.projects.documents.parse_service import DocumentParseService
from tests.factories import MutableClock, create_organization, create_user
from tests.integration.test_document_parse_api import RecordingDispatcher, _uploaded_version

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 8, 24, 14, 0, tzinfo=UTC)


async def test_task_run_detail_and_project_list_read_postgresql_facts(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, version_id = await _uploaded_version(migrated_database)
    dispatcher = RecordingDispatcher()
    service = DocumentParseService(
        dispatcher=dispatcher,
        now_provider=MutableClock(_NOW).now,
    )
    async with scenario.session_factory() as session:
        _, started = await service.start_parse(
            session,
            context=scenario.context,
            document_version_id=version_id,
            idempotency_key="task-query-1",
            request_id="req-task-query-1",
        )

    app = create_app(
        settings=Settings(
            app_env="test",
            database_url=migrated_database,
            allowed_origins=["http://frontend.localhost"],
        )
    )

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with scenario.session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[require_business_access] = lambda: scenario.context
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                detail = await client.get(f"/api/v1/task-runs/{started.task_run.id}")
                listed = await client.get(
                    f"/api/v1/projects/{scenario.project.id}/task-runs",
                    params={"task_type": "DOCUMENT_PARSE", "task_status": "QUEUED"},
                )
        assert detail.status_code == 200, detail.text
        assert detail.json()["id"] == str(started.task_run.id)
        assert detail.json()["task_status"] == "QUEUED"
        assert listed.status_code == 200, listed.text
        assert [item["id"] for item in listed.json()["items"]] == [str(started.task_run.id)]
    finally:
        await scenario.engine.dispose()


async def test_task_run_queries_reject_cross_organization_non_member(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, version_id = await _uploaded_version(migrated_database)
    service = DocumentParseService(
        dispatcher=RecordingDispatcher(),
        now_provider=MutableClock(_NOW).now,
    )
    async with scenario.session_factory() as session:
        _, started = await service.start_parse(
            session,
            context=scenario.context,
            document_version_id=version_id,
            idempotency_key="task-query-forbidden",
            request_id="req-task-query-forbidden",
        )
        other_organization = create_organization(tenant_key=f"task-other-{uuid4()}")
        other_user = create_user(
            organization_id=other_organization.id,
            login_name=f"task-other-{uuid4()}",
        )
        session.add_all([other_organization, other_user])
        await session.commit()
    other_context = AuthenticatedContext(
        session_id=uuid4(),
        user_id=other_user.id,
        organization_id=other_organization.id,
        system_role=other_user.system_role,
        must_change_password=False,
    )
    app = create_app(settings=Settings(app_env="test", database_url=migrated_database))

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with scenario.session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[require_business_access] = lambda: other_context
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                detail = await client.get(f"/api/v1/task-runs/{started.task_run.id}")
                listed = await client.get(f"/api/v1/projects/{scenario.project.id}/task-runs")
        assert detail.status_code == 403
        assert detail.json()["code"] == "FORBIDDEN"
        assert listed.status_code == 403
        assert listed.json()["code"] == "FORBIDDEN"
    finally:
        await scenario.engine.dispose()
