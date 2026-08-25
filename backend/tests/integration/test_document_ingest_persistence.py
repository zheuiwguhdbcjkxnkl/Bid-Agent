from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.core.errors import DomainError
from app.db.models.document import DocumentPage, DocumentParse, DocumentSegment, DocumentVersion
from app.db.models.workflow import TaskRun
from app.documents.ingest_service import DocumentIngestService
from app.documents.ir import DocumentIR, DocumentIRPage, DocumentIRSegment
from tests.factories import MutableClock
from tests.integration.test_document_ingest import _ingest_request

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 8, 24, 17, 0, tzinfo=UTC)


class SuccessfulParser:
    async def parse(self, *, file_name: str, content_type: str, content: bytes) -> DocumentIR:
        assert file_name == "bid.pdf"
        assert content_type == "application/pdf"
        assert content == b"source-pdf"
        return DocumentIR(
            parser_name="mineru",
            parser_version="3.4.5",
            model_version="pipeline",
            backend_mode="pipeline",
            pages=[DocumentIRPage(page_no=1, width=595, height=842)],
            segments=[
                DocumentIRSegment(
                    segment_type="HEADING",
                    page_no=1,
                    section_path="第一章",
                    content_text="第一章 项目概况",
                    source_hash="a" * 64,
                    confidence=0.99,
                ),
                DocumentIRSegment(
                    segment_type="PARAGRAPH",
                    page_no=1,
                    section_path="第一章",
                    content_text="本项目建设统一平台。",
                    source_hash="b" * 64,
                    confidence=0.97,
                ),
            ],
        )


class FailingParser:
    async def parse(self, *, file_name: str, content_type: str, content: bytes) -> DocumentIR:
        del file_name, content_type, content
        raise DomainError(422, "DOCUMENT_PARSE_UNSUPPORTED", "文件无法可靠解析")


async def test_document_ingest_success_persists_ir_and_marks_terminal_states(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, storage, context, request, _ = await _ingest_request(migrated_database)
    service = DocumentIngestService(
        storage=storage,
        parser=SuccessfulParser(),
        now_provider=MutableClock(_NOW).now,
    )
    try:
        async with scenario.session_factory() as session:
            await service.ingest(session, context=context, request=request)

        async with scenario.session_factory() as session:
            task = await session.get(TaskRun, request.task_run_id)
            version = await session.get(DocumentVersion, request.document_version_id)
            parse = await session.get(DocumentParse, task.document_parse_id if task else None)
            assert task is not None
            assert version is not None
            assert parse is not None
            assert task.task_status == "SUCCEEDED"
            assert task.progress_percent == 100
            assert task.finished_at == _NOW
            assert task.result_refs == {"document_parse_id": str(parse.id), "segment_count": 2}
            assert version.parse_status == "PARSED"
            assert parse.parse_status == "SUCCEEDED"
            assert parse.started_at is not None
            assert parse.completed_at is not None
            assert parse.started_at <= parse.completed_at
            assert parse.parser_name == "mineru"
            assert await session.scalar(select(func.count(DocumentPage.id))) == 1
            assert await session.scalar(select(func.count(DocumentSegment.id))) == 2
    finally:
        await scenario.engine.dispose()


class UnexpectedFailingParser:
    async def parse(self, *, file_name: str, content_type: str, content: bytes) -> DocumentIR:
        del file_name, content_type, content
        raise RuntimeError("parser crashed with sensitive details")


async def test_document_ingest_unexpected_failure_persists_sanitized_terminal_state(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, storage, context, request, _ = await _ingest_request(migrated_database)
    service = DocumentIngestService(
        storage=storage,
        parser=UnexpectedFailingParser(),
        now_provider=MutableClock(_NOW).now,
    )
    try:
        with pytest.raises(RuntimeError, match="parser crashed"):
            async with scenario.session_factory() as session:
                await service.ingest(session, context=context, request=request)
        async with scenario.session_factory() as session:
            task = await session.get(TaskRun, request.task_run_id)
            parse = await session.get(DocumentParse, task.document_parse_id if task else None)
            assert task is not None
            assert parse is not None
            assert task.task_status == "FAILED"
            assert task.last_error_code == "DOCUMENT_PARSE_INTERNAL_ERROR"
            assert task.last_error_message == "文档解析发生内部错误"
            assert parse.parse_status == "FAILED"
            assert parse.error_message == "文档解析发生内部错误"
    finally:
        await scenario.engine.dispose()


async def test_document_ingest_failure_marks_failed_without_deleting_source_or_partial_ir(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario, storage, context, request, content = await _ingest_request(migrated_database)
    service = DocumentIngestService(
        storage=storage,
        parser=FailingParser(),
        now_provider=MutableClock(_NOW).now,
    )
    try:
        with pytest.raises(DomainError) as error:
            async with scenario.session_factory() as session:
                await service.ingest(session, context=context, request=request)
        assert error.value.code == "DOCUMENT_PARSE_UNSUPPORTED"
        assert (
            await storage.get(f"memory://projects/source/{request.document_version_id}.pdf")
            == content
        )

        async with scenario.session_factory() as session:
            task = await session.get(TaskRun, request.task_run_id)
            version = await session.get(DocumentVersion, request.document_version_id)
            parse = await session.get(DocumentParse, task.document_parse_id if task else None)
            assert task is not None
            assert version is not None
            assert parse is not None
            assert task.task_status == "FAILED"
            assert task.last_error_code == "DOCUMENT_PARSE_UNSUPPORTED"
            assert version.parse_status == "PARSE_FAILED"
            assert parse.parse_status == "FAILED"
            assert await session.scalar(select(func.count(DocumentPage.id))) == 0
            assert await session.scalar(select(func.count(DocumentSegment.id))) == 0
    finally:
        await scenario.engine.dispose()
