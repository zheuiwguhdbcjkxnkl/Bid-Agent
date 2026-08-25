from __future__ import annotations

from typing import Protocol

from app.core.errors import DomainError
from app.documents.ir import DocumentIR
from app.documents.parsers.docx import parse_docx
from app.documents.parsers.xlsx import parse_xlsx

_PDF_TYPES = {"application/pdf", "image/png", "image/jpeg"}
_DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class AsyncDocumentParser(Protocol):
    async def parse(
        self,
        *,
        file_name: str,
        content_type: str,
        content: bytes,
    ) -> DocumentIR: ...


class DocxParser:
    async def parse(
        self,
        *,
        file_name: str,
        content_type: str,
        content: bytes,
    ) -> DocumentIR:
        del file_name, content_type
        return parse_docx(content)


class XlsxParser:
    async def parse(
        self,
        *,
        file_name: str,
        content_type: str,
        content: bytes,
    ) -> DocumentIR:
        del file_name, content_type
        return parse_xlsx(content)


class HybridDocumentParser:
    def __init__(
        self,
        *,
        mineru: AsyncDocumentParser,
        docx: AsyncDocumentParser,
        xlsx: AsyncDocumentParser,
    ) -> None:
        self._mineru = mineru
        self._docx = docx
        self._xlsx = xlsx

    async def parse(
        self,
        *,
        file_name: str,
        content_type: str,
        content: bytes,
    ) -> DocumentIR:
        if content_type in _PDF_TYPES:
            parser = self._mineru
        elif content_type == _DOCX_TYPE:
            parser = self._docx
        elif content_type == _XLSX_TYPE:
            parser = self._xlsx
        else:
            raise DomainError(422, "DOCUMENT_PARSE_UNSUPPORTED", "文件类型不支持解析")
        return await parser.parse(
            file_name=file_name,
            content_type=content_type,
            content=content,
        )
