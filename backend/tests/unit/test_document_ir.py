from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.documents.ir import DocumentIR, DocumentIRPage, DocumentIRSegment


def test_document_ir_accepts_pages_segments_and_source_locations() -> None:
    ir = DocumentIR(
        parser_name="mineru",
        parser_version="3.4.5",
        model_version="pipeline",
        backend_mode="pipeline",
        pages=[DocumentIRPage(page_no=1, width=595.0, height=842.0)],
        segments=[
            DocumentIRSegment(
                segment_type="HEADING",
                page_no=1,
                section_path="第一章",
                content_text="第一章 项目概况",
                source_hash="a" * 64,
                source_bbox={"x0": 10.0, "y0": 20.0, "x1": 300.0, "y1": 50.0},
                confidence=0.99,
                metadata_json={"heading_level": 1},
            )
        ],
    )

    assert ir.pages[0].page_no == 1
    assert ir.segments[0].segment_type == "HEADING"


def test_document_ir_rejects_invalid_page_confidence_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        DocumentIRPage.model_validate({"page_no": 0})
    with pytest.raises(ValidationError):
        DocumentIRSegment.model_validate(
            {
                "segment_type": "PARAGRAPH",
                "content_text": "正文",
                "source_hash": "a" * 64,
                "confidence": 1.1,
            }
        )
    with pytest.raises(ValidationError):
        DocumentIR.model_validate(
            {
                "parser_name": "mineru",
                "parser_version": "3.4.5",
                "pages": [],
                "segments": [],
                "unexpected": True,
            }
        )
