from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.core.errors import DomainError
from app.projects.documents.storage import (
    MAX_FILE_SIZE,
    MemoryObjectStorage,
    UnconfiguredObjectStorage,
    build_object_key,
    calculate_sha256,
    validate_upload_metadata,
)


@pytest.mark.asyncio
async def test_unconfigured_storage_rejects_write() -> None:
    storage = UnconfiguredObjectStorage()

    with pytest.raises(DomainError) as exc:
        await storage.put(object_key="projects/p/documents/v1.pdf", content=b"pdf")

    assert exc.value.status_code == 500
    assert exc.value.code == "OBJECT_STORAGE_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_memory_storage_put_get_delete() -> None:
    storage = MemoryObjectStorage()
    uri = await storage.put(object_key="projects/p/documents/v1.pdf", content=b"pdf")

    assert uri == "memory://projects/p/documents/v1.pdf"
    assert await storage.get(uri) == b"pdf"

    await storage.delete(uri)
    assert await storage.get(uri) is None


def test_validate_upload_metadata_accepts_supported_pdf() -> None:
    validate_upload_metadata(
        file_name="招标文件.pdf",
        content_type="application/pdf",
        content=b"pdf",
    )


def test_validate_upload_metadata_accepts_supported_office_types() -> None:
    validate_upload_metadata(
        file_name="需求.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content=b"docx",
    )
    validate_upload_metadata(
        file_name="报价.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content=b"xlsx",
    )


@pytest.mark.parametrize(
    "file_name",
    ["报价\n.pdf", "报价\r.pdf", "报价\x00.pdf"],
)
def test_validate_upload_metadata_rejects_ascii_control_characters(
    file_name: str,
) -> None:
    with pytest.raises(DomainError) as exc:
        validate_upload_metadata(
            file_name=file_name,
            content_type="application/pdf",
            content=b"pdf",
        )

    assert exc.value.status_code == 422
    assert exc.value.code == "VALIDATION_ERROR"
    assert exc.value.message == "文件校验失败"


@pytest.mark.parametrize("file_name", ["../file.pdf", "..\\file.pdf", "folder/file.pdf", ""])
def test_validate_upload_metadata_rejects_path_like_or_empty_file_name(
    file_name: str,
) -> None:
    with pytest.raises(DomainError) as exc:
        validate_upload_metadata(
            file_name=file_name,
            content_type="application/pdf",
            content=b"pdf",
        )

    assert exc.value.status_code == 422
    assert exc.value.code == "VALIDATION_ERROR"
    assert exc.value.message == "文件校验失败"


@pytest.mark.parametrize(
    ("file_name", "content_type", "content"),
    [
        ("empty.pdf", "application/pdf", b""),
        ("script.exe", "application/octet-stream", b"MZ"),
        ("file.pdf", "application/octet-stream", b"pdf"),
        ("file.docx", "application/pdf", b"docx"),
        ("file.xlsx", "application/pdf", b"xlsx"),
    ],
)
def test_validate_upload_metadata_rejects_invalid_metadata(
    file_name: str, content_type: str, content: bytes
) -> None:
    with pytest.raises(DomainError) as exc:
        validate_upload_metadata(
            file_name=file_name,
            content_type=content_type,
            content=content,
        )

    assert exc.value.status_code == 422
    assert exc.value.code == "VALIDATION_ERROR"
    assert exc.value.message == "文件校验失败"


def test_validate_upload_metadata_accepts_exact_size_limit() -> None:
    validate_upload_metadata(
        file_name="large.pdf",
        content_type="application/pdf",
        content=b"x" * MAX_FILE_SIZE,
    )


def test_validate_upload_metadata_rejects_content_over_size_limit() -> None:
    with pytest.raises(DomainError) as exc:
        validate_upload_metadata(
            file_name="large.pdf",
            content_type="application/pdf",
            content=b"x" * (MAX_FILE_SIZE + 1),
        )

    assert exc.value.code == "VALIDATION_ERROR"


def test_calculate_sha256() -> None:
    assert calculate_sha256(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_build_object_key_uses_project_uuid_and_safe_extension() -> None:
    project_id = uuid4()
    document_id = uuid4()

    key = build_object_key(project_id=project_id, document_id=document_id, file_name="报价.xlsx")

    assert key == f"projects/{project_id}/documents/{document_id}.xlsx"
    assert "报价" not in key
    UUID(key.split("/")[3].split(".")[0])


def test_build_object_key_rejects_unsafe_extension() -> None:
    with pytest.raises(DomainError) as exc:
        build_object_key(project_id=uuid4(), document_id=uuid4(), file_name="file.exe")

    assert exc.value.status_code == 422
    assert exc.value.code == "VALIDATION_ERROR"
