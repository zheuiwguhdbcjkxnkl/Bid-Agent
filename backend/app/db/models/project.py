from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BidProject(Base):
    __tablename__ = "bid_project"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "project_code", name="uq_bid_project_organization_project_code"
        ),
        CheckConstraint(
            "procurement_method IN ('PUBLIC_TENDER', 'INVITED_TENDER', 'COMPETITIVE_NEGOTIATION', "
            "'COMPETITIVE_CONSULTATION', 'INQUIRY', 'SINGLE_SOURCE', 'OTHER')",
            name="ck_bid_project_procurement_method",
        ),
        CheckConstraint(
            "regime_type IN ('GOVERNMENT_PROCUREMENT', 'TENDER_BIDDING')",
            name="ck_bid_project_regime_type",
        ),
        CheckConstraint("project_status IN ('DRAFT')", name="ck_bid_project_project_status"),
        CheckConstraint(
            "external_ai_policy IN ('PUBLIC_ONLY', 'ALLOW_INTERNAL', 'ALLOW_CONFIDENTIAL')",
            name="ck_bid_project_external_ai_policy",
        ),
        {"schema": "project"},
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
    project_code: Mapped[str] = mapped_column(String(64), nullable=False)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    procurement_method: Mapped[str] = mapped_column(String(64), nullable=False)
    regime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    project_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'DRAFT'"),
    )
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_ai_policy: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'PUBLIC_ONLY'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class BidPackage(Base):
    __tablename__ = "bid_package"
    __table_args__ = (
        UniqueConstraint("project_id", "package_code", name="uq_bid_package_project_package_code"),
        CheckConstraint(
            "package_status IN ('ACTIVE', 'NOT_BIDDING')", name="ck_bid_package_package_status"
        ),
        Index(
            "uq_bid_package_single_primary",
            "project_id",
            unique=True,
            postgresql_where=text("is_v1_primary IS TRUE"),
        ),
        {"schema": "project"},
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
    package_code: Mapped[str] = mapped_column(String(64), nullable=False)
    package_name: Mapped[str] = mapped_column(String(255), nullable=False)
    package_status: Mapped[str] = mapped_column(String(32), nullable=False)
    is_v1_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ProjectMember(Base):
    __tablename__ = "project_member"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "user_id", name="pk_project_member"),
        CheckConstraint(
            "project_role IN ('BID_MANAGER', 'BID_WRITER', 'TECHNICAL_WRITER', 'PRICING_OWNER', "
            "'COMMERCIAL_REVIEWER', 'COMPLIANCE_LEGAL_REVIEWER', 'SUBMISSION_OWNER')",
            name="ck_project_member_project_role",
        ),
        CheckConstraint(
            "assignment_status IN ('ACTIVE', 'REMOVED')",
            name="ck_project_member_assignment_status",
        ),
        {"schema": "project"},
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project.bid_project.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("iam.user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_role: Mapped[str] = mapped_column(String(64), nullable=False)
    assignment_status: Mapped[str] = mapped_column(String(32), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
