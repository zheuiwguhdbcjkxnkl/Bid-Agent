from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.projects.members.schemas import (
    AddMemberRequest,
    MemberItem,
    MemberListResponse,
    UpdateMemberRoleRequest,
)


def test_add_member_request_accepts_valid_role() -> None:
    request = AddMemberRequest(user_id=uuid4(), project_role="BID_WRITER")
    assert request.project_role == "BID_WRITER"


def test_add_member_request_rejects_invalid_role() -> None:
    with pytest.raises(ValidationError):
        AddMemberRequest(user_id=uuid4(), project_role="NOT_A_ROLE")


def test_add_member_request_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        AddMemberRequest.model_validate(
            {"user_id": uuid4(), "project_role": "BID_WRITER", "extra": 1}
        )


def test_member_item_serializes_assigned_at() -> None:
    assigned_at = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)
    item = MemberItem(
        user_id=uuid4(),
        display_name="张三",
        project_role="BID_WRITER",
        assigned_at=assigned_at,
    )
    assert item.assigned_at == assigned_at


def test_member_list_response_shape() -> None:
    response = MemberListResponse(items=[])
    assert response.items == []


def test_update_member_role_request() -> None:
    request = UpdateMemberRoleRequest(project_role="PRICING_OWNER")
    assert request.project_role == "PRICING_OWNER"
