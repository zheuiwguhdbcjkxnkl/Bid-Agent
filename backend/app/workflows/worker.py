from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.mcp.client import DocumentIngestClient
from app.mcp.schemas import DocumentIngestRequest, McpCallContext
from app.workflows.repository import claim_document_parse_task


async def process_document_parse_task(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    mcp_client: DocumentIngestClient,
    context: McpCallContext,
    task_run_id: UUID,
    started_at: datetime,
) -> bool:
    async with session_factory() as session:
        task = await claim_document_parse_task(
            session,
            task_run_id=task_run_id,
            started_at=started_at,
        )
        await session.commit()
    if task is None:
        return False
    if task.document_version_id is None:
        raise RuntimeError("DOCUMENT_PARSE 任务缺少 document_version_id")
    await mcp_client.ingest(
        context=context,
        request=DocumentIngestRequest(
            task_run_id=task.id,
            document_version_id=task.document_version_id,
            task_type=task.task_type,
            expected_content_hash=None,
        ),
    )
    return True
