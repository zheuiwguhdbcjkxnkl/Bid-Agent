from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.projects.documents.parse_schemas import StartDocumentParseResponse
from app.workflows.schemas import TaskRunItem, TaskRunListResponse


def _task_run_values() -> dict[str, object]:
    return {
        "id": uuid4(),
        "project_id": uuid4(),
        "document_version_id": uuid4(),
        "document_parse_id": uuid4(),
        "task_type": "DOCUMENT_PARSE",
        "task_status": "QUEUED",
        "current_step": None,
        "progress_percent": 0,
        "queued_at": datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
        "started_at": None,
        "finished_at": None,
        "last_error_code": None,
        "last_error_message": None,
    }


def test_task_run_item_and_responses_accept_strict_contract() -> None:
    item = TaskRunItem.model_validate(_task_run_values())
    response = TaskRunListResponse(items=[item])
    start_response = StartDocumentParseResponse(task_run=item)

    assert response.items == [item]
    assert start_response.task_run == item


def test_task_run_item_rejects_invalid_uuid_status_progress_and_naive_datetime() -> None:
    values = _task_run_values()

    with pytest.raises(ValidationError):
        TaskRunItem.model_validate({**values, "id": "not-a-uuid"})
    with pytest.raises(ValidationError):
        TaskRunItem.model_validate({**values, "task_status": "UNKNOWN"})
    with pytest.raises(ValidationError):
        TaskRunItem.model_validate({**values, "progress_percent": -1})
    with pytest.raises(ValidationError):
        TaskRunItem.model_validate({**values, "progress_percent": 101})
    with pytest.raises(ValidationError):
        TaskRunItem.model_validate({**values, "queued_at": datetime(2026, 8, 24, 9, 0)})


def test_task_run_responses_reject_extra_fields() -> None:
    item = TaskRunItem.model_validate(_task_run_values())

    with pytest.raises(ValidationError):
        TaskRunListResponse.model_validate({"items": [item], "unexpected": True})
    with pytest.raises(ValidationError):
        StartDocumentParseResponse.model_validate({"task_run": item, "unexpected": True})
