from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.errors import DomainError
from app.projects.idempotency import IdempotencyReplay
from app.projects.repository import (
    ActorIdentity,
    OwnerCandidate,
    assert_actor_can_create_project,
    assert_owner_eligible,
)
from app.projects.schemas import CreateProjectRequest, ProjectCreatedResponse


class TestIdempotencyReplay:
    def test_uses_approved_response_field_names(self) -> None:
        replay = IdempotencyReplay(
            response_status=201,
            response_body={"project_status": "DRAFT"},
        )

        assert replay.response_status == 201
        assert replay.response_body == {"project_status": "DRAFT"}


class TestCreateProjectRequest:
    def test_accepts_valid_payload_and_preserves_internal_spaces(self) -> None:
        owner_user_id = uuid4()
        deadline_at = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        payload = {
            "project_name": "政务云  平台 运维 服务采购项目",
            "procurement_method": "PUBLIC_TENDER",
            "regime_type": "GOVERNMENT_PROCUREMENT",
            "deadline_at": deadline_at,
            "owner_user_id": owner_user_id,
        }

        request = CreateProjectRequest.model_validate(payload)

        assert request.project_name == "政务云  平台 运维 服务采购项目"
        assert request.procurement_method == "PUBLIC_TENDER"
        assert request.regime_type == "GOVERNMENT_PROCUREMENT"
        assert request.deadline_at == deadline_at
        assert request.owner_user_id == owner_user_id

    @pytest.mark.parametrize(
        ("field_name", "field_value"),
        [
            ("project_source", "GOV_PLATFORM"),
            ("external_project_code", "XMBH-001"),
            ("unexpected", "value"),
        ],
    )
    def test_rejects_extra_fields(self, field_name: str, field_value: str) -> None:
        payload = {
            "project_name": "政务云平台运维服务采购项目",
            "procurement_method": "PUBLIC_TENDER",
            "regime_type": "GOVERNMENT_PROCUREMENT",
            "deadline_at": datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
            "owner_user_id": uuid4(),
            field_name: field_value,
        }

        with pytest.raises(ValidationError) as exc_info:
            CreateProjectRequest.model_validate(payload)

        assert exc_info.value.errors()[0]["type"] == "extra_forbidden"

    @pytest.mark.parametrize(
        "missing_field",
        [
            "project_name",
            "procurement_method",
            "regime_type",
            "deadline_at",
            "owner_user_id",
        ],
    )
    def test_requires_all_fields(self, missing_field: str) -> None:
        payload = {
            "project_name": "政务云平台运维服务采购项目",
            "procurement_method": "PUBLIC_TENDER",
            "regime_type": "GOVERNMENT_PROCUREMENT",
            "deadline_at": datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
            "owner_user_id": uuid4(),
        }
        del payload[missing_field]

        with pytest.raises(ValidationError) as exc_info:
            CreateProjectRequest.model_validate(payload)

        assert exc_info.value.errors()[0]["type"] == "missing"

    @pytest.mark.parametrize("project_name", ["", "   ", "\t\n"])
    def test_rejects_blank_project_name(self, project_name: str) -> None:
        payload = {
            "project_name": project_name,
            "procurement_method": "PUBLIC_TENDER",
            "regime_type": "GOVERNMENT_PROCUREMENT",
            "deadline_at": datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
            "owner_user_id": uuid4(),
        }

        with pytest.raises(ValidationError) as exc_info:
            CreateProjectRequest.model_validate(payload)

        assert exc_info.value.errors()[0]["loc"] == ("project_name",)

    def test_rejects_invalid_procurement_method(self) -> None:
        payload = {
            "project_name": "政务云平台运维服务采购项目",
            "procurement_method": "INVALID_METHOD",
            "regime_type": "GOVERNMENT_PROCUREMENT",
            "deadline_at": datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
            "owner_user_id": uuid4(),
        }

        with pytest.raises(ValidationError) as exc_info:
            CreateProjectRequest.model_validate(payload)

        assert exc_info.value.errors()[0]["loc"] == ("procurement_method",)

    def test_rejects_invalid_regime_type(self) -> None:
        payload = {
            "project_name": "政务云平台运维服务采购项目",
            "procurement_method": "PUBLIC_TENDER",
            "regime_type": "INVALID_REGIME",
            "deadline_at": datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
            "owner_user_id": uuid4(),
        }

        with pytest.raises(ValidationError) as exc_info:
            CreateProjectRequest.model_validate(payload)

        assert exc_info.value.errors()[0]["loc"] == ("regime_type",)

    def test_rejects_naive_deadline(self) -> None:
        payload = {
            "project_name": "政务云平台运维服务采购项目",
            "procurement_method": "PUBLIC_TENDER",
            "regime_type": "GOVERNMENT_PROCUREMENT",
            "deadline_at": datetime(2026, 8, 21, 12, 0),
            "owner_user_id": uuid4(),
        }

        with pytest.raises(ValidationError) as exc_info:
            CreateProjectRequest.model_validate(payload)

        assert exc_info.value.errors()[0]["loc"] == ("deadline_at",)


class TestProjectCreatedResponse:
    def test_requires_aware_created_at(self) -> None:
        payload = {
            "id": uuid4(),
            "project_code": "XM20260821001",
            "project_name": "政务云平台运维服务采购项目",
            "project_status": "DRAFT",
            "owner_user_id": uuid4(),
            "package_id": uuid4(),
            "created_at": datetime(2026, 8, 21, 12, 0),
        }

        with pytest.raises(ValidationError) as exc_info:
            ProjectCreatedResponse.model_validate(payload)

        assert exc_info.value.errors()[0]["loc"] == ("created_at",)


class TestActorProjectPolicy:
    def test_allows_active_bid_manager_to_create_project(self) -> None:
        actor = ActorIdentity(
            user_id=uuid4(),
            organization_id=uuid4(),
            account_status="ACTIVE",
            system_role="BID_MANAGER",
        )

        assert_actor_can_create_project(actor)

    @pytest.mark.parametrize(
        ("account_status", "system_role"),
        [
            ("DISABLED", "BID_MANAGER"),
            ("LOCKED", "BID_MANAGER"),
            ("ACTIVE", "VIEWER"),
        ],
    )
    def test_rejects_ineligible_actor(self, account_status: str, system_role: str) -> None:
        actor = ActorIdentity(
            user_id=uuid4(),
            organization_id=uuid4(),
            account_status=account_status,
            system_role=system_role,
        )

        with pytest.raises(DomainError) as exc_info:
            assert_actor_can_create_project(actor)

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "FORBIDDEN"


class TestOwnerEligibility:
    def test_rejects_missing_owner(self) -> None:
        with pytest.raises(DomainError) as exc_info:
            assert_owner_eligible(actor_organization_id=uuid4(), owner=None)

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "OWNER_ROLE_MISMATCH"

    def test_rejects_cross_organization_before_status_or_role_checks(self) -> None:
        owner = OwnerCandidate(
            user_id=uuid4(),
            organization_id=uuid4(),
            account_status="DISABLED",
            system_role="VIEWER",
        )

        with pytest.raises(DomainError) as exc_info:
            assert_owner_eligible(actor_organization_id=uuid4(), owner=owner)

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "OWNER_ORGANIZATION_MISMATCH"

    @pytest.mark.parametrize(
        ("account_status", "system_role"),
        [
            ("DISABLED", "BID_MANAGER"),
            ("LOCKED", "BID_MANAGER"),
            ("ACTIVE", "VIEWER"),
        ],
    )
    def test_rejects_owner_with_wrong_status_or_role(
        self,
        account_status: str,
        system_role: str,
    ) -> None:
        organization_id = uuid4()
        owner = OwnerCandidate(
            user_id=uuid4(),
            organization_id=organization_id,
            account_status=account_status,
            system_role=system_role,
        )

        with pytest.raises(DomainError) as exc_info:
            assert_owner_eligible(actor_organization_id=organization_id, owner=owner)

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "OWNER_ROLE_MISMATCH"

    def test_accepts_active_bid_manager_in_same_organization(self) -> None:
        organization_id = uuid4()
        owner = OwnerCandidate(
            user_id=uuid4(),
            organization_id=organization_id,
            account_status="ACTIVE",
            system_role="BID_MANAGER",
        )

        assert_owner_eligible(actor_organization_id=organization_id, owner=owner)
