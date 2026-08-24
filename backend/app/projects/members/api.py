from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_db_session, require_business_access
from app.auth.service import AuthenticatedContext
from app.projects.members import queries
from app.projects.members.schemas import MemberListResponse

router = APIRouter(prefix="/projects/{project_id}/members", tags=["projects"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
BusinessContext = Annotated[AuthenticatedContext, Depends(require_business_access)]


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
