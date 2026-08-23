"""M1 数据库基础表与约束。"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_m1_foundation"
down_revision = None
branch_labels = None
depends_on = None


ACCOUNT_STATUS_CHECK = "account_status IN ('ACTIVE', 'DISABLED')"
SYSTEM_ROLE_CHECK = (
    "system_role IN ('BID_MANAGER', 'COMMERCIAL_WRITER', 'TECHNICAL_WRITER', "
    "'COMPLIANCE_REVIEWER', 'MATERIAL_ADMIN', 'ADMIN')"
)
REVOKE_REASON_CHECK = (
    "revoke_reason IS NULL OR revoke_reason IN ('LOGOUT', 'PASSWORD_CHANGED', 'ACCOUNT_DISABLED', "
    "'ROLE_CHANGED', 'ADMIN_REVOKED', 'EXPIRED')"
)
IDEMPOTENCY_STATUS_CHECK = "processing_status IN ('PROCESSING', 'SUCCEEDED')"
IDEMPOTENCY_SUCCEEDED_FIELDS_CHECK = (
    "processing_status <> 'SUCCEEDED' OR "
    "(response_status IS NOT NULL AND response_body IS NOT NULL AND completed_at IS NOT NULL)"
)
ORGANIZATION_TYPE_CHECK = "organization_type IN ('CLIENT', 'VENDOR', 'PROCUREMENT_PARTY')"
ORGANIZATION_DATA_CLASSIFICATION_CHECK = "data_classification IN ('INTERNAL')"
PROCUREMENT_METHOD_CHECK = (
    "procurement_method IN ('PUBLIC_TENDER', 'INVITED_TENDER', 'COMPETITIVE_NEGOTIATION', "
    "'COMPETITIVE_CONSULTATION', 'INQUIRY', 'SINGLE_SOURCE', 'OTHER')"
)
REGIME_TYPE_CHECK = "regime_type IN ('GOVERNMENT_PROCUREMENT', 'TENDER_BIDDING')"
PROJECT_STATUS_CHECK = "project_status IN ('DRAFT')"
EXTERNAL_AI_POLICY_CHECK = (
    "external_ai_policy IN ('PUBLIC_ONLY', 'ALLOW_INTERNAL', 'ALLOW_CONFIDENTIAL')"
)
PACKAGE_STATUS_CHECK = "package_status IN ('ACTIVE', 'NOT_BIDDING')"
PROJECT_ROLE_CHECK = (
    "project_role IN ('BID_MANAGER', 'BID_WRITER', 'TECHNICAL_WRITER', 'PRICING_OWNER', "
    "'COMMERCIAL_REVIEWER', 'COMPLIANCE_LEGAL_REVIEWER', 'SUBMISSION_OWNER')"
)
ASSIGNMENT_STATUS_CHECK = "assignment_status IN ('ACTIVE', 'REMOVED')"
ACTOR_TYPE_CHECK = "actor_type IN ('USER', 'SYSTEM', 'AGENT')"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE SCHEMA IF NOT EXISTS iam")
    op.execute("CREATE SCHEMA IF NOT EXISTS project")
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")
    op.execute("CREATE SEQUENCE IF NOT EXISTS project.project_code_seq START WITH 1 INCREMENT BY 1")

    op.create_table(
        "organization",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("organization_type", sa.String(length=64), nullable=False),
        sa.Column("tenant_key", sa.String(length=128), nullable=False),
        sa.Column(
            "data_classification",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'INTERNAL'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_key", name="uq_organization_tenant_key"),
        sa.CheckConstraint(ORGANIZATION_TYPE_CHECK, name="ck_organization_type"),
        sa.CheckConstraint(
            ORGANIZATION_DATA_CLASSIFICATION_CHECK, name="ck_organization_data_classification"
        ),
        schema="iam",
    )

    op.create_table(
        "user",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("login_name", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("account_status", sa.String(length=32), nullable=False),
        sa.Column("system_role", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "login_name = lower(btrim(login_name))",
            name="ck_user_login_name_normalized",
        ),
        sa.CheckConstraint(ACCOUNT_STATUS_CHECK, name="ck_user_account_status"),
        sa.CheckConstraint(SYSTEM_ROLE_CHECK, name="ck_user_system_role"),
        sa.ForeignKeyConstraint(["organization_id"], ["iam.organization.id"], ondelete="RESTRICT"),
        schema="iam",
    )
    op.create_index(
        "uq_user_organization_login_name_normalized",
        "user",
        ["organization_id", sa.text("lower(btrim(login_name))")],
        unique=True,
        schema="iam",
    )

    op.create_table(
        "user_session",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reauthenticated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=64), nullable=True),
        sa.Column("client_fingerprint_hash", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["iam.user.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("token_hash", name="uq_user_session_token_hash"),
        sa.CheckConstraint(REVOKE_REASON_CHECK, name="ck_user_session_revoke_reason"),
        schema="iam",
    )

    op.create_table(
        "idempotency_record",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("http_method", sa.String(length=16), nullable=False),
        sa.Column("route_template", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=255), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["iam.organization.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["iam.user.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "organization_id",
            "actor_user_id",
            "http_method",
            "route_template",
            "idempotency_key",
            name="uq_idempotency_record_scope",
        ),
        sa.CheckConstraint(
            IDEMPOTENCY_STATUS_CHECK, name="ck_idempotency_record_processing_status"
        ),
        sa.CheckConstraint(
            IDEMPOTENCY_SUCCEEDED_FIELDS_CHECK, name="ck_idempotency_record_succeeded_fields"
        ),
        schema="iam",
    )

    op.create_table(
        "bid_project",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_code", sa.String(length=64), nullable=False),
        sa.Column("project_name", sa.String(length=255), nullable=False),
        sa.Column("procurement_method", sa.String(length=64), nullable=False),
        sa.Column("regime_type", sa.String(length=64), nullable=False),
        sa.Column(
            "project_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'DRAFT'"),
        ),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "external_ai_policy",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'PUBLIC_ONLY'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["iam.organization.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "organization_id", "project_code", name="uq_bid_project_organization_project_code"
        ),
        sa.CheckConstraint(PROCUREMENT_METHOD_CHECK, name="ck_bid_project_procurement_method"),
        sa.CheckConstraint(REGIME_TYPE_CHECK, name="ck_bid_project_regime_type"),
        sa.CheckConstraint(PROJECT_STATUS_CHECK, name="ck_bid_project_project_status"),
        sa.CheckConstraint(EXTERNAL_AI_POLICY_CHECK, name="ck_bid_project_external_ai_policy"),
        schema="project",
    )

    op.create_table(
        "bid_package",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_code", sa.String(length=64), nullable=False),
        sa.Column("package_name", sa.String(length=255), nullable=False),
        sa.Column("package_status", sa.String(length=32), nullable=False),
        sa.Column("is_v1_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.bid_project.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "project_id", "package_code", name="uq_bid_package_project_package_code"
        ),
        sa.CheckConstraint(PACKAGE_STATUS_CHECK, name="ck_bid_package_package_status"),
        schema="project",
    )
    op.create_index(
        "uq_bid_package_single_primary",
        "bid_package",
        ["project_id"],
        unique=True,
        schema="project",
        postgresql_where=sa.text("is_v1_primary IS TRUE"),
    )

    op.create_table(
        "project_member",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_role", sa.String(length=64), nullable=False),
        sa.Column("assignment_status", sa.String(length=32), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.bid_project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["iam.user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("project_id", "user_id", name="pk_project_member"),
        sa.CheckConstraint(PROJECT_ROLE_CHECK, name="ck_project_member_project_role"),
        sa.CheckConstraint(ASSIGNMENT_STATUS_CHECK, name="ck_project_member_assignment_status"),
        schema="project",
    )

    op.create_table(
        "audit_event",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("object_type", sa.String(length=128), nullable=False),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["iam.organization.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["project.bid_project.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["iam.user.id"], ondelete="SET NULL"),
        sa.CheckConstraint(ACTOR_TYPE_CHECK, name="ck_audit_event_actor_type"),
        schema="audit",
    )
    op.create_index(
        "ix_audit_event_organization_occurred_at",
        "audit_event",
        ["organization_id", "occurred_at"],
        schema="audit",
    )
    op.create_index(
        "ix_audit_event_project_occurred_at",
        "audit_event",
        ["project_id", "occurred_at"],
        schema="audit",
    )
    op.create_index(
        "ix_audit_event_object_type_object_id",
        "audit_event",
        ["object_type", "object_id"],
        schema="audit",
    )
    op.create_index(
        "ix_audit_event_actor_user_id_occurred_at",
        "audit_event",
        ["actor_user_id", "occurred_at"],
        schema="audit",
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit.prevent_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_event is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_prevent_audit_event_mutation
        BEFORE UPDATE OR DELETE ON audit.audit_event
        FOR EACH ROW
        EXECUTE FUNCTION audit.prevent_audit_event_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_event_no_truncate
        BEFORE TRUNCATE ON audit.audit_event
        FOR EACH STATEMENT
        EXECUTE FUNCTION audit.prevent_audit_event_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_event_no_truncate ON audit.audit_event")
    op.execute("DROP TRIGGER IF EXISTS trg_prevent_audit_event_mutation ON audit.audit_event")
    op.execute("DROP FUNCTION IF EXISTS audit.prevent_audit_event_mutation()")
    op.drop_index(
        "ix_audit_event_actor_user_id_occurred_at", table_name="audit_event", schema="audit"
    )
    op.drop_index("ix_audit_event_object_type_object_id", table_name="audit_event", schema="audit")
    op.drop_index("ix_audit_event_project_occurred_at", table_name="audit_event", schema="audit")
    op.drop_index(
        "ix_audit_event_organization_occurred_at", table_name="audit_event", schema="audit"
    )
    op.drop_table("audit_event", schema="audit")
    op.drop_table("project_member", schema="project")
    op.drop_index("uq_bid_package_single_primary", table_name="bid_package", schema="project")
    op.drop_table("bid_package", schema="project")
    op.drop_table("bid_project", schema="project")
    op.drop_table("idempotency_record", schema="iam")
    op.drop_table("user_session", schema="iam")
    op.drop_index(
        "uq_user_organization_login_name_normalized",
        table_name="user",
        schema="iam",
    )
    op.drop_table("user", schema="iam")
    op.drop_table("organization", schema="iam")
    op.execute("DROP SEQUENCE IF EXISTS project.project_code_seq")
    op.execute("DROP SCHEMA IF EXISTS audit")
    op.execute("DROP SCHEMA IF EXISTS project")
    op.execute("DROP SCHEMA IF EXISTS iam")
