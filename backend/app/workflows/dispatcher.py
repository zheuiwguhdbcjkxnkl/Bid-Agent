from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import DomainError
from app.db.models.workflow import TaskRun


class TaskDispatcher(Protocol):
    async def dispatch_document_parse(self, task_run_id: UUID) -> None: ...


class TaskPublisher(Protocol):
    def publish_document_parse(self, task_run_id: UUID) -> str: ...


class UnconfiguredTaskDispatcher:
    async def dispatch_document_parse(self, task_run_id: UUID) -> None:
        del task_run_id
        raise DomainError(503, "TASK_DISPATCHER_NOT_CONFIGURED", "任务调度器未配置")


class CeleryTaskDispatcher:
    def __init__(
        self,
        *,
        publisher: TaskPublisher,
        session_factory: async_sessionmaker[AsyncSession],
        now_provider: Callable[[], datetime],
    ) -> None:
        self._publisher = publisher
        self._session_factory = session_factory
        self._now_provider = now_provider

    async def dispatch_document_parse(self, task_run_id: UUID) -> None:
        celery_task_id = self._publisher.publish_document_parse(task_run_id)
        dispatched_at = self._now_provider().astimezone(UTC)
        async with self._session_factory() as session, session.begin():
            task = await session.get(TaskRun, task_run_id, with_for_update=True)
            if task is None:
                raise DomainError(404, "TASK_RUN_NOT_FOUND", "任务不存在")
            if task.task_status != "QUEUED":
                return
            task.task_status = "DISPATCHED"
            task.celery_task_id = celery_task_id
            task.dispatched_at = dispatched_at
