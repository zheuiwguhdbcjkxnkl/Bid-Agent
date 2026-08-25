from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_db_session, get_now_provider, require_business_access
from app.auth.service import AuthenticatedContext
from app.core.csrf import assert_csrf_valid
from app.core.request_id import ensure_request_id
from app.projects.idempotency import normalize_idempotency_key
from app.projects.members import queries
from app.projects.members.schemas import (
    AddMemberRequest,
    MemberItem,
    MemberListResponse,
    UpdateMemberRoleRequest,
)
from app.projects.members.service import MemberService

router = APIRouter(prefix="/projects/{project_id}/members", tags=["projects"])

_MEMBER_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"description": "统一错误响应"} for code in (400, 401, 403, 404, 409, 422, 500)
}

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
BusinessContext = Annotated[AuthenticatedContext, Depends(require_business_access)]
NowProvider = Annotated[Callable[[], datetime], Depends(get_now_provider)]


@router.get("", response_model=MemberListResponse)
async def list_members(
    session: DbSession,
    context: BusinessContext,
    project_id: UUID,
) -> MemberListResponse:
    items = await queries.list_members(
        session, project_id=project_id, actor_user_id=context.user_id
    )
    return MemberListResponse(items=items)


@router.post(
    "",
    response_model=MemberItem,
    status_code=status.HTTP_201_CREATED,
    responses=_MEMBER_ERROR_RESPONSES,
)
async def add_member(
    request: Request,
    response: Response,
    session: DbSession,
    now_provider: NowProvider,
    context: BusinessContext,
    project_id: UUID,
    payload: Annotated[AddMemberRequest, Body()],
    idempotency_header: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> MemberItem:
    idempotency_key = normalize_idempotency_key(idempotency_header)
    assert_csrf_valid(
        request.cookies.get(request.app.state.settings.csrf_cookie_name),
        csrf_token,
    )

    service = MemberService(now_provider=now_provider)
    status_code, item = await service.add_member(
        session,
        context=context,
        project_id=project_id,
        payload=payload,
        idempotency_key=idempotency_key,
        request_id=ensure_request_id(request),
    )
    response.status_code = status_code
    return item


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_MEMBER_ERROR_RESPONSES,
)
async def remove_member(
    request: Request,
    session: DbSession,
    now_provider: NowProvider,
    context: BusinessContext,
    project_id: UUID,
    user_id: UUID,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    assert_csrf_valid(
        request.cookies.get(request.app.state.settings.csrf_cookie_name),
        csrf_token,
    )
    service = MemberService(now_provider=now_provider)
    await service.remove_member(
        session,
        context=context,
        project_id=project_id,
        user_id=user_id,
        request_id=ensure_request_id(request),
    )


@router.patch(
    "/{user_id}",
    response_model=MemberItem,
    responses=_MEMBER_ERROR_RESPONSES,
)
async def update_member_role(
    request: Request,
    session: DbSession,
    now_provider: NowProvider,
    context: BusinessContext,
    project_id: UUID,
    user_id: UUID,
    payload: Annotated[UpdateMemberRoleRequest, Body()],
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> MemberItem:
    assert_csrf_valid(
        request.cookies.get(request.app.state.settings.csrf_cookie_name),
        csrf_token,
    )

    service = MemberService(now_provider=now_provider)
    return await service.update_role(
        session,
        context=context,
        project_id=project_id,
        user_id=user_id,
        project_role=payload.project_role.value,
        request_id=ensure_request_id(request),
    )
