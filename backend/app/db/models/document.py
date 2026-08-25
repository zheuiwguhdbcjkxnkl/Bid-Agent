from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProcurementDocument(Base):
    __tablename__ = "procurement_document"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('ANNOUNCEMENT', 'PROCUREMENT_FILE', 'CLARIFICATION', "
            "'CORRECTION', 'ADDENDUM', 'BID_TEMPLATE')",
            name="ck_procurement_document_type",
        ),
        CheckConstraint(
            "document_status IN ('ACTIVE')",
            name="ck_procurement_document_status",
        ),
        {"schema": "document"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project.bid_project.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'ACTIVE'"),
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class DocumentVersion(Base):
    __tablename__ = "document_version"
    __table_args__ = (
        UniqueConstraint("document_id", "version_no", name="uq_document_version_no"),
        UniqueConstraint("document_id", "content_hash", name="uq_document_version_hash"),
        CheckConstraint("file_size >= 0", name="ck_document_version_file_size_non_negative"),
        CheckConstraint(
            "parse_status IN ('PENDING', 'PARSING', 'PARSED', 'PARSE_FAILED')",
            name="ck_document_version_parse_status",
        ),
        {"schema": "document"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document.procurement_document.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    parse_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'PENDING'"),
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class DocumentParse(Base):
    __tablename__ = "document_parse"
    __table_args__ = (
        CheckConstraint(
            "parse_status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')",
            name="ck_document_parse_status",
        ),
        {"schema": "document"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document.document_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    parser_name: Mapped[str] = mapped_column(String(128), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    backend_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False)
    quality_summary: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class DocumentPage(Base):
    __tablename__ = "document_page"
    __table_args__ = (
        UniqueConstraint("document_parse_id", "page_no", name="uq_document_page_parse_page_no"),
        {"schema": "document"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    document_parse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document.document_parse.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[float | None] = mapped_column(nullable=True)
    height: Mapped[float | None] = mapped_column(nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class DocumentSegment(Base):
    __tablename__ = "document_segment"
    __table_args__ = (
        CheckConstraint(
            "segment_type IN ('HEADING', 'PARAGRAPH', 'LIST', 'TABLE', "
            "'TABLE_ROW', 'FIGURE', 'OTHER')",
            name="ck_document_segment_type",
        ),
        CheckConstraint(
            "segment_status IN ('DRAFT', 'CONFIRMED', 'STALE', 'INVALID')",
            name="ck_document_segment_status",
        ),
        {"schema": "document"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document.document_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_parse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document.document_parse.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document.document_page.id", ondelete="SET NULL"),
        nullable=True,
    )
    parent_segment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    segment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_bbox: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    source_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    segment_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'DRAFT'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
