from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.db.models.document import DocumentParse, DocumentVersion, ProcurementDocument
from app.db.models.project import BidProject
from app.db.models.workflow import TaskRun
from app.documents import repository
from app.documents.ir import DocumentIR
from app.mcp.schemas import DocumentIngestRequest, DocumentSource, McpCallContext
from app.projects.documents.storage import ObjectStorage


class DocumentParser(Protocol):
    async def parse(
        self,
        *,
        file_name: str,
        content_type: str,
        content: bytes,
    ) -> DocumentIR: ...


class DocumentIngestService:
    def __init__(
        self,
        *,
        storage: ObjectStorage,
        now_provider: Callable[[], datetime],
        parser: DocumentParser | None = None,
    ) -> None:
        self._storage = storage
        self._now_provider = now_provider
        self._parser = parser

    async def load_source(
        self,
        session: AsyncSession,
        *,
        context: McpCallContext,
        request: DocumentIngestRequest,
    ) -> DocumentSource:
        row = await self._load_bound_resources(session, context=context, request=request)
        task, version, _ = row
        content = await self._storage.get(version.storage_uri)
        if content is None:
            raise DomainError(404, "DOCUMENT_OBJECT_NOT_FOUND", "原始文件对象不存在")
        assert task.document_parse_id is not None
        return DocumentSource(
            task_run_id=task.id,
            document_version_id=version.id,
            document_parse_id=task.document_parse_id,
            file_name=version.file_name,
            content_type=version.content_type,
            content_hash=version.content_hash,
            content=content,
        )

    async def ingest(
        self,
        session: AsyncSession,
        *,
        context: McpCallContext,
        request: DocumentIngestRequest,
    ) -> None:
        if self._parser is None:
            raise DomainError(500, "DOCUMENT_PARSER_NOT_CONFIGURED", "文档解析器未配置")
        source = await self.load_source(session, context=context, request=request)
        try:
            ir = await self._parser.parse(
                file_name=source.file_name,
                content_type=source.content_type,
                content=source.content,
            )
        except DomainError as exc:
            await self._persist_failure_after_exception(
                session,
                context=context,
                request=request,
                error_code=exc.code,
                error_message=exc.message,
            )
            raise
        except Exception:
            await self._persist_failure_after_exception(
                session,
                context=context,
                request=request,
                error_code="DOCUMENT_PARSE_INTERNAL_ERROR",
                error_message="文档解析发生内部错误",
            )
            raise

        await session.rollback()
        async with session.begin():
            task, version, document_parse = await self._load_bound_resources(
                session,
                context=context,
                request=request,
                for_update=True,
            )
            await repository.persist_success(
                session,
                task=task,
                version=version,
                document_parse=document_parse,
                ir=ir,
                finished_at=self._now_provider().astimezone(UTC),
            )

    async def _persist_failure_after_exception(
        self,
        session: AsyncSession,
        *,
        context: McpCallContext,
        request: DocumentIngestRequest,
        error_code: str,
        error_message: str,
    ) -> None:
        await session.rollback()
        async with session.begin():
            task, version, document_parse = await self._load_bound_resources(
                session,
                context=context,
                request=request,
                for_update=True,
            )
            await repository.persist_failure(
                session,
                task=task,
                version=version,
                document_parse=document_parse,
                error_code=error_code,
                error_message=error_message,
                finished_at=self._now_provider().astimezone(UTC),
            )

    async def _load_bound_resources(
        self,
        session: AsyncSession,
        *,
        context: McpCallContext,
        request: DocumentIngestRequest,
        for_update: bool = False,
    ) -> tuple[TaskRun, DocumentVersion, DocumentParse]:
        if context.caller_type != "CELERY_WORKER":
            raise DomainError(403, "MCP_CALLER_FORBIDDEN", "调用主体无权执行文档解析")
        if request.task_type != "DOCUMENT_PARSE":
            raise DomainError(403, "MCP_TASK_TYPE_FORBIDDEN", "任务类型无权调用文档解析")
        statement = (
            select(TaskRun, DocumentVersion, DocumentParse)
            .join(DocumentVersion, DocumentVersion.id == TaskRun.document_version_id)
            .join(
                ProcurementDocument,
                ProcurementDocument.id == DocumentVersion.document_id,
            )
            .join(BidProject, BidProject.id == ProcurementDocument.project_id)
            .join(DocumentParse, DocumentParse.id == TaskRun.document_parse_id)
            .where(
                TaskRun.id == request.task_run_id,
                TaskRun.task_type == "DOCUMENT_PARSE",
                TaskRun.document_version_id == request.document_version_id,
                ProcurementDocument.project_id == context.project_id,
                BidProject.organization_id == context.organization_id,
            )
        )
        if for_update:
            statement = statement.with_for_update()
        row = (await session.execute(statement)).one_or_none()
        if row is None:
            raise DomainError(403, "MCP_RESOURCE_FORBIDDEN", "任务或文档资源不属于调用上下文")
        task, version, document_parse = row
        if (
            request.expected_content_hash is not None
            and request.expected_content_hash != version.content_hash
        ):
            raise DomainError(409, "DOCUMENT_VERSION_CONFLICT", "文件版本内容已变化")
        return task, version, document_parse
