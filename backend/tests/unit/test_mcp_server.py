from __future__ import annotations

import asyncio

from app.core.db import create_engine, create_session_factory
from app.documents.ingest_service import DocumentIngestService
from app.mcp.server import create_mcp_server
from app.projects.documents.storage import MemoryObjectStorage


def test_document_ingest_mcp_tool_requires_structured_request_envelope() -> None:
    engine = create_engine("postgresql+psycopg://test:test@localhost/test")
    session_factory = create_session_factory(engine)
    server = create_mcp_server(
        session_factory=session_factory,
        ingest_service_factory=lambda: DocumentIngestService(
            storage=MemoryObjectStorage(),
            now_provider=lambda: __import__("datetime").datetime.now(__import__("datetime").UTC),
        ),
        service_token="test-token",
    )

    tools = asyncio.run(server.list_tools())
    assert len(tools) == 1
    assert tools[0].name == "document.ingest"
    assert tools[0].input_schema["required"] == ["request"]
    assert tools[0].input_schema["properties"]["request"]["$ref"].endswith("DocumentIngestRequest")
