from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import BidProject
from app.db.models.workflow import TaskRun


async def load_task_project_context(
    session: AsyncSession,
    *,
    task_run_id: UUID,
) -> tuple[UUID, UUID] | None:
    row = (
        await session.execute(
            select(TaskRun.project_id, BidProject.organization_id)
            .join(BidProject, BidProject.id == TaskRun.project_id)
            .where(TaskRun.id == task_run_id)
        )
    ).one_or_none()
    if row is None:
        return None
    return row.project_id, row.organization_id


async def claim_document_parse_task(
    session: AsyncSession,
    *,
    task_run_id: UUID,
    started_at: datetime,
) -> TaskRun | None:
    statement = (
        update(TaskRun)
        .where(
            TaskRun.id == task_run_id,
            TaskRun.task_type == "DOCUMENT_PARSE",
            TaskRun.task_status.in_(("QUEUED", "DISPATCHED")),
        )
        .values(
            task_status="RUNNING",
            current_step="LOAD_SOURCE",
            progress_percent=1,
            started_at=started_at,
            heartbeat_at=started_at,
        )
        .returning(TaskRun)
    )
    result = await session.execute(statement)
    return result.scalar_one_or_none()
