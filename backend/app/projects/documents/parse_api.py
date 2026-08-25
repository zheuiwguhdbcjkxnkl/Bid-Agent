from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_db_session, require_business_access
from app.auth.service import AuthenticatedContext
from app.core.csrf import assert_csrf_valid
from app.core.request_id import ensure_request_id
from app.projects.documents.parse_schemas import StartDocumentParseResponse
from app.projects.documents.parse_service import DocumentParseService
from app.projects.idempotency import normalize_idempotency_key

router = APIRouter(prefix="/document-versions", tags=["documents"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"description": "统一错误响应"} for code in (400, 401, 403, 404, 409, 422, 500)
}

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
BusinessContext = Annotated[AuthenticatedContext, Depends(require_business_access)]


@router.post(
    "/{document_version_id}/parse",
    response_model=StartDocumentParseResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERROR_RESPONSES,
)
async def start_document_parse(
    request: Request,
    document_version_id: UUID,
    session: DbSession,
    context: BusinessContext,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> StartDocumentParseResponse:
    assert_csrf_valid(
        request.cookies.get(request.app.state.settings.csrf_cookie_name),
        csrf_token,
    )
    service = DocumentParseService(
        dispatcher=request.app.state.task_dispatcher,
        now_provider=request.app.state.clock,
    )
    _, response = await service.start_parse(
        session,
        context=context,
        document_version_id=document_version_id,
        idempotency_key=normalize_idempotency_key(idempotency_key),
        request_id=ensure_request_id(request),
    )
    return response
