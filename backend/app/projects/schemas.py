from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_AWARE_DATETIME_ERROR = "必须使用带时区的时间"
_PROJECT_STATUS_DRAFT = "DRAFT"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProcurementMethod(StrEnum):
    PUBLIC_TENDER = "PUBLIC_TENDER"
    INVITED_TENDER = "INVITED_TENDER"
    COMPETITIVE_NEGOTIATION = "COMPETITIVE_NEGOTIATION"
    COMPETITIVE_CONSULTATION = "COMPETITIVE_CONSULTATION"
    INQUIRY = "INQUIRY"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    OTHER = "OTHER"


class RegimeType(StrEnum):
    GOVERNMENT_PROCUREMENT = "GOVERNMENT_PROCUREMENT"
    TENDER_BIDDING = "TENDER_BIDDING"


def _validate_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(_AWARE_DATETIME_ERROR)
    return value.astimezone(UTC)


class CreateProjectRequest(_StrictModel):
    project_name: str = Field(min_length=1, max_length=255)
    procurement_method: ProcurementMethod
    regime_type: RegimeType
    deadline_at: datetime
    owner_user_id: UUID

    @field_validator("project_name", mode="before")
    @classmethod
    def _normalize_project_name(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        return value.strip()

    @field_validator("project_name")
    @classmethod
    def _validate_project_name(cls, value: str) -> str:
        if not value:
            raise ValueError("项目名称不能为空白")
        return value

    @field_validator("deadline_at")
    @classmethod
    def _validate_deadline_at(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)


class ProjectCreatedResponse(_StrictModel):
    id: UUID
    project_code: str
    project_name: str = Field(min_length=1, max_length=255)
    project_status: str
    owner_user_id: UUID
    package_id: UUID
    created_at: datetime

    @field_validator("project_status")
    @classmethod
    def _validate_project_status(cls, value: str) -> str:
        if value != _PROJECT_STATUS_DRAFT:
            raise ValueError("项目状态必须为 DRAFT")
        return value

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)


class ProjectListItem(_StrictModel):
    id: UUID
    project_code: str
    project_name: str
    procurement_method: str
    regime_type: str
    project_status: str
    deadline_at: datetime | None
    owner_user_id: UUID
    owner_display_name: str
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def _validate_updated_at(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)


class ProjectListResponse(_StrictModel):
    items: list[ProjectListItem]
    page: int
    page_size: int
    total: int


class StageProgress(_StrictModel):
    stage: str
    status: str
    percent: int


class CurrentAction(_StrictModel):
    code: str
    label: str


class ProjectOverviewResponse(_StrictModel):
    id: UUID
    project_code: str
    project_name: str
    project_status: str
    procurement_method: str
    regime_type: str
    deadline_at: datetime | None
    owner_user_id: UUID
    owner_display_name: str
    stage_progress: StageProgress
    current_action: CurrentAction
    allowed_actions: list[str]
    blocking_items: list[dict[str, Any]]
    member_tasks: list[dict[str, Any]]
    recent_changes: list[dict[str, Any]]
    running_tasks: list[dict[str, Any]]


class WorkbenchTodo(_StrictModel):
    project_id: UUID
    code: str
    label: str
    deadline_at: datetime | None


class WorkbenchTask(_StrictModel):
    task_run_id: UUID
    state: str
    stage: str
    progress: int
    failed_reason: str | None


class WorkbenchResponse(_StrictModel):
    personal_todos: list[WorkbenchTodo]
    recent_projects: list[ProjectListItem]
    running_tasks: list[WorkbenchTask]
    failed_tasks: list[WorkbenchTask]
