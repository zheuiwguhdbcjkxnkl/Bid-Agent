from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.core.db import create_engine, create_session_factory
from app.mcp.client import StreamableHttpMcpClient
from app.mcp.schemas import McpCallContext
from app.workflows.celery_app import (
    DOCUMENT_PARSE_REDELIVERY_TASK_NAME,
    DOCUMENT_PARSE_TASK_NAME,
    create_celery_app,
)
from app.workflows.dispatcher import CeleryTaskDispatcher
from app.workflows.publisher import CeleryTaskPublisher
from app.workflows.recovery import redeliver_stale_queued_tasks
from app.workflows.repository import load_task_project_context
from app.workflows.worker import process_document_parse_task

settings = get_settings()
if settings.redis_url is None:
    raise RuntimeError("Celery Worker 需要配置 redis_url")
if settings.mcp_service_token is None:
    raise RuntimeError("Celery Worker 需要通过 Secret 配置 mcp_service_token")
mcp_service_token = settings.mcp_service_token

celery_app = create_celery_app(settings.redis_url)


@celery_app.task(name=DOCUMENT_PARSE_TASK_NAME)  # type: ignore[untyped-decorator]
def run_document_parse(task_run_id: str) -> None:
    asyncio.run(_process_task(UUID(task_run_id)))


@celery_app.task(name=DOCUMENT_PARSE_REDELIVERY_TASK_NAME)  # type: ignore[untyped-decorator]
def redeliver_document_parse() -> None:
    asyncio.run(_redeliver_tasks())


async def _redeliver_tasks() -> None:
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        await redeliver_stale_queued_tasks(
            session_factory=session_factory,
            dispatcher=CeleryTaskDispatcher(
                publisher=CeleryTaskPublisher(celery_app),
                session_factory=session_factory,
                now_provider=lambda: datetime.now(UTC),
            ),
            queued_before=datetime.now(UTC) - timedelta(minutes=5),
            batch_size=100,
        )
    finally:
        await engine.dispose()


async def _process_task(task_run_id: UUID) -> None:
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            project_context = await load_task_project_context(
                session,
                task_run_id=task_run_id,
            )
        if project_context is None:
            return
        project_id, organization_id = project_context
        request_id = str(uuid4())
        await process_document_parse_task(
            session_factory=session_factory,
            mcp_client=StreamableHttpMcpClient(
                settings.mcp_endpoint,
                service_token=mcp_service_token,
            ),
            context=McpCallContext(
                request_id=request_id,
                trace_id=request_id,
                caller_type="CELERY_WORKER",
                organization_id=organization_id,
                project_id=project_id,
                skill_id="document-ingest-worker",
                skill_version="1",
            ),
            task_run_id=task_run_id,
            started_at=datetime.now(UTC),
        )
    finally:
        await engine.dispose()
