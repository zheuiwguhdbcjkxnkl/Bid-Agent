"""解析批次、页面、片段和任务运行基础表。"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_document_parse_workflow"
down_revision = "0002_document_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema_exists = op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'workflow')")
    )
    if schema_exists:
        raise RuntimeError(
            "workflow schema already exists; migration 0003 requires it to be absent"
        )
    op.execute("CREATE SCHEMA workflow")
    op.drop_constraint(
        "ck_document_version_parse_status",
        "document_version",
        schema="document",
        type_="check",
    )
    op.create_check_constraint(
        "ck_document_version_parse_status",
        "document_version",
        "parse_status IN ('PENDING', 'PARSING', 'PARSED', 'PARSE_FAILED')",
        schema="document",
    )

    op.create_table(
        "document_parse",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parser_name", sa.String(128), nullable=False),
        sa.Column("parser_version", sa.String(128), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=True),
        sa.Column("backend_mode", sa.String(64), nullable=True),
        sa.Column("parse_status", sa.String(32), nullable=False),
        sa.Column("quality_summary", postgresql.JSONB, nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document.document_version.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "parse_status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')",
            name="ck_document_parse_status",
        ),
        schema="document",
    )
    op.create_table(
        "document_page",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("document_parse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_no", sa.Integer, nullable=False),
        sa.Column("width", sa.Float, nullable=True),
        sa.Column("height", sa.Float, nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["document_parse_id"], ["document.document_parse.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("document_parse_id", "page_no", name="uq_document_page_parse_page_no"),
        schema="document",
    )
    op.create_table(
        "document_segment",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_parse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_segment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("segment_type", sa.String(32), nullable=False),
        sa.Column("page_no", sa.Integer, nullable=True),
        sa.Column("section_path", sa.String(1024), nullable=True),
        sa.Column("content_text", sa.Text, nullable=False),
        sa.Column("char_start", sa.Integer, nullable=True),
        sa.Column("char_end", sa.Integer, nullable=True),
        sa.Column("source_bbox", postgresql.JSONB, nullable=True),
        sa.Column("source_hash", sa.String(128), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column(
            "segment_status", sa.String(32), nullable=False, server_default=sa.text("'DRAFT'")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document.document_version.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["document_parse_id"], ["document.document_parse.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["page_id"], ["document.document_page.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "segment_type IN ('HEADING', 'PARAGRAPH', 'LIST', 'TABLE', "
            "'TABLE_ROW', 'FIGURE', 'OTHER')",
            name="ck_document_segment_type",
        ),
        sa.CheckConstraint(
            "segment_status IN ('DRAFT', 'CONFIRMED', 'STALE', 'INVALID')",
            name="ck_document_segment_status",
        ),
        schema="document",
    )
    op.create_table(
        "task_run",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_parse_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("task_status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("payload_refs", postgresql.JSONB, nullable=False),
        sa.Column("result_refs", postgresql.JSONB, nullable=True),
        sa.Column("current_step", sa.String(128), nullable=True),
        sa.Column("progress_percent", sa.Integer, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default=sa.text("3")),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column(
            "queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(128), nullable=True),
        sa.Column("last_error_message", sa.Text, nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["project.bid_project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document.document_version.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["document_parse_id"], ["document.document_parse.id"], ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "task_type IN ('RUN_WORKFLOW', 'DOCUMENT_PARSE', 'OCR', 'EMBEDDING', "
            "'MULTIMODAL_ANALYSIS', 'DOCUMENT_RENDER', 'DOCUMENT_EXPORT', "
            "'CONSISTENCY_CHECK', 'REDELIVERY')",
            name="ck_task_run_type",
        ),
        sa.CheckConstraint(
            "task_status IN ('QUEUED', 'DISPATCHED', 'RUNNING', 'SUCCEEDED', "
            "'FAILED', 'CANCELLED', 'STALE')",
            name="ck_task_run_status",
        ),
        sa.CheckConstraint(
            "progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100",
            name="ck_task_run_progress_percent",
        ),
        schema="workflow",
    )
    op.create_index(
        "uq_task_run_active_document_parse_version",
        "task_run",
        ["document_version_id"],
        unique=True,
        schema="workflow",
        postgresql_where=sa.text(
            "task_type = 'DOCUMENT_PARSE' AND task_status IN ('QUEUED', 'DISPATCHED', 'RUNNING')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_task_run_active_document_parse_version", table_name="task_run", schema="workflow"
    )
    op.drop_table("task_run", schema="workflow")
    op.drop_table("document_segment", schema="document")
    op.drop_table("document_page", schema="document")
    op.drop_table("document_parse", schema="document")
    op.drop_constraint(
        "ck_document_version_parse_status", "document_version", schema="document", type_="check"
    )
    op.create_check_constraint(
        "ck_document_version_parse_status",
        "document_version",
        "parse_status IN ('PENDING')",
        schema="document",
    )
    op.execute("DROP SCHEMA workflow")
