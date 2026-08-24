from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import field_validator

from app.projects.schemas import _StrictModel, _validate_aware_datetime


class ProjectRole(StrEnum):
    BID_MANAGER = "BID_MANAGER"
    BID_WRITER = "BID_WRITER"
    TECHNICAL_WRITER = "TECHNICAL_WRITER"
    PRICING_OWNER = "PRICING_OWNER"
    COMMERCIAL_REVIEWER = "COMMERCIAL_REVIEWER"
    COMPLIANCE_LEGAL_REVIEWER = "COMPLIANCE_LEGAL_REVIEWER"
    SUBMISSION_OWNER = "SUBMISSION_OWNER"


class AddMemberRequest(_StrictModel):
    user_id: UUID
    project_role: ProjectRole


class UpdateMemberRoleRequest(_StrictModel):
    project_role: ProjectRole


class MemberItem(_StrictModel):
    user_id: UUID
    display_name: str
    project_role: str
    assigned_at: datetime

    @field_validator("assigned_at")
    @classmethod
    def _validate_assigned_at(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)


class MemberListResponse(_StrictModel):
    items: list[MemberItem]
