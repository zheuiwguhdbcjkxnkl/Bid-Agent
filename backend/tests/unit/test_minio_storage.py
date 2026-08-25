from __future__ import annotations

from typing import BinaryIO

import pytest

from app.core.errors import DomainError
from app.projects.documents.storage import MinioObjectStorage


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.closed = False
        self.released = False

    def read(self) -> bytes:
        return self.content

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class FakeMinioClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.last_response: FakeResponse | None = None

    def put_object(
        self,
        bucket: str,
        key: str,
        data: BinaryIO,
        length: int,
    ) -> object:
        self.objects[(bucket, key)] = data.read(length)
        return object()

    def get_object(self, bucket: str, key: str) -> FakeResponse:
        response = FakeResponse(self.objects[(bucket, key)])
        self.last_response = response
        return response

    def remove_object(self, bucket: str, key: str) -> None:
        self.objects.pop((bucket, key), None)


@pytest.mark.asyncio
async def test_minio_storage_put_get_delete_and_close_response() -> None:
    client = FakeMinioClient()
    storage = MinioObjectStorage(client=client, bucket_name="bid-files")

    uri = await storage.put(object_key="projects/p1/documents/v1.pdf", content=b"pdf")
    assert uri == "minio://bid-files/projects/p1/documents/v1.pdf"
    assert await storage.get(uri) == b"pdf"
    assert client.last_response is not None
    assert client.last_response.closed is True
    assert client.last_response.released is True
    await storage.delete(uri)
    assert client.objects == {}


@pytest.mark.asyncio
async def test_minio_storage_rejects_foreign_bucket_and_invalid_uri() -> None:
    storage = MinioObjectStorage(client=FakeMinioClient(), bucket_name="bid-files")

    for uri in ("memory://x", "minio://other/key", "minio://bid-files/../secret"):
        with pytest.raises(DomainError) as error:
            await storage.get(uri)
        assert error.value.code == "OBJECT_STORAGE_URI_INVALID"
