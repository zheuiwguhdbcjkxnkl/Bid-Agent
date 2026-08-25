from __future__ import annotations

import hashlib
from io import BytesIO

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.core.errors import DomainError
from app.documents.ir import DocumentIR, DocumentIRSegment


def parse_docx(content: bytes) -> DocumentIR:
    try:
        document = Document(BytesIO(content))
    except Exception as exc:
        raise DomainError(422, "DOCX_PARSE_FAILED", "DOCX 文件无法解析") from exc

    segments: list[DocumentIRSegment] = []
    current_section: str | None = None
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue
            style_name = block.style.name if block.style is not None else ""
            metadata: dict[str, object] | None
            if style_name.startswith("Heading"):
                segment_type = "HEADING"
                current_section = text
                metadata = {"style": style_name}
            elif style_name.startswith("List"):
                segment_type = "LIST"
                metadata = {"style": style_name}
            else:
                segment_type = "PARAGRAPH"
                metadata = {"style": style_name} if style_name else None
            segments.append(
                DocumentIRSegment(
                    segment_type=segment_type,
                    section_path=current_section,
                    content_text=text,
                    source_hash=_hash(text),
                    metadata_json=metadata,
                )
            )
        elif isinstance(block, Table):
            rows = [[cell.text.strip() for cell in row.cells] for row in block.rows]
            text = "\n".join("\t".join(row) for row in rows).strip()
            if not text:
                continue
            column_count = max((len(row) for row in rows), default=0)
            segments.append(
                DocumentIRSegment(
                    segment_type="TABLE",
                    section_path=current_section,
                    content_text=text,
                    source_hash=_hash(text),
                    metadata_json={"rows": len(rows), "columns": column_count},
                )
            )
    if not segments:
        raise DomainError(422, "DOCX_PARSE_EMPTY", "DOCX 文件没有可解析内容")
    return DocumentIR(
        parser_name="python-docx",
        parser_version="1.2.0",
        backend_mode="native",
        pages=[],
        segments=segments,
    )


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
