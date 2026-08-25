from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.core.config import get_settings
from app.core.db import create_engine, create_session_factory
from app.documents.ingest_service import DocumentIngestService
from app.documents.parsers.mineru import HttpMineruProvider
from app.documents.parsers.router import DocxParser, HybridDocumentParser, XlsxParser
from app.mcp.server import create_mcp_server
from app.projects.documents.storage_factory import build_object_storage

settings = get_settings()
if settings.mcp_service_token is None:
    raise RuntimeError("MCP Server 需要通过 Secret 配置 mcp_service_token")

engine = create_engine(settings.database_url)
session_factory = create_session_factory(engine)
storage = build_object_storage(settings)
mineru_client = httpx.AsyncClient()


def _build_ingest_service() -> DocumentIngestService:
    parser = HybridDocumentParser(
        mineru=HttpMineruProvider(
            base_url=settings.mineru_endpoint,
            client=mineru_client,
            timeout_seconds=1800,
        ),
        docx=DocxParser(),
        xlsx=XlsxParser(),
    )
    return DocumentIngestService(
        storage=storage,
        parser=parser,
        now_provider=lambda: datetime.now(UTC),
    )


mcp_server = create_mcp_server(
    session_factory=session_factory,
    ingest_service_factory=_build_ingest_service,
    service_token=settings.mcp_service_token,
)


def main() -> None:
    mcp_server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
