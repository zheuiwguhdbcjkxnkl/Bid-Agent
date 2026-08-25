from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_db_session, require_business_access
from app.auth.service import AuthenticatedContext
from app.workflows import queries
from app.workflows.schemas import TaskRunItem, TaskRunListResponse, TaskStatus, TaskType

router = APIRouter(tags=["tasks"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"description": "统一错误响应"} for code in (401, 403, 404, 422, 500)
}

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
BusinessContext = Annotated[AuthenticatedContext, Depends(require_business_access)]


@router.get(
    "/task-runs/{task_run_id}",
    response_model=TaskRunItem,
    responses=_ERROR_RESPONSES,
)
async def get_task_run(
    task_run_id: UUID,
    session: DbSession,
    context: BusinessContext,
) -> TaskRunItem:
    return await queries.get_task_run(
        session,
        task_run_id=task_run_id,
        actor_user_id=context.user_id,
        organization_id=context.organization_id,
    )


@router.get(
    "/projects/{project_id}/task-runs",
    response_model=TaskRunListResponse,
    responses=_ERROR_RESPONSES,
)
async def list_project_task_runs(
    project_id: UUID,
    session: DbSession,
    context: BusinessContext,
    task_type: TaskType | None = None,
    task_status: TaskStatus | None = None,
) -> TaskRunListResponse:
    items = await queries.list_project_task_runs(
        session,
        project_id=project_id,
        actor_user_id=context.user_id,
        organization_id=context.organization_id,
        task_type=task_type,
        task_status=task_status,
    )
    return TaskRunListResponse(items=items)
