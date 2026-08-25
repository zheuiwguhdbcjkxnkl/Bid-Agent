from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskRun(Base):
    __tablename__ = "task_run"
    __table_args__ = (
        CheckConstraint(
            "task_type IN ('RUN_WORKFLOW', 'DOCUMENT_PARSE', 'OCR', 'EMBEDDING', "
            "'MULTIMODAL_ANALYSIS', 'DOCUMENT_RENDER', 'DOCUMENT_EXPORT', "
            "'CONSISTENCY_CHECK', 'REDELIVERY')",
            name="ck_task_run_type",
        ),
        CheckConstraint(
            "task_status IN ('QUEUED', 'DISPATCHED', 'RUNNING', 'SUCCEEDED', "
            "'FAILED', 'CANCELLED', 'STALE')",
            name="ck_task_run_status",
        ),
        CheckConstraint(
            "progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100",
            name="ck_task_run_progress_percent",
        ),
        {"schema": "workflow"},
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
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document.document_version.id", ondelete="CASCADE"),
        nullable=True,
    )
    document_parse_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document.document_parse.id", ondelete="SET NULL"),
        nullable=True,
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    task_status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_refs: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    result_refs: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    current_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    progress_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
