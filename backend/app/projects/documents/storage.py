from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO
from pathlib import PurePath
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import UUID

from app.core.errors import DomainError

MAX_FILE_SIZE = 200 * 1024 * 1024

_SUPPORTED_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class ObjectStorage(Protocol):
    async def put(self, *, object_key: str, content: bytes) -> str: ...

    async def get(self, storage_uri: str) -> bytes | None: ...

    async def delete(self, storage_uri: str) -> None: ...


class UnconfiguredObjectStorage:
    async def put(self, *, object_key: str, content: bytes) -> str:
        raise DomainError(500, "OBJECT_STORAGE_NOT_CONFIGURED", "对象存储未配置")

    async def get(self, storage_uri: str) -> bytes | None:
        raise DomainError(500, "OBJECT_STORAGE_NOT_CONFIGURED", "对象存储未配置")

    async def delete(self, storage_uri: str) -> None:
        raise DomainError(500, "OBJECT_STORAGE_NOT_CONFIGURED", "对象存储未配置")


class MinioClient(Protocol):
    def put_object(self, bucket_name: str, object_name: str, data: Any, length: int) -> Any: ...

    def get_object(self, bucket_name: str, object_name: str) -> Any: ...

    def remove_object(self, bucket_name: str, object_name: str) -> None: ...


class MinioObjectStorage:
    def __init__(self, *, client: MinioClient, bucket_name: str) -> None:
        self._client = client
        self._bucket_name = bucket_name

    async def put(self, *, object_key: str, content: bytes) -> str:
        key = self._validate_key(object_key)
        await asyncio.to_thread(
            self._client.put_object,
            self._bucket_name,
            key,
            BytesIO(content),
            len(content),
        )
        return f"minio://{self._bucket_name}/{key}"

    async def get(self, storage_uri: str) -> bytes | None:
        key = self._parse_uri(storage_uri)
        response = await asyncio.to_thread(
            self._client.get_object,
            self._bucket_name,
            key,
        )
        try:
            return await asyncio.to_thread(response.read)
        finally:
            response.close()
            response.release_conn()

    async def delete(self, storage_uri: str) -> None:
        key = self._parse_uri(storage_uri)
        await asyncio.to_thread(
            self._client.remove_object,
            self._bucket_name,
            key,
        )

    def _parse_uri(self, storage_uri: str) -> str:
        parsed = urlparse(storage_uri)
        if parsed.scheme != "minio" or parsed.netloc != self._bucket_name:
            raise _storage_uri_error()
        return self._validate_key(parsed.path.removeprefix("/"))

    @staticmethod
    def _validate_key(object_key: str) -> str:
        if not object_key or object_key.startswith("/") or "\\" in object_key:
            raise _storage_uri_error()
        segments = object_key.split("/")
        if any(segment in {"", ".", ".."} for segment in segments):
            raise _storage_uri_error()
        return object_key


class MemoryObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, *, object_key: str, content: bytes) -> str:
        self.objects[object_key] = content
        return f"memory://{object_key}"

    async def get(self, storage_uri: str) -> bytes | None:
        return self.objects.get(storage_uri.removeprefix("memory://"))

    async def delete(self, storage_uri: str) -> None:
        self.objects.pop(storage_uri.removeprefix("memory://"), None)


def _storage_uri_error() -> DomainError:
    return DomainError(422, "OBJECT_STORAGE_URI_INVALID", "对象存储 URI 无效")


def _validation_error() -> DomainError:
    return DomainError(422, "VALIDATION_ERROR", "文件校验失败")


def _safe_extension(file_name: str) -> str:
    if not file_name or any(
        ord(character) < 32 or ord(character) == 127 for character in file_name
    ):
        raise _validation_error()
    path_segments = file_name.replace("\\", "/").split("/")
    if "/" in file_name or "\\" in file_name or ".." in path_segments:
        raise _validation_error()

    extension = PurePath(file_name).suffix.lower()
    if extension not in _SUPPORTED_TYPES:
        raise _validation_error()
    return extension


def validate_upload_metadata(*, file_name: str, content_type: str, content: bytes) -> None:
    extension = _safe_extension(file_name)
    if not content or len(content) > MAX_FILE_SIZE:
        raise _validation_error()
    if content_type != _SUPPORTED_TYPES[extension]:
        raise _validation_error()


def calculate_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_object_key(*, project_id: UUID, document_id: UUID, file_name: str) -> str:
    extension = _safe_extension(file_name)
    return f"projects/{project_id}/documents/{document_id}{extension}"
