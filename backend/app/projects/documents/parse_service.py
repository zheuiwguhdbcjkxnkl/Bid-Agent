from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import append_audit_event
from app.auth.service import AuthenticatedContext
from app.core.errors import DomainError
from app.db.models.document import DocumentParse
from app.db.models.workflow import TaskRun
from app.projects.documents import parse_repository
from app.projects.documents.parse_schemas import StartDocumentParseResponse
from app.projects.idempotency import (
    build_document_parse_scope,
    claim_or_replay,
    compute_request_hash,
    mark_succeeded,
)
from app.workflows.dispatcher import TaskDispatcher
from app.workflows.schemas import TaskRunItem

_PARSER_NAME = "mineru-hybrid"
_PARSER_VERSION = "1"
_AUDIT_EVENT_TYPE = "DOCUMENT_PARSE_QUEUED"
_LOGGER = logging.getLogger(__name__)


class DocumentParseService:
    def __init__(
        self,
        *,
        dispatcher: TaskDispatcher,
        now_provider: Callable[[], datetime],
    ) -> None:
        self._dispatcher = dispatcher
        self._now_provider = now_provider

    async def start_parse(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedContext,
        document_version_id: UUID,
        idempotency_key: str,
        request_id: str,
    ) -> tuple[int, StartDocumentParseResponse]:
        now = self._now_provider().astimezone(UTC)
        scope = build_document_parse_scope(
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            document_version_id=document_version_id,
            key=idempotency_key,
        )
        request_hash = compute_request_hash(
            {
                "document_version_id": str(document_version_id),
                "parser_name": _PARSER_NAME,
                "parser_version": _PARSER_VERSION,
            }
        )
        task_run_id: UUID | None = None

        async with _transaction(session):
            loaded = await parse_repository.load_version_for_manager(
                session,
                document_version_id=document_version_id,
                actor_user_id=context.user_id,
                organization_id=context.organization_id,
            )
            if loaded is None:
                raise DomainError(403, "FORBIDDEN", "仅项目负责人可启动解析")
            version, document = loaded

            claimed = await claim_or_replay(session, scope=scope, request_hash=request_hash)
            if claimed.replay is not None:
                return claimed.replay.response_status, StartDocumentParseResponse.model_validate(
                    claimed.replay.response_body
                )

            if version.parse_status != "PENDING":
                raise DomainError(
                    409,
                    "DOCUMENT_PARSE_STATE_CONFLICT",
                    "当前文件版本状态不允许首次解析",
                )

            document_parse = DocumentParse(
                id=uuid4(),
                document_version_id=version.id,
                parser_name=_PARSER_NAME,
                parser_version=_PARSER_VERSION,
                backend_mode="SELF_HOSTED",
                parse_status="QUEUED",
                created_at=now,
            )
            task_run = TaskRun(
                id=uuid4(),
                project_id=document.project_id,
                document_version_id=version.id,
                document_parse_id=document_parse.id,
                task_type="DOCUMENT_PARSE",
                task_status="QUEUED",
                idempotency_key=idempotency_key,
                payload_refs={
                    "document_version_id": str(version.id),
                    "document_parse_id": str(document_parse.id),
                },
                progress_percent=0,
                retry_count=0,
                max_retries=3,
                queued_at=now,
            )
            version.parse_status = "PARSING"
            await parse_repository.create_parse_and_task(
                session,
                document_parse=document_parse,
                task_run=task_run,
            )
            item = _to_item(task_run)
            response = StartDocumentParseResponse(task_run=item)
            body = response.model_dump(mode="json")
            await append_audit_event(
                session,
                organization_id=context.organization_id,
                project_id=document.project_id,
                event_type=_AUDIT_EVENT_TYPE,
                object_type="DOCUMENT_VERSION",
                object_id=version.id,
                actor_user_id=context.user_id,
                request_id=request_id,
                occurred_at=now,
                after_snapshot=body,
            )
            mark_succeeded(
                claimed.record,
                status_code=202,
                body=body,
                resource_type="TASK_RUN",
                resource_id=task_run.id,
                completed_at=now,
            )
            task_run_id = task_run.id

        assert task_run_id is not None
        try:
            await self._dispatcher.dispatch_document_parse(task_run_id)
        except Exception:
            _LOGGER.exception(
                "解析任务发布失败，保留 QUEUED 等待补投",
                extra={"task_run_id": str(task_run_id)},
            )
        return 202, response


def _to_item(task: TaskRun) -> TaskRunItem:
    return TaskRunItem(
        id=task.id,
        project_id=task.project_id,
        document_version_id=task.document_version_id,
        document_parse_id=task.document_parse_id,
        task_type=task.task_type,
        task_status=task.task_status,
        current_step=task.current_step,
        progress_percent=task.progress_percent,
        queued_at=task.queued_at,
        dispatched_at=task.dispatched_at,
        started_at=task.started_at,
        heartbeat_at=task.heartbeat_at,
        finished_at=task.finished_at,
        last_error_code=task.last_error_code,
        last_error_message=task.last_error_message,
    )


@asynccontextmanager
async def _transaction(session: AsyncSession) -> AsyncIterator[None]:
    if session.in_transaction():
        async with session.begin_nested():
            yield
    else:
        async with session.begin():
            yield
