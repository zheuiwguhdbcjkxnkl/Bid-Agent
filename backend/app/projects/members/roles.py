from __future__ import annotations

from app.core.errors import DomainError

# system_role -> 允许承担的 project_role 集合
PROJECT_ROLES_BY_SYSTEM_ROLE: dict[str, set[str]] = {
    "BID_MANAGER": {"BID_MANAGER", "SUBMISSION_OWNER"},
    "COMMERCIAL_WRITER": {"BID_WRITER", "PRICING_OWNER"},
    "TECHNICAL_WRITER": {"TECHNICAL_WRITER"},
    "COMPLIANCE_REVIEWER": {"COMMERCIAL_REVIEWER", "COMPLIANCE_LEGAL_REVIEWER"},
    "MATERIAL_ADMIN": set(),
    "ADMIN": set(),
}

_MANAGER_ROLE = "BID_MANAGER"


def assert_actor_is_manager(actor_role: str) -> None:
    """校验操作者是项目负责人。"""
    if actor_role != _MANAGER_ROLE:
        raise DomainError(403, "FORBIDDEN", "仅项目负责人可管理成员")


def assert_role_assignment_allowed(*, system_role: str, project_role: str) -> None:
    """校验目标成员的平台角色允许承担指定项目职责。"""
    if project_role == _MANAGER_ROLE:
        raise DomainError(403, "FORBIDDEN", "负责人职责不可分配")
    allowed = PROJECT_ROLES_BY_SYSTEM_ROLE.get(system_role, set())
    if project_role not in allowed:
        raise DomainError(422, "MEMBER_ROLE_MISMATCH", "成员平台角色与项目职责不兼容")
