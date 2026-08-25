from __future__ import annotations

import httpx
import pytest

from app.core.errors import DomainError
from app.documents.parsers.mineru import HttpMineruProvider


@pytest.mark.asyncio
async def test_mineru_provider_converts_internal_content_list_to_ir() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/file_parse"
        return httpx.Response(
            200,
            json={
                "version": "3.4.5",
                "backend": "pipeline",
                "model_version": "pipeline",
                "pages": [{"page_no": 0, "width": 595, "height": 842}],
                "content_list": [
                    {
                        "type": "text",
                        "text": "项目概况",
                        "page_idx": 0,
                        "bbox": [10, 20, 300, 50],
                        "confidence": 0.98,
                        "text_level": 1,
                    },
                    {
                        "type": "table",
                        "text": "<table><tr><td>资格要求</td></tr></table>",
                        "page_idx": 0,
                        "bbox": [10, 80, 500, 300],
                    },
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = HttpMineruProvider(
        base_url="http://mineru:8000",
        client=client,
        timeout_seconds=60,
    )
    try:
        ir = await provider.parse(
            file_name="bid.pdf",
            content_type="application/pdf",
            content=b"pdf",
        )
    finally:
        await client.aclose()

    assert ir.parser_name == "mineru"
    assert ir.parser_version == "3.4.5"
    assert ir.pages[0].page_no == 1
    assert [item.segment_type for item in ir.segments] == ["HEADING", "TABLE"]
    assert ir.segments[0].source_bbox == {"x0": 10.0, "y0": 20.0, "x1": 300.0, "y1": 50.0}
    assert ir.segments[1].metadata_json == {"format": "html"}


@pytest.mark.asyncio
async def test_mineru_provider_maps_timeout_and_rejects_incomplete_result() -> None:
    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    timeout_client = httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler))
    provider = HttpMineruProvider(
        base_url="http://mineru:8000",
        client=timeout_client,
        timeout_seconds=1,
    )
    try:
        with pytest.raises(DomainError) as timeout_error:
            await provider.parse(
                file_name="bid.pdf",
                content_type="application/pdf",
                content=b"pdf",
            )
    finally:
        await timeout_client.aclose()
    assert timeout_error.value.code == "MINERU_TEMPORARILY_UNAVAILABLE"

    invalid_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"pages": []}))
    )
    invalid_provider = HttpMineruProvider(
        base_url="http://mineru:8000",
        client=invalid_client,
        timeout_seconds=1,
    )
    try:
        with pytest.raises(DomainError) as invalid_error:
            await invalid_provider.parse(
                file_name="bid.pdf",
                content_type="application/pdf",
                content=b"pdf",
            )
    finally:
        await invalid_client.aclose()
    assert invalid_error.value.code == "MINERU_RESULT_INVALID"
