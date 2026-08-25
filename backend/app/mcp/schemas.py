from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from app.projects.schemas import _StrictModel


class McpCallerType(StrEnum):
    CELERY_WORKER = "CELERY_WORKER"
    AGENT_RUNTIME = "AGENT_RUNTIME"
    FASTAPI = "FASTAPI"


class McpCallContext(_StrictModel):
    request_id: str
    trace_id: str
    caller_type: McpCallerType
    organization_id: UUID
    project_id: UUID
    user_id: UUID | None = None
    workflow_run_id: UUID | None = None
    agent_run_id: UUID | None = None
    skill_id: str
    skill_version: str


class DocumentIngestRequest(_StrictModel):
    task_run_id: UUID
    document_version_id: UUID
    task_type: str
    expected_content_hash: str | None = None


class DocumentSource(_StrictModel):
    task_run_id: UUID
    document_version_id: UUID
    document_parse_id: UUID
    file_name: str
    content_type: str
    content_hash: str
    content: bytes
