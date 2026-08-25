from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.db.models.iam import User
from app.db.models.project import BidProject, ProjectMember
from app.db.models.workflow import TaskRun
from app.workflows.schemas import TaskRunItem, TaskStatus, TaskType

_ACTIVE = "ACTIVE"


async def _require_project_access(
    session: AsyncSession,
    *,
    project_id: UUID,
    actor_user_id: UUID,
    organization_id: UUID,
) -> None:
    member = await session.scalar(
        select(ProjectMember)
        .join(BidProject, BidProject.id == ProjectMember.project_id)
        .join(User, User.id == ProjectMember.user_id)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == actor_user_id,
            ProjectMember.assignment_status == _ACTIVE,
            BidProject.organization_id == organization_id,
            User.organization_id == organization_id,
            User.account_status == _ACTIVE,
        )
    )
    if member is None:
        raise DomainError(403, "FORBIDDEN", "无项目任务访问权限")


async def get_task_run(
    session: AsyncSession,
    *,
    task_run_id: UUID,
    actor_user_id: UUID,
    organization_id: UUID,
) -> TaskRunItem:
    task = await session.get(TaskRun, task_run_id)
    if task is None:
        raise DomainError(404, "TASK_RUN_NOT_FOUND", "任务不存在")
    await _require_project_access(
        session,
        project_id=task.project_id,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
    )
    return _to_item(task)


async def list_project_task_runs(
    session: AsyncSession,
    *,
    project_id: UUID,
    actor_user_id: UUID,
    organization_id: UUID,
    task_type: TaskType | None,
    task_status: TaskStatus | None,
) -> list[TaskRunItem]:
    await _require_project_access(
        session,
        project_id=project_id,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
    )
    statement = select(TaskRun).where(TaskRun.project_id == project_id)
    if task_type is not None:
        statement = statement.where(TaskRun.task_type == task_type.value)
    if task_status is not None:
        statement = statement.where(TaskRun.task_status == task_status.value)
    tasks = (await session.scalars(statement.order_by(TaskRun.queued_at.desc()))).all()
    return [_to_item(task) for task in tasks]


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
