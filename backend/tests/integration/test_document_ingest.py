from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.errors import DomainError
from app.db.models.document import DocumentVersion
from app.documents.ingest_service import DocumentIngestService
from app.mcp.schemas import DocumentIngestRequest, McpCallContext
from app.projects.documents.parse_service import DocumentParseService
from app.projects.documents.storage import MemoryObjectStorage
from tests.factories import MutableClock
from tests.integration.test_document_parse_api import RecordingDispatcher, _uploaded_version
from tests.integration.test_project_documents import UploadScenario

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 8, 24, 16, 0, tzinfo=UTC)


async def _ingest_request(
    database_url: str,
) -> tuple[
    UploadScenario,
    MemoryObjectStorage,
    McpCallContext,
    DocumentIngestRequest,
    bytes,
]:
    scenario, version_id = await _uploaded_version(database_url)
    storage = MemoryObjectStorage()
    content = b"source-pdf"
    storage.objects[f"projects/source/{version_id}.pdf"] = content
    service = DocumentParseService(
        dispatcher=RecordingDispatcher(),
        now_provider=MutableClock(_NOW).now,
    )
    async with scenario.session_factory() as session:
        version = await session.get(DocumentVersion, version_id)
        assert version is not None
        version.storage_uri = f"memory://projects/source/{version_id}.pdf"
        await session.commit()
    async with scenario.session_factory() as session:
        _, started = await service.start_parse(
            session,
            context=scenario.context,
            document_version_id=version_id,
            idempotency_key="ingest-parse",
            request_id="req-ingest-parse",
        )
    context = McpCallContext(
        request_id="req-ingest",
        trace_id="trace-ingest",
        caller_type="CELERY_WORKER",
        organization_id=scenario.organization.id,
        project_id=scenario.project.id,
        user_id=scenario.actor.id,
        skill_id="document-ingest-worker",
        skill_version="1",
    )
    request = DocumentIngestRequest(
        task_run_id=started.task_run.id,
        document_version_id=version_id,
        task_type="DOCUMENT_PARSE",
        expected_content_hash=None,
    )
    return scenario, storage, context, request, content


async def test_document_ingest_reads_source_after_context_validation(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, storage, context, request, content = await _ingest_request(migrated_database)
    service = DocumentIngestService(storage=storage, now_provider=MutableClock(_NOW).now)
    try:
        async with scenario.session_factory() as session:
            source = await service.load_source(
                session,
                context=context,
                request=request,
            )
        assert source.content == content
        assert source.file_name == "bid.pdf"
        assert source.content_type == "application/pdf"
    finally:
        await scenario.engine.dispose()


@pytest.mark.parametrize(
    ("context_change", "request_change", "expected_code"),
    [
        ({"caller_type": "USER"}, {}, "MCP_CALLER_FORBIDDEN"),
        ({"organization_id": uuid4()}, {}, "MCP_RESOURCE_FORBIDDEN"),
        ({"project_id": uuid4()}, {}, "MCP_RESOURCE_FORBIDDEN"),
        ({}, {"task_type": "OCR"}, "MCP_TASK_TYPE_FORBIDDEN"),
    ],
)
async def test_document_ingest_rejects_invalid_context_and_task_type(
    clean_database: None,
    migrated_database: str,
    context_change: dict[str, object],
    request_change: dict[str, object],
    expected_code: str,
) -> None:
    scenario, storage, context, request, _ = await _ingest_request(migrated_database)
    service = DocumentIngestService(storage=storage, now_provider=MutableClock(_NOW).now)
    try:
        changed_context = context.model_copy(update=context_change)
        changed_request = request.model_copy(update=request_change)
        async with scenario.session_factory() as session:
            with pytest.raises(DomainError) as error:
                await service.load_source(
                    session,
                    context=changed_context,
                    request=changed_request,
                )
        assert error.value.code == expected_code
    finally:
        await scenario.engine.dispose()
