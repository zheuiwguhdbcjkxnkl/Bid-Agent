from __future__ import annotations

import pytest

from app.core.errors import DomainError
from app.documents.ir import DocumentIR
from app.documents.parsers.router import HybridDocumentParser


class RecordingParser:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[tuple[str, str, bytes]] = []

    async def parse(self, *, file_name: str, content_type: str, content: bytes) -> DocumentIR:
        self.calls.append((file_name, content_type, content))
        return DocumentIR(
            parser_name=self.name,
            parser_version="1",
            pages=[],
            segments=[],
        )


@pytest.mark.asyncio
async def test_hybrid_parser_routes_pdf_docx_and_xlsx_by_content_type() -> None:
    mineru = RecordingParser("mineru")
    docx = RecordingParser("python-docx")
    xlsx = RecordingParser("openpyxl")
    router = HybridDocumentParser(mineru=mineru, docx=docx, xlsx=xlsx)

    await router.parse(file_name="a.pdf", content_type="application/pdf", content=b"pdf")
    await router.parse(
        file_name="a.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content=b"docx",
    )
    await router.parse(
        file_name="a.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content=b"xlsx",
    )

    assert [len(parser.calls) for parser in (mineru, docx, xlsx)] == [1, 1, 1]


@pytest.mark.asyncio
async def test_hybrid_parser_rejects_unsupported_content_type() -> None:
    parser = RecordingParser("unused")
    router = HybridDocumentParser(mineru=parser, docx=parser, xlsx=parser)

    with pytest.raises(DomainError) as error:
        await router.parse(
            file_name="a.txt",
            content_type="text/plain",
            content=b"text",
        )
    assert error.value.code == "DOCUMENT_PARSE_UNSUPPORTED"
