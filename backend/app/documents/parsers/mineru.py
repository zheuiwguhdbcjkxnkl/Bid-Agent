from __future__ import annotations

import hashlib
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.errors import DomainError
from app.documents.ir import DocumentIR, DocumentIRPage, DocumentIRSegment, SegmentType


class MineruProvider(Protocol):
    async def parse(
        self,
        *,
        file_name: str,
        content_type: str,
        content: bytes,
    ) -> DocumentIR: ...


class _MineruPage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    page_no: int
    width: float | int | None = None
    height: float | int | None = None


class _MineruContent(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    type: str
    text: str
    page_idx: int
    bbox: list[float | int] | None = None
    confidence: float | int | None = None
    text_level: int | None = None


class _MineruResult(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    version: str
    backend: str
    model_version: str | None = None
    pages: list[_MineruPage]
    content_list: list[_MineruContent]


class HttpMineruProvider:
    def __init__(
        self,
        *,
        base_url: str,
        client: httpx.AsyncClient,
        timeout_seconds: int,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def parse(
        self,
        *,
        file_name: str,
        content_type: str,
        content: bytes,
    ) -> DocumentIR:
        try:
            response = await self._client.post(
                f"{self._base_url}/file_parse",
                files={"files": (file_name, content, content_type)},
                data={"backend": "pipeline", "return_content_list": "true"},
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise DomainError(
                503,
                "MINERU_TEMPORARILY_UNAVAILABLE",
                "内部 MinerU 服务暂时不可用",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise DomainError(
                502,
                "MINERU_REQUEST_FAILED",
                "内部 MinerU 服务解析失败",
            ) from exc

        try:
            result = _MineruResult.model_validate(response.json())
            return _to_document_ir(result)
        except (ValueError, ValidationError) as exc:
            raise DomainError(
                502,
                "MINERU_RESULT_INVALID",
                "内部 MinerU 返回结果不符合解析契约",
            ) from exc


def _to_document_ir(result: _MineruResult) -> DocumentIR:
    pages = [
        DocumentIRPage(
            page_no=page.page_no + 1,
            width=float(page.width) if page.width is not None else None,
            height=float(page.height) if page.height is not None else None,
        )
        for page in result.pages
    ]
    segments = [_to_segment(item) for item in result.content_list]
    if not pages or not segments:
        raise ValueError("MinerU 结果缺少页面或内容片段")
    return DocumentIR(
        parser_name="mineru",
        parser_version=result.version,
        model_version=result.model_version,
        backend_mode=result.backend,
        pages=pages,
        segments=segments,
    )


def _to_segment(item: _MineruContent) -> DocumentIRSegment:
    segment_type, metadata = _map_segment_type(item)
    bbox = _normalize_bbox(item.bbox)
    content_text = item.text.strip()
    if not content_text:
        raise ValueError("MinerU 内容片段为空")
    return DocumentIRSegment(
        segment_type=segment_type,
        page_no=item.page_idx + 1,
        section_path=content_text if segment_type == "HEADING" else None,
        content_text=content_text,
        source_hash=hashlib.sha256(content_text.encode("utf-8")).hexdigest(),
        source_bbox=bbox,
        confidence=float(item.confidence) if item.confidence is not None else None,
        metadata_json=metadata,
    )


def _map_segment_type(item: _MineruContent) -> tuple[SegmentType, dict[str, Any] | None]:
    if item.type == "table":
        return "TABLE", {"format": "html"}
    if item.type in {"image", "figure"}:
        return "FIGURE", None
    if item.type == "list":
        return "LIST", None
    if item.text_level is not None:
        return "HEADING", {"heading_level": item.text_level}
    if item.type == "text":
        return "PARAGRAPH", None
    return "OTHER", {"mineru_type": item.type}


def _normalize_bbox(values: list[float | int] | None) -> dict[str, float] | None:
    if values is None:
        return None
    if len(values) != 4:
        raise ValueError("MinerU bbox 必须包含四个坐标")
    return {
        "x0": float(values[0]),
        "y0": float(values[1]),
        "x1": float(values[2]),
        "y1": float(values[3]),
    }
