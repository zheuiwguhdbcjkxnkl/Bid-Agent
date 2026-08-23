from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.db.models.iam import User
from app.db.models.project import BidPackage, BidProject, ProjectMember

_ACTIVE_ACCOUNT_STATUS = "ACTIVE"
_BID_MANAGER_ROLE = "BID_MANAGER"
_PRIMARY_PACKAGE_CODE = "PKG-01"
_PRIMARY_PACKAGE_NAME_MAX_LENGTH = 255
_PRIMARY_PACKAGE_NAME_SUFFIX = "主标包"
_PRIMARY_PACKAGE_STATUS = "ACTIVE"
_PROJECT_MEMBER_STATUS_ACTIVE = "ACTIVE"
_PROJECT_STATUS_DRAFT = "DRAFT"


@dataclass(slots=True)
class ActorIdentity:
    user_id: UUID
    organization_id: UUID
    account_status: str
    system_role: str


@dataclass(slots=True)
class OwnerCandidate:
    user_id: UUID
    organization_id: UUID
    account_status: str
    system_role: str


def assert_actor_can_create_project(actor: ActorIdentity) -> None:
    if actor.account_status != _ACTIVE_ACCOUNT_STATUS:
        raise DomainError(status_code=403, code="FORBIDDEN", message="当前账号不可创建项目")
    if actor.system_role != _BID_MANAGER_ROLE:
        raise DomainError(status_code=403, code="FORBIDDEN", message="当前角色不可创建项目")


def assert_owner_eligible(*, actor_organization_id: UUID, owner: OwnerCandidate | None) -> None:
    if owner is None:
        raise DomainError(
            status_code=422,
            code="OWNER_ROLE_MISMATCH",
            message="项目负责人不存在或不可用",
        )
    if owner.organization_id != actor_organization_id:
        raise DomainError(
            status_code=422,
            code="OWNER_ORGANIZATION_MISMATCH",
            message="项目负责人与当前组织不一致",
        )
    if owner.account_status != _ACTIVE_ACCOUNT_STATUS:
        raise DomainError(
            status_code=422,
            code="OWNER_ROLE_MISMATCH",
            message="项目负责人不存在或不可用",
        )
    if owner.system_role != _BID_MANAGER_ROLE:
        raise DomainError(
            status_code=422,
            code="OWNER_ROLE_MISMATCH",
            message="项目负责人不存在或不可用",
        )


async def load_owner_candidate(
    session: AsyncSession,
    *,
    owner_user_id: UUID,
) -> OwnerCandidate | None:
    statement = select(User).where(User.id == owner_user_id).with_for_update()
    result = await session.execute(statement)
    user = result.scalar_one_or_none()
    if user is None:
        return None
    return OwnerCandidate(
        user_id=user.id,
        organization_id=user.organization_id,
        account_status=user.account_status,
        system_role=user.system_role,
    )


async def allocate_project_code(session: AsyncSession, *, now: datetime) -> str:
    result = await session.execute(text("SELECT nextval('project.project_code_seq')"))
    sequence_value = result.scalar_one()
    return f"BID-{now.year}-{sequence_value:04d}"


async def create_project_row(
    session: AsyncSession,
    *,
    organization_id: UUID,
    project_code: str,
    project_name: str,
    procurement_method: str,
    regime_type: str,
    deadline_at: datetime,
) -> BidProject:
    project = BidProject(
        organization_id=organization_id,
        project_code=project_code,
        project_name=project_name,
        procurement_method=procurement_method,
        regime_type=regime_type,
        project_status=_PROJECT_STATUS_DRAFT,
        deadline_at=deadline_at,
    )
    session.add(project)
    await session.flush()
    return project


async def create_package_row(
    session: AsyncSession,
    *,
    project_id: UUID,
    project_name: str,
) -> BidPackage:
    package_name_prefix_length = _PRIMARY_PACKAGE_NAME_MAX_LENGTH - len(
        _PRIMARY_PACKAGE_NAME_SUFFIX
    )
    package = BidPackage(
        project_id=project_id,
        package_code=_PRIMARY_PACKAGE_CODE,
        package_name=f"{project_name[:package_name_prefix_length]}{_PRIMARY_PACKAGE_NAME_SUFFIX}",
        package_status=_PRIMARY_PACKAGE_STATUS,
        is_v1_primary=True,
    )
    session.add(package)
    await session.flush()
    return package


async def create_member_row(
    session: AsyncSession,
    *,
    project_id: UUID,
    owner_user_id: UUID,
    assigned_at: datetime,
) -> ProjectMember:
    member = ProjectMember(
        project_id=project_id,
        user_id=owner_user_id,
        project_role=_BID_MANAGER_ROLE,
        assignment_status=_PROJECT_MEMBER_STATUS_ACTIVE,
        assigned_at=assigned_at,
    )
    session.add(member)
    await session.flush()
    return member
