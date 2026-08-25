from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import append_audit_event
from app.auth.service import AuthenticatedContext
from app.core.errors import DomainError
from app.projects.documents import repository
from app.projects.documents.schemas import DocumentItem, DocumentType, DocumentVersionItem
from app.projects.documents.storage import (
    ObjectStorage,
    build_object_key,
    calculate_sha256,
    validate_upload_metadata,
)
from app.projects.idempotency import (
    build_document_upload_scope,
    claim_or_replay,
    compute_request_hash,
    mark_succeeded,
)

_AUDIT_EVENT_TYPE = "DOCUMENT_UPLOADED"
_AUDIT_OBJECT_TYPE = "PROCUREMENT_DOCUMENT"
_RESOURCE_TYPE = "PROCUREMENT_DOCUMENT"
_DOCUMENT_VERSION_EXISTS = "DOCUMENT_VERSION_EXISTS"
_DOCUMENT_VERSION_CONSTRAINTS = {
    "uq_document_version_hash",
    "uq_document_version_no",
}
_LOGGER = logging.getLogger(__name__)


class DocumentService:
    def __init__(
        self,
        *,
        storage: ObjectStorage,
        now_provider: Callable[[], datetime],
    ) -> None:
        self._storage = storage
        self._now_provider = now_provider

    async def upload_document(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedContext,
        project_id: UUID,
        document_type: DocumentType,
        display_name: str,
        file_name: str,
        content_type: str,
        content: bytes,
        idempotency_key: str,
        request_id: str,
    ) -> tuple[int, DocumentItem]:
        validate_upload_metadata(
            file_name=file_name,
            content_type=content_type,
            content=content,
        )
        now = self._now_provider().astimezone(UTC)
        content_hash = calculate_sha256(content)
        request_hash = compute_request_hash(
            {
                "document_type": document_type.value,
                "display_name": display_name,
                "file_name": file_name,
                "content_type": content_type,
                "content_hash": content_hash,
            }
        )
        scope = build_document_upload_scope(
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            project_id=project_id,
            key=idempotency_key,
        )
        storage_uri: str | None = None

        try:
            async with _transaction(session):
                manager = await repository.load_active_manager(
                    session,
                    project_id=project_id,
                    actor_user_id=context.user_id,
                    organization_id=context.organization_id,
                )
                if manager is None:
                    raise DomainError(403, "FORBIDDEN", "仅项目负责人可上传文件")

                claimed = await claim_or_replay(session, scope=scope, request_hash=request_hash)
                if claimed.replay is not None:
                    return claimed.replay.response_status, DocumentItem.model_validate(
                        claimed.replay.response_body
                    )

                if await repository.content_hash_exists(
                    session,
                    project_id=project_id,
                    content_hash=content_hash,
                ):
                    raise DomainError(409, _DOCUMENT_VERSION_EXISTS, "相同文件内容已存在")

                document_id = uuid4()
                version_id = uuid4()
                object_key = build_object_key(
                    project_id=project_id,
                    document_id=version_id,
                    file_name=file_name,
                )
                storage_uri = await self._storage.put(object_key=object_key, content=content)

                try:
                    document, version = await repository.create_document_with_version(
                        session,
                        document_id=document_id,
                        version_id=version_id,
                        project_id=project_id,
                        document_type=document_type.value,
                        display_name=display_name,
                        file_name=file_name,
                        content_type=content_type,
                        file_size=len(content),
                        content_hash=content_hash,
                        storage_uri=storage_uri,
                        uploaded_at=now,
                    )
                except IntegrityError as exc:
                    if _extract_constraint_name(exc) in _DOCUMENT_VERSION_CONSTRAINTS:
                        raise DomainError(
                            409,
                            _DOCUMENT_VERSION_EXISTS,
                            "相同文件内容已存在",
                        ) from exc
                    raise

                item = DocumentItem(
                    id=document.id,
                    document_type=document.document_type,
                    display_name=document.display_name,
                    document_status=document.document_status,
                    current_version_id=document.current_version_id,
                    versions=[
                        DocumentVersionItem(
                            id=version.id,
                            version_no=version.version_no,
                            file_name=version.file_name,
                            content_type=version.content_type,
                            file_size=version.file_size,
                            content_hash=version.content_hash,
                            storage_uri=version.storage_uri,
                            parse_status=version.parse_status,
                            uploaded_at=version.uploaded_at,
                        )
                    ],
                )
                response_body = item.model_dump(mode="json")

                await append_audit_event(
                    session,
                    organization_id=context.organization_id,
                    project_id=project_id,
                    event_type=_AUDIT_EVENT_TYPE,
                    object_type=_AUDIT_OBJECT_TYPE,
                    object_id=document.id,
                    actor_user_id=context.user_id,
                    request_id=request_id,
                    occurred_at=now,
                    after_snapshot=response_body,
                )
                mark_succeeded(
                    claimed.record,
                    status_code=201,
                    body=response_body,
                    resource_type=_RESOURCE_TYPE,
                    resource_id=document.id,
                    completed_at=now,
                )
                return 201, item
        except Exception as exc:
            if storage_uri is not None:
                try:
                    await self._storage.delete(storage_uri)
                except Exception:
                    _LOGGER.exception("文件上传补偿删除失败", extra={"storage_uri": storage_uri})
            raise exc


@asynccontextmanager
async def _transaction(session: AsyncSession) -> AsyncIterator[None]:
    if session.in_transaction():
        async with session.begin_nested():
            yield
    else:
        async with session.begin():
            yield


def _extract_constraint_name(error: IntegrityError) -> str | None:
    original_error = getattr(error, "orig", None)
    diag = getattr(original_error, "diag", None)
    return getattr(diag, "constraint_name", None)
