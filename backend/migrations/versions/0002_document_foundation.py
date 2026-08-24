"""采购文件与文件版本基础表。"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_document_foundation"
down_revision = "0001_m1_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema_exists = op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'document')")
    )
    if schema_exists:
        raise RuntimeError(
            "document schema already exists; migration 0002 requires it to be absent"
        )

    op.execute("CREATE SCHEMA document")

    op.create_table(
        "procurement_document",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column(
            "document_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'ACTIVE'"),
        ),
        sa.Column("current_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.bid_project.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "document_type IN ('ANNOUNCEMENT', 'PROCUREMENT_FILE', 'CLARIFICATION', "
            "'CORRECTION', 'ADDENDUM', 'BID_TEMPLATE')",
            name="ck_procurement_document_type",
        ),
        sa.CheckConstraint(
            "document_status IN ('ACTIVE')",
            name="ck_procurement_document_status",
        ),
        schema="document",
    )

    op.create_table(
        "document_version",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_no", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("storage_uri", sa.String(length=1024), nullable=False),
        sa.Column(
            "parse_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["document.procurement_document.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("document_id", "version_no", name="uq_document_version_no"),
        sa.UniqueConstraint("document_id", "content_hash", name="uq_document_version_hash"),
        sa.CheckConstraint("file_size >= 0", name="ck_document_version_file_size_non_negative"),
        sa.CheckConstraint(
            "parse_status IN ('PENDING')",
            name="ck_document_version_parse_status",
        ),
        schema="document",
    )


def downgrade() -> None:
    op.drop_table("document_version", schema="document")
    op.drop_table("procurement_document", schema="document")
    op.execute("DROP SCHEMA IF EXISTS document")
