from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.db.models.workflow import TaskRun
from app.mcp.schemas import DocumentIngestRequest, McpCallContext
from app.projects.documents.parse_service import DocumentParseService
from app.workflows.dispatcher import CeleryTaskDispatcher
from app.workflows.recovery import redeliver_stale_queued_tasks
from app.workflows.repository import claim_document_parse_task
from app.workflows.worker import process_document_parse_task
from tests.factories import MutableClock
from tests.integration.test_document_parse_api import RecordingDispatcher, _uploaded_version
from tests.integration.test_project_documents import UploadScenario

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 8, 24, 15, 0, tzinfo=UTC)


class FakeTaskPublisher:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.task_ids: list[UUID] = []

    def publish_document_parse(self, task_run_id: UUID) -> str:
        self.task_ids.append(task_run_id)
        if self.should_fail:
            raise RuntimeError("broker unavailable")
        return f"celery-{task_run_id}"


async def _queued_task(database_url: str) -> tuple[UploadScenario, UUID]:
    scenario, version_id = await _uploaded_version(database_url)
    service = DocumentParseService(
        dispatcher=RecordingDispatcher(),
        now_provider=MutableClock(_NOW).now,
    )
    async with scenario.session_factory() as session:
        _, response = await service.start_parse(
            session,
            context=scenario.context,
            document_version_id=version_id,
            idempotency_key=f"dispatch-{version_id}",
            request_id="req-dispatch",
        )
    return scenario, response.task_run.id


async def test_redelivery_dispatches_only_stale_queued_document_parse_tasks(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, task_run_id = await _queued_task(migrated_database)
    dispatcher = RecordingDispatcher()
    try:
        async with scenario.session_factory() as session:
            task = await session.get(TaskRun, task_run_id)
            assert task is not None
            task.queued_at = _NOW - timedelta(minutes=10)
            await session.commit()
        redelivered = await redeliver_stale_queued_tasks(
            session_factory=scenario.session_factory,
            dispatcher=dispatcher,
            queued_before=_NOW - timedelta(minutes=5),
            batch_size=10,
        )
        assert redelivered == 1
        assert dispatcher.task_ids == [task_run_id]

        redelivered_again = await redeliver_stale_queued_tasks(
            session_factory=scenario.session_factory,
            dispatcher=dispatcher,
            queued_before=_NOW + timedelta(minutes=1),
            batch_size=10,
        )
        assert redelivered_again == 1
        assert dispatcher.task_ids == [task_run_id, task_run_id]
    finally:
        await scenario.engine.dispose()


async def test_dispatcher_publishes_and_marks_task_dispatched(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, task_run_id = await _queued_task(migrated_database)
    publisher = FakeTaskPublisher()
    dispatcher = CeleryTaskDispatcher(
        publisher=publisher,
        session_factory=scenario.session_factory,
        now_provider=MutableClock(_NOW).now,
    )
    try:
        await dispatcher.dispatch_document_parse(task_run_id)
        assert publisher.task_ids == [task_run_id]
        async with scenario.session_factory() as session:
            task = await session.get(TaskRun, task_run_id)
            assert task is not None
            assert task.task_status == "DISPATCHED"
            assert task.celery_task_id == f"celery-{task_run_id}"
            assert task.dispatched_at == _NOW
    finally:
        await scenario.engine.dispose()


async def test_dispatch_failure_keeps_task_queued(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, task_run_id = await _queued_task(migrated_database)
    dispatcher = CeleryTaskDispatcher(
        publisher=FakeTaskPublisher(should_fail=True),
        session_factory=scenario.session_factory,
        now_provider=MutableClock(_NOW).now,
    )
    try:
        with pytest.raises(RuntimeError, match="broker unavailable"):
            await dispatcher.dispatch_document_parse(task_run_id)
        async with scenario.session_factory() as session:
            task = await session.get(TaskRun, task_run_id)
            assert task is not None
            assert task.task_status == "QUEUED"
            assert task.celery_task_id is None
            assert task.dispatched_at is None
    finally:
        await scenario.engine.dispose()


class RecordingMcpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[McpCallContext, DocumentIngestRequest]] = []

    async def ingest(
        self,
        *,
        context: McpCallContext,
        request: DocumentIngestRequest,
    ) -> None:
        self.calls.append((context, request))


async def test_worker_process_calls_mcp_once_after_claim(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, task_run_id = await _queued_task(migrated_database)
    client = RecordingMcpClient()
    context = McpCallContext(
        request_id="worker-request",
        trace_id="worker-trace",
        caller_type="CELERY_WORKER",
        organization_id=scenario.organization.id,
        project_id=scenario.project.id,
        user_id=scenario.actor.id,
        skill_id="document-ingest-worker",
        skill_version="1",
    )
    try:
        first = await process_document_parse_task(
            session_factory=scenario.session_factory,
            mcp_client=client,
            context=context,
            task_run_id=task_run_id,
            started_at=_NOW,
        )
        second = await process_document_parse_task(
            session_factory=scenario.session_factory,
            mcp_client=client,
            context=context,
            task_run_id=task_run_id,
            started_at=_NOW,
        )
        assert first is True
        assert second is False
        assert len(client.calls) == 1
        assert client.calls[0][1].task_run_id == task_run_id
        assert client.calls[0][1].task_type == "DOCUMENT_PARSE"
    finally:
        await scenario.engine.dispose()


async def test_worker_claims_task_once_and_terminal_redelivery_is_noop(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, task_run_id = await _queued_task(migrated_database)
    try:
        async with scenario.session_factory() as session:
            first = await claim_document_parse_task(
                session,
                task_run_id=task_run_id,
                started_at=_NOW,
            )
            await session.commit()
        assert first is not None
        assert first.task_status == "RUNNING"

        async with scenario.session_factory() as session:
            second = await claim_document_parse_task(
                session,
                task_run_id=task_run_id,
                started_at=_NOW,
            )
            await session.commit()
        assert second is None

        async with scenario.session_factory() as session:
            task = await session.get(TaskRun, task_run_id)
            assert task is not None
            task.task_status = "SUCCEEDED"
            task.finished_at = _NOW
            await session.commit()
        async with scenario.session_factory() as session:
            terminal = await claim_document_parse_task(
                session,
                task_run_id=task_run_id,
                started_at=_NOW,
            )
        assert terminal is None
    finally:
        await scenario.engine.dispose()
