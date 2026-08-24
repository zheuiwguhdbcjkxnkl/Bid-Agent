from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
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
            "parse_status IN ('PENDING')",
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
