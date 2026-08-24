from __future__ import annotations

import pytest

from app.core.errors import DomainError
from app.projects.members.roles import (
    assert_actor_is_manager,
    assert_role_assignment_allowed,
)


def test_allows_manager_role_for_bid_manager_system_role() -> None:
    assert_role_assignment_allowed(system_role="BID_MANAGER", project_role="SUBMISSION_OWNER")


def test_allows_writer_role_for_commercial_writer() -> None:
    assert_role_assignment_allowed(system_role="COMMERCIAL_WRITER", project_role="BID_WRITER")


def test_allows_pricing_owner_for_commercial_writer() -> None:
    assert_role_assignment_allowed(system_role="COMMERCIAL_WRITER", project_role="PRICING_OWNER")


def test_allows_technical_writer_for_technical_writer() -> None:
    assert_role_assignment_allowed(system_role="TECHNICAL_WRITER", project_role="TECHNICAL_WRITER")


def test_allows_compliance_roles_for_compliance_reviewer() -> None:
    assert_role_assignment_allowed(
        system_role="COMPLIANCE_REVIEWER", project_role="COMMERCIAL_REVIEWER"
    )
    assert_role_assignment_allowed(
        system_role="COMPLIANCE_REVIEWER", project_role="COMPLIANCE_LEGAL_REVIEWER"
    )


def test_rejects_mismatched_role() -> None:
    with pytest.raises(DomainError) as exc:
        assert_role_assignment_allowed(system_role="TECHNICAL_WRITER", project_role="BID_WRITER")
    assert exc.value.code == "MEMBER_ROLE_MISMATCH"


def test_rejects_manager_role_assignment() -> None:
    with pytest.raises(DomainError) as exc:
        assert_role_assignment_allowed(system_role="BID_MANAGER", project_role="BID_MANAGER")
    assert exc.value.status_code == 403
    assert exc.value.code == "FORBIDDEN"


def test_rejects_material_admin_as_member() -> None:
    with pytest.raises(DomainError) as exc:
        assert_role_assignment_allowed(system_role="MATERIAL_ADMIN", project_role="BID_WRITER")
    assert exc.value.code == "MEMBER_ROLE_MISMATCH"


def test_assert_actor_is_manager_allows_manager() -> None:
    assert_actor_is_manager(actor_role="BID_MANAGER")


def test_assert_actor_is_manager_rejects_non_manager() -> None:
    with pytest.raises(DomainError) as exc:
        assert_actor_is_manager(actor_role="BID_WRITER")
    assert exc.value.code == "FORBIDDEN"
