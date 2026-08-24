from __future__ import annotations

import hashlib
from pathlib import PurePath
from typing import Protocol
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

    async def delete(self, storage_uri: str) -> None: ...


class UnconfiguredObjectStorage:
    async def put(self, *, object_key: str, content: bytes) -> str:
        raise DomainError(500, "OBJECT_STORAGE_NOT_CONFIGURED", "对象存储未配置")

    async def delete(self, storage_uri: str) -> None:
        raise DomainError(500, "OBJECT_STORAGE_NOT_CONFIGURED", "对象存储未配置")


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
