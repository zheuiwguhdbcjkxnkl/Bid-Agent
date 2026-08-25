from __future__ import annotations

from collections.abc import Callable
from secrets import compare_digest
from typing import Any, cast

from mcp.server import MCPServer
from mcp.server.mcpserver.context import Context
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import DomainError
from app.documents.ingest_service import DocumentIngestService
from app.mcp.schemas import DocumentIngestRequest, McpCallContext


def create_mcp_server(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    ingest_service_factory: Callable[[], DocumentIngestService],
    service_token: str,
) -> MCPServer:
    server = MCPServer("bid-tools-mcp")

    @server.tool(name="document.ingest", structured_output=True)
    async def document_ingest(
        request: DocumentIngestRequest,
        context: Context[Any, Any],
    ) -> dict[str, object]:
        headers = context.headers or {}
        provided_token = headers.get("x-internal-service-token", "")
        if not provided_token or not compare_digest(provided_token, service_token):
            raise DomainError(403, "MCP_SERVICE_FORBIDDEN", "内部 MCP 服务凭证无效")
        try:
            meta = cast(dict[str, object], context.request_context.meta or {})
            call_context = McpCallContext.model_validate(meta)
        except ValidationError as exc:
            raise DomainError(403, "MCP_CONTEXT_INVALID", "MCP 调用上下文无效") from exc
        async with session_factory() as session:
            await ingest_service_factory().ingest(
                session,
                context=call_context,
                request=request,
            )
        return {
            "task_run_id": str(request.task_run_id),
            "status": "SUCCEEDED",
        }

    return server
