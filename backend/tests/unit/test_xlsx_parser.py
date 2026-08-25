from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook

from app.documents.parsers.xlsx import parse_xlsx


def _xlsx_content() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "报价表"
    sheet["A1"] = "项目"
    sheet["B1"] = "金额"
    sheet["A2"] = "软件"
    sheet["B2"] = 100
    sheet["C2"] = "=B2*1.06"
    sheet.merge_cells("A3:C3")
    sheet["A3"] = "含税总价"
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def test_xlsx_parser_preserves_sheet_cells_formulas_and_merged_regions() -> None:
    ir = parse_xlsx(_xlsx_content())

    assert ir.parser_name == "openpyxl"
    assert ir.pages[0].metadata_json == {"sheet_name": "报价表"}
    assert len(ir.segments) == 1
    segment = ir.segments[0]
    assert segment.segment_type == "TABLE"
    assert "C2\t=B2*1.06" in segment.content_text
    assert segment.metadata_json is not None
    assert segment.metadata_json["merged_ranges"] == ["A3:C3"]
