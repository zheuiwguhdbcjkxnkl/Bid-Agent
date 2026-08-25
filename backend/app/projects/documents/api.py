from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_db_session, require_business_access
from app.auth.service import AuthenticatedContext
from app.core.csrf import assert_csrf_valid
from app.core.request_id import ensure_request_id
from app.projects.documents import queries
from app.projects.documents.schemas import DocumentItem, DocumentListResponse, DocumentType
from app.projects.documents.service import DocumentService
from app.projects.documents.storage import MAX_FILE_SIZE
from app.projects.idempotency import normalize_idempotency_key

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["projects"])

_DOCUMENT_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"description": "统一错误响应"} for code in (400, 401, 403, 404, 409, 422, 500)
}

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
BusinessContext = Annotated[AuthenticatedContext, Depends(require_business_access)]


@router.get("", response_model=DocumentListResponse, responses=_DOCUMENT_ERROR_RESPONSES)
async def list_project_documents(
    project_id: UUID,
    session: DbSession,
    context: BusinessContext,
) -> DocumentListResponse:
    items = await queries.list_documents(
        session, project_id=project_id, actor_user_id=context.user_id
    )
    return DocumentListResponse(items=items)


@router.post(
    "",
    response_model=DocumentItem,
    status_code=status.HTTP_201_CREATED,
    responses=_DOCUMENT_ERROR_RESPONSES,
)
async def upload_project_document(
    request: Request,
    response: Response,
    session: DbSession,
    context: BusinessContext,
    project_id: UUID,
    file: Annotated[UploadFile, File()],
    document_type: Annotated[DocumentType, Form()],
    display_name: Annotated[str, Form(min_length=1, max_length=255)],
    idempotency_header: str | None = Header(default=None, alias="Idempotency-Key"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> DocumentItem:
    assert_csrf_valid(
        request.cookies.get(request.app.state.settings.csrf_cookie_name),
        csrf_token,
    )
    idempotency_key = normalize_idempotency_key(idempotency_header)
    content = await file.read(MAX_FILE_SIZE + 1)
    service = DocumentService(
        storage=request.app.state.document_storage,
        now_provider=request.app.state.clock,
    )
    status_code, item = await service.upload_document(
        session,
        context=context,
        project_id=project_id,
        document_type=document_type,
        display_name=display_name,
        file_name=file.filename or "",
        content_type=file.content_type or "",
        content=content,
        idempotency_key=idempotency_key,
        request_id=ensure_request_id(request),
    )
    response.status_code = status_code
    return item
