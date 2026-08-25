from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt, field_validator

from app.projects.schemas import _StrictModel, _validate_aware_datetime


class DocumentType(StrEnum):
    ANNOUNCEMENT = "ANNOUNCEMENT"
    PROCUREMENT_FILE = "PROCUREMENT_FILE"
    CLARIFICATION = "CLARIFICATION"
    CORRECTION = "CORRECTION"
    ADDENDUM = "ADDENDUM"
    BID_TEMPLATE = "BID_TEMPLATE"


class UploadDocumentRequest(_StrictModel):
    document_type: DocumentType
    display_name: str | None = Field(default=None, min_length=1, max_length=255)


class DocumentVersionItem(_StrictModel):
    id: UUID
    version_no: str
    file_name: str
    content_type: str
    file_size: StrictInt = Field(ge=0)
    content_hash: str
    storage_uri: str
    parse_status: str
    uploaded_at: AwareDatetime

    @field_validator("uploaded_at")
    @classmethod
    def _validate_uploaded_at(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)


class DocumentItem(_StrictModel):
    id: UUID
    document_type: DocumentType
    display_name: str
    document_status: str
    current_version_id: UUID | None
    versions: list[DocumentVersionItem]


class DocumentListResponse(_StrictModel):
    items: list[DocumentItem]
