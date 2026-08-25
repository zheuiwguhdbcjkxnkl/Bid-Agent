from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.projects.documents.queries import list_documents
from app.projects.documents.schemas import (
    DocumentItem,
    DocumentListResponse,
    DocumentType,
    DocumentVersionItem,
    UploadDocumentRequest,
)


class _FakeResult:
    def __init__(self, *, scalar: object = None, rows: list[object] | None = None) -> None:
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self) -> object:
        return self._scalar

    def all(self) -> list[object]:
        return self._rows


class _FakeSession:
    def __init__(self, results: list[_FakeResult]) -> None:
        self._results = iter(results)
        self.statements: list[object] = []

    async def execute(self, statement: object) -> _FakeResult:
        self.statements.append(statement)
        return next(self._results)


def test_document_type_contains_six_approved_values() -> None:
    assert {item.value for item in DocumentType} == {
        "ANNOUNCEMENT",
        "PROCUREMENT_FILE",
        "CLARIFICATION",
        "CORRECTION",
        "ADDENDUM",
        "BID_TEMPLATE",
    }


def test_upload_document_request_is_strict() -> None:
    request = UploadDocumentRequest(
        document_type=DocumentType.PROCUREMENT_FILE,
        display_name="采购文件",
    )

    assert request.document_type is DocumentType.PROCUREMENT_FILE
    assert request.display_name == "采购文件"
    with pytest.raises(ValidationError):
        UploadDocumentRequest.model_validate(
            {
                "document_type": DocumentType.PROCUREMENT_FILE,
                "display_name": "采购文件",
                "unexpected": True,
            }
        )


def test_document_version_accepts_aware_iso_datetime_string() -> None:
    values = {
        "id": uuid4(),
        "version_no": "v1",
        "file_name": "采购文件.pdf",
        "content_type": "application/pdf",
        "file_size": 0,
        "content_hash": "a" * 64,
        "storage_uri": "s3://bucket/key",
        "parse_status": "PENDING",
        "uploaded_at": "2026-08-24T09:00:00+08:00",
    }

    item = DocumentVersionItem(**values)

    assert item.file_size == 0
    assert item.uploaded_at.tzinfo is not None


def test_document_version_rejects_negative_size_and_requires_aware_datetime() -> None:
    values = {
        "id": uuid4(),
        "version_no": "v1",
        "file_name": "采购文件.pdf",
        "content_type": "application/pdf",
        "file_size": 0,
        "content_hash": "a" * 64,
        "storage_uri": "s3://bucket/key",
        "parse_status": "PENDING",
        "uploaded_at": datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
    }

    with pytest.raises(ValidationError):
        DocumentVersionItem(**{**values, "file_size": -1})
    with pytest.raises(ValidationError):
        DocumentVersionItem(**{**values, "file_size": "0"})
    with pytest.raises(ValidationError):
        DocumentVersionItem(**{**values, "file_size": 0.5})
    with pytest.raises(ValidationError):
        DocumentVersionItem(**{**values, "uploaded_at": datetime(2026, 8, 24, 9, 0)})
    with pytest.raises(ValidationError):
        DocumentVersionItem(**{**values, "uploaded_at": "2026-08-24T09:00:00"})


def test_document_items_and_list_response_are_strict() -> None:
    version = DocumentVersionItem(
        id=uuid4(),
        version_no="v1",
        file_name="采购文件.pdf",
        content_type="application/pdf",
        file_size=12,
        content_hash="b" * 64,
        storage_uri="s3://bucket/key",
        parse_status="PENDING",
        uploaded_at=datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
    )
    document = DocumentItem(
        id=uuid4(),
        document_type=DocumentType.ANNOUNCEMENT,
        display_name="公告",
        document_status="ACTIVE",
        current_version_id=version.id,
        versions=[version],
    )
    response = DocumentListResponse(items=[document])
    assert response.items == [document]
    with pytest.raises(ValidationError):
        DocumentListResponse.model_validate({"items": [document], "unexpected": True})


@pytest.mark.asyncio
async def test_list_documents_requires_active_project_member() -> None:
    from app.core.errors import DomainError

    with pytest.raises(DomainError, match="无项目访问权限") as error:
        await list_documents(
            cast(Any, _FakeSession([_FakeResult()])), project_id=uuid4(), actor_user_id=uuid4()
        )
    assert error.value.status_code == 403
    assert error.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_list_documents_orders_versions_by_numeric_version_no() -> None:
    session = _FakeSession(
        [
            _FakeResult(scalar=object()),
            _FakeResult(rows=[]),
        ]
    )

    await list_documents(cast(Any, session), project_id=uuid4(), actor_user_id=uuid4())

    statement = str(session.statements[1])
    assert "CAST(substring(document.document_version.version_no" in statement
    assert "AS INTEGER) ASC" in statement


@pytest.mark.asyncio
async def test_list_documents_aggregates_versions_without_binary_content() -> None:
    document_id = uuid4()
    first_version_id = uuid4()
    second_version_id = uuid4()
    tenth_version_id = uuid4()
    document = SimpleNamespace(
        id=document_id,
        document_type="PROCUREMENT_FILE",
        display_name="采购文件",
        document_status="ACTIVE",
        current_version_id=second_version_id,
        created_at=datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
    )
    versions = [
        SimpleNamespace(
            id=second_version_id,
            document_id=document_id,
            version_no="v2",
            file_name="v2.pdf",
            content_type="application/pdf",
            file_size=20,
            content_hash="b" * 64,
            storage_uri="memory://v2",
            parse_status="PENDING",
            uploaded_at=datetime(2026, 8, 24, 9, 2, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=first_version_id,
            document_id=document_id,
            version_no="v1",
            file_name="v1.pdf",
            content_type="application/pdf",
            file_size=10,
            content_hash="a" * 64,
            storage_uri="memory://v1",
            parse_status="PENDING",
            uploaded_at=datetime(2026, 8, 24, 9, 1, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=tenth_version_id,
            document_id=document_id,
            version_no="v10",
            file_name="v10.pdf",
            content_type="application/pdf",
            file_size=100,
            content_hash="c" * 64,
            storage_uri="memory://v10",
            parse_status="PENDING",
            uploaded_at=datetime(2026, 8, 24, 9, 10, tzinfo=UTC),
        ),
    ]
    items = await list_documents(
        cast(
            Any,
            _FakeSession(
                [
                    _FakeResult(scalar=object()),
                    _FakeResult(
                        rows=[
                            (document, versions[1]),
                            (document, versions[0]),
                            (document, versions[2]),
                        ]
                    ),
                ]
            ),
        ),
        project_id=uuid4(),
        actor_user_id=uuid4(),
    )
    assert [version.version_no for version in items[0].versions] == ["v1", "v2", "v10"]
    assert not hasattr(items[0], "content")
