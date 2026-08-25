from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any, Protocol, cast

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, RequestParamsMeta

from app.core.errors import DomainError
from app.mcp.schemas import DocumentIngestRequest, McpCallContext

_INTERNAL_TOKEN_HEADER = "X-Internal-Service-Token"


class DocumentIngestClient(Protocol):
    async def ingest(
        self,
        *,
        context: McpCallContext,
        request: DocumentIngestRequest,
    ) -> None: ...


class StreamableHttpMcpClient:
    def __init__(self, endpoint: str, *, service_token: str) -> None:
        self._endpoint = endpoint
        self._service_token = service_token

    async def ingest(
        self,
        *,
        context: McpCallContext,
        request: DocumentIngestRequest,
    ) -> None:
        async with AsyncExitStack() as stack:
            http_client = await stack.enter_async_context(
                httpx2.AsyncClient(headers={_INTERNAL_TOKEN_HEADER: self._service_token})
            )
            transport = streamable_http_client(
                self._endpoint,
                http_client=http_client,
            )
            streams = await stack.enter_async_context(transport)
            session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
            await session.initialize()
            result = await session.call_tool(
                "document.ingest",
                {"request": request.model_dump(mode="json")},
                meta=cast(RequestParamsMeta, context.model_dump(mode="json")),
            )
        if not isinstance(result, CallToolResult) or result.is_error:
            raise DomainError(502, "MCP_DOCUMENT_INGEST_FAILED", "内部 MCP 文档解析失败")


def extract_structured_content(result: Any) -> dict[str, object] | None:
    content = getattr(result, "structured_content", None)
    return content if isinstance(content, dict) else None
