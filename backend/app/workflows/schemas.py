from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt, field_validator

from app.projects.schemas import _StrictModel, _validate_aware_datetime


class TaskType(StrEnum):
    RUN_WORKFLOW = "RUN_WORKFLOW"
    DOCUMENT_PARSE = "DOCUMENT_PARSE"
    OCR = "OCR"
    EMBEDDING = "EMBEDDING"
    MULTIMODAL_ANALYSIS = "MULTIMODAL_ANALYSIS"
    DOCUMENT_RENDER = "DOCUMENT_RENDER"
    DOCUMENT_EXPORT = "DOCUMENT_EXPORT"
    CONSISTENCY_CHECK = "CONSISTENCY_CHECK"
    REDELIVERY = "REDELIVERY"


class TaskStatus(StrEnum):
    QUEUED = "QUEUED"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    STALE = "STALE"


class TaskRunItem(_StrictModel):
    id: UUID
    project_id: UUID
    document_version_id: UUID | None = None
    document_parse_id: UUID | None = None
    task_type: TaskType
    task_status: TaskStatus
    current_step: str | None = None
    progress_percent: StrictInt | None = Field(default=None, ge=0, le=100)
    queued_at: AwareDatetime
    dispatched_at: AwareDatetime | None = None
    started_at: AwareDatetime | None = None
    heartbeat_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None

    @field_validator(
        "queued_at",
        "dispatched_at",
        "started_at",
        "heartbeat_at",
        "finished_at",
    )
    @classmethod
    def _validate_task_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _validate_aware_datetime(value)


class TaskRunListResponse(_StrictModel):
    items: list[TaskRunItem]
