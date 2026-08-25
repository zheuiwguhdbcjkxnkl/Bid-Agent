from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_db_session, require_business_access
from app.core.config import Settings
from app.core.errors import DomainError
from app.db.models.audit import AuditEvent
from app.db.models.document import DocumentParse, DocumentVersion
from app.db.models.iam import IdempotencyRecord
from app.db.models.project import ProjectMember
from app.db.models.workflow import TaskRun
from app.main import create_app
from app.projects.documents.parse_service import DocumentParseService
from tests.factories import MutableClock
from tests.integration.test_project_documents import (
    TrackingStorage,
    UploadScenario,
    _create_upload_scenario,
    _upload,
)

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 8, 24, 13, 0, tzinfo=UTC)


class RecordingDispatcher:
    def __init__(self) -> None:
        self.task_ids: list[UUID] = []

    async def dispatch_document_parse(self, task_run_id: UUID) -> None:
        self.task_ids.append(task_run_id)


async def _uploaded_version(database_url: str) -> tuple[UploadScenario, UUID]:
    scenario = await _create_upload_scenario(database_url)
    _, item = await _upload(scenario, TrackingStorage())
    assert item.current_version_id is not None
    return scenario, item.current_version_id


async def test_start_document_parse_persists_transaction_and_dispatches_after_commit(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, version_id = await _uploaded_version(migrated_database)
    dispatcher = RecordingDispatcher()
    service = DocumentParseService(
        dispatcher=dispatcher,
        now_provider=MutableClock(_NOW).now,
    )
    try:
        async with scenario.session_factory() as session:
            status_code, response = await service.start_parse(
                session,
                context=scenario.context,
                document_version_id=version_id,
                idempotency_key="parse-1",
                request_id="req-parse-1",
            )

        assert status_code == 202
        assert response.task_run.document_version_id == version_id
        assert response.task_run.task_status == "QUEUED"
        assert dispatcher.task_ids == [response.task_run.id]

        async with scenario.session_factory() as session:
            version = await session.get(DocumentVersion, version_id)
            assert version is not None
            assert version.parse_status == "PARSING"
            assert await session.scalar(select(func.count(DocumentParse.id))) == 1
            assert await session.scalar(select(func.count(TaskRun.id))) == 1
            assert await session.scalar(select(func.count(IdempotencyRecord.id))) == 2
            audit = await session.scalar(
                select(AuditEvent).where(AuditEvent.event_type == "DOCUMENT_PARSE_QUEUED")
            )
            assert audit is not None
            assert audit.object_id == version_id
    finally:
        await scenario.engine.dispose()


async def test_start_document_parse_same_key_replays_without_second_dispatch(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, version_id = await _uploaded_version(migrated_database)
    dispatcher = RecordingDispatcher()
    service = DocumentParseService(
        dispatcher=dispatcher,
        now_provider=MutableClock(_NOW).now,
    )
    try:
        async with scenario.session_factory() as session:
            first = await service.start_parse(
                session,
                context=scenario.context,
                document_version_id=version_id,
                idempotency_key="same-parse-key",
                request_id="req-parse-first",
            )
        async with scenario.session_factory() as session:
            second = await service.start_parse(
                session,
                context=scenario.context,
                document_version_id=version_id,
                idempotency_key="same-parse-key",
                request_id="req-parse-second",
            )

        assert second == first
        assert dispatcher.task_ids == [first[1].task_run.id]
        async with scenario.session_factory() as session:
            assert await session.scalar(select(func.count(DocumentParse.id))) == 1
            assert await session.scalar(select(func.count(TaskRun.id))) == 1
            assert (
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.event_type == "DOCUMENT_PARSE_QUEUED"
                    )
                )
                == 1
            )
    finally:
        await scenario.engine.dispose()


class FailingDispatcher:
    async def dispatch_document_parse(self, task_run_id: UUID) -> None:
        del task_run_id
        raise RuntimeError("broker unavailable")


async def test_start_document_parse_keeps_accepted_task_when_dispatch_fails(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, version_id = await _uploaded_version(migrated_database)
    service = DocumentParseService(
        dispatcher=FailingDispatcher(),
        now_provider=MutableClock(_NOW).now,
    )
    try:
        async with scenario.session_factory() as session:
            status_code, response = await service.start_parse(
                session,
                context=scenario.context,
                document_version_id=version_id,
                idempotency_key="parse-dispatch-failure",
                request_id="req-parse-dispatch-failure",
            )
        assert status_code == 202
        async with scenario.session_factory() as session:
            task = await session.get(TaskRun, response.task_run.id)
            assert task is not None
            assert task.task_status == "QUEUED"
            assert task.celery_task_id is None
    finally:
        await scenario.engine.dispose()


async def test_start_document_parse_api_returns_accepted_task(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, version_id = await _uploaded_version(migrated_database)
    dispatcher = RecordingDispatcher()
    app = create_app(
        settings=Settings(
            app_env="test",
            database_url=migrated_database,
            allowed_origins=["http://frontend.localhost"],
        ),
        now_provider=MutableClock(_NOW).now,
        task_dispatcher=dispatcher,
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
                client.cookies.set("bid_csrf", "csrf-token")
                response = await client.post(
                    f"/api/v1/document-versions/{version_id}/parse",
                    headers={
                        "Origin": "http://frontend.localhost",
                        "X-CSRF-Token": "csrf-token",
                        "Idempotency-Key": "api-parse-1",
                    },
                )
        assert response.status_code == 202, response.text
        assert response.json()["task_run"]["document_version_id"] == str(version_id)
        assert response.json()["task_run"]["task_status"] == "QUEUED"
        assert dispatcher.task_ids == [UUID(response.json()["task_run"]["id"])]
    finally:
        await scenario.engine.dispose()


async def test_start_document_parse_rejects_non_manager_and_invalid_status(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, version_id = await _uploaded_version(migrated_database)
    service = DocumentParseService(
        dispatcher=RecordingDispatcher(),
        now_provider=MutableClock(_NOW).now,
    )
    try:
        async with scenario.session_factory() as session:
            await session.execute(
                update(ProjectMember)
                .where(
                    ProjectMember.project_id == scenario.project.id,
                    ProjectMember.user_id == scenario.actor.id,
                )
                .values(project_role="BID_WRITER")
            )
            await session.commit()
        async with scenario.session_factory() as session:
            with pytest.raises(DomainError) as forbidden:
                await service.start_parse(
                    session,
                    context=scenario.context,
                    document_version_id=version_id,
                    idempotency_key="parse-forbidden",
                    request_id="req-parse-forbidden",
                )
        assert forbidden.value.status_code == 403
        assert forbidden.value.code == "FORBIDDEN"

        async with scenario.session_factory() as session:
            await session.execute(
                update(ProjectMember)
                .where(
                    ProjectMember.project_id == scenario.project.id,
                    ProjectMember.user_id == scenario.actor.id,
                )
                .values(project_role="BID_MANAGER")
            )
            await session.execute(
                update(DocumentVersion)
                .where(DocumentVersion.id == version_id)
                .values(parse_status="PARSED")
            )
            await session.commit()
        async with scenario.session_factory() as session:
            with pytest.raises(DomainError) as conflict:
                await service.start_parse(
                    session,
                    context=scenario.context,
                    document_version_id=version_id,
                    idempotency_key="parse-conflict",
                    request_id="req-parse-conflict",
                )
        assert conflict.value.status_code == 409
        assert conflict.value.code == "DOCUMENT_PARSE_STATE_CONFLICT"
    finally:
        await scenario.engine.dispose()
