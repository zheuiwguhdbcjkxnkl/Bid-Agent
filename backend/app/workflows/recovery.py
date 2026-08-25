from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.workflow import TaskRun
from app.workflows.dispatcher import TaskDispatcher


async def redeliver_stale_queued_tasks(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    dispatcher: TaskDispatcher,
    queued_before: datetime,
    batch_size: int,
) -> int:
    async with session_factory() as session:
        task_ids = (
            await session.scalars(
                select(TaskRun.id)
                .where(
                    TaskRun.task_type == "DOCUMENT_PARSE",
                    TaskRun.task_status == "QUEUED",
                    TaskRun.dispatched_at.is_(None),
                    TaskRun.queued_at <= queued_before,
                )
                .order_by(TaskRun.queued_at.asc())
                .limit(batch_size)
            )
        ).all()
    redelivered = 0
    for task_id in task_ids:
        try:
            await dispatcher.dispatch_document_parse(task_id)
        except Exception:
            continue
        redelivered += 1
    return redelivered
