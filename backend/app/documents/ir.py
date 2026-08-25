from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.projects.schemas import _StrictModel

SegmentType = Literal[
    "HEADING",
    "PARAGRAPH",
    "LIST",
    "TABLE",
    "TABLE_ROW",
    "FIGURE",
    "OTHER",
]


class DocumentIRPage(_StrictModel):
    page_no: int = Field(ge=1)
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)
    metadata_json: dict[str, Any] | None = None


class DocumentIRSegment(_StrictModel):
    segment_type: SegmentType
    page_no: int | None = Field(default=None, ge=1)
    section_path: str | None = None
    content_text: str = Field(min_length=1)
    source_hash: str = Field(min_length=64, max_length=64)
    source_bbox: dict[str, float] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    metadata_json: dict[str, Any] | None = None
    parent_index: int | None = Field(default=None, ge=0)


class DocumentIR(_StrictModel):
    parser_name: str
    parser_version: str
    model_version: str | None = None
    backend_mode: str | None = None
    pages: list[DocumentIRPage]
    segments: list[DocumentIRSegment]
