from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Organization(Base):
    __tablename__ = "organization"
    __table_args__ = (
        UniqueConstraint("tenant_key", name="uq_organization_tenant_key"),
        CheckConstraint(
            "organization_type IN ('CLIENT', 'VENDOR', 'PROCUREMENT_PARTY')",
            name="ck_organization_type",
        ),
        CheckConstraint(
            "data_classification IN ('INTERNAL')", name="ck_organization_data_classification"
        ),
        {"schema": "iam"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_type: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_key: Mapped[str] = mapped_column(String(128), nullable=False)
    data_classification: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'INTERNAL'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        CheckConstraint(
            "login_name = lower(btrim(login_name))",
            name="ck_user_login_name_normalized",
        ),
        CheckConstraint("account_status IN ('ACTIVE', 'DISABLED')", name="ck_user_account_status"),
        CheckConstraint(
            "system_role IN ('BID_MANAGER', 'COMMERCIAL_WRITER', 'TECHNICAL_WRITER', "
            "'COMPLIANCE_REVIEWER', 'MATERIAL_ADMIN', 'ADMIN')",
            name="ck_user_system_role",
        ),
        Index(
            "uq_user_organization_login_name_normalized",
            "organization_id",
            text("lower(btrim(login_name))"),
            unique=True,
        ),
        {"schema": "iam"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("iam.organization.id", ondelete="RESTRICT"),
        nullable=False,
    )
    login_name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_status: Mapped[str] = mapped_column(String(32), nullable=False)
    system_role: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class UserSession(Base):
    __tablename__ = "user_session"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_user_session_token_hash"),
        CheckConstraint(
            "revoke_reason IS NULL OR revoke_reason IN ("
            "'LOGOUT', 'PASSWORD_CHANGED', 'ACCOUNT_DISABLED', "
            "'ROLE_CHANGED', 'ADMIN_REVOKED', 'EXPIRED'"
            ")",
            name="ck_user_session_revoke_reason",
        ),
        {"schema": "iam"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("iam.user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reauthenticated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_fingerprint_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_record"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "actor_user_id",
            "http_method",
            "route_template",
            "idempotency_key",
            name="uq_idempotency_record_scope",
        ),
        CheckConstraint(
            "processing_status IN ('PROCESSING', 'SUCCEEDED')",
            name="ck_idempotency_record_processing_status",
        ),
        CheckConstraint(
            "processing_status <> 'SUCCEEDED' OR ("
            "response_status IS NOT NULL AND response_body IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="ck_idempotency_record_succeeded_fields",
        ),
        {"schema": "iam"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("iam.organization.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("iam.user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    http_method: Mapped[str] = mapped_column(String(16), nullable=False)
    route_template: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
