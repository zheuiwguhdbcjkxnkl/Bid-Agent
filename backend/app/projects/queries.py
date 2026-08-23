from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import DomainError
from app.db.models.iam import User
from app.db.models.project import BidProject, ProjectMember
from app.projects.schemas import (
    CurrentAction,
    ProjectListItem,
    ProjectOverviewResponse,
    StageProgress,
)

_ACTIVE = "ACTIVE"
_BID_MANAGER_ROLE = "BID_MANAGER"
_STAGE_SETUP = "PROJECT_SETUP"
_STAGE_NOT_STARTED = "NOT_STARTED"
_ACTION_COMPLETE_SETUP = "COMPLETE_PROJECT_SETUP"
_ACTION_COMPLETE_SETUP_LABEL = "完善项目基础信息"
_PROJECT_READ = "PROJECT_READ"
_PROJECT_UPDATE = "PROJECT_UPDATE"


async def list_projects(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    page: int,
    page_size: int,
    keyword: str | None,
    status: str | None,
    owner_user_id: UUID | None,
    only_my_projects: bool,
    sort: str,
) -> tuple[list[ProjectListItem], int]:
    owner_member = aliased(ProjectMember)
    owner_user = aliased(User)

    filters = [
        ProjectMember.user_id == actor_user_id,
        ProjectMember.assignment_status == _ACTIVE,
        owner_member.project_id == BidProject.id,
        owner_member.project_role == _BID_MANAGER_ROLE,
        owner_member.assignment_status == _ACTIVE,
    ]
    if keyword:
        filters.append(BidProject.project_name.ilike(f"%{keyword}%"))
    if status:
        filters.append(BidProject.project_status == status)
    if owner_user_id is not None:
        filters.append(owner_user.id == owner_user_id)
    if only_my_projects:
        filters.append(owner_user.id == actor_user_id)

    base = (
        select(BidProject, owner_user.id, owner_user.display_name)
        .join(ProjectMember, ProjectMember.project_id == BidProject.id)
        .join(owner_member, owner_member.project_id == BidProject.id)
        .join(owner_user, owner_user.id == owner_member.user_id)
        .where(*filters)
    )

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    if sort == "created_at":
        order = BidProject.created_at.asc()
    elif sort == "updated_at":
        order = BidProject.updated_at.asc()
    elif sort == "-updated_at":
        order = BidProject.updated_at.desc()
    else:
        order = BidProject.created_at.desc()
    rows = (
        await session.execute(base.order_by(order).offset((page - 1) * page_size).limit(page_size))
    ).all()

    items = [
        ProjectListItem(
            id=project.id,
            project_code=project.project_code,
            project_name=project.project_name,
            procurement_method=project.procurement_method,
            regime_type=project.regime_type,
            project_status=project.project_status,
            deadline_at=project.deadline_at,
            owner_user_id=owner_id,
            owner_display_name=owner_display_name,
            updated_at=project.updated_at,
        )
        for project, owner_id, owner_display_name in rows
    ]
    return items, total


async def get_project_overview(
    session: AsyncSession,
    *,
    project_id: UUID,
    actor_user_id: UUID,
) -> ProjectOverviewResponse | None:
    project = await session.get(BidProject, project_id)
    if project is None:
        return None

    membership = (
        await session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == actor_user_id,
                ProjectMember.assignment_status == _ACTIVE,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise DomainError(403, "FORBIDDEN", "无项目访问权限")

    owner_member = (
        await session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.project_role == _BID_MANAGER_ROLE,
                ProjectMember.assignment_status == _ACTIVE,
            )
        )
    ).scalar_one_or_none()
    if owner_member is None:
        raise DomainError(500, "INTERNAL_ERROR", "服务器内部错误")
    owner = await session.get(User, owner_member.user_id)
    if owner is None:
        raise DomainError(500, "INTERNAL_ERROR", "服务器内部错误")

    allowed_actions = [_PROJECT_READ]
    if owner.id == actor_user_id:
        allowed_actions.append(_PROJECT_UPDATE)

    return ProjectOverviewResponse(
        id=project.id,
        project_code=project.project_code,
        project_name=project.project_name,
        project_status=project.project_status,
        procurement_method=project.procurement_method,
        regime_type=project.regime_type,
        deadline_at=project.deadline_at,
        owner_user_id=owner.id,
        owner_display_name=owner.display_name,
        stage_progress=StageProgress(stage=_STAGE_SETUP, status=_STAGE_NOT_STARTED, percent=0),
        current_action=CurrentAction(
            code=_ACTION_COMPLETE_SETUP,
            label=_ACTION_COMPLETE_SETUP_LABEL,
        ),
        allowed_actions=allowed_actions,
        blocking_items=[],
        member_tasks=[],
        recent_changes=[],
        running_tasks=[],
    )


async def get_workbench(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
) -> list[ProjectListItem]:
    items, _ = await list_projects(
        session,
        actor_user_id=actor_user_id,
        page=1,
        page_size=5,
        keyword=None,
        status=None,
        owner_user_id=None,
        only_my_projects=False,
        sort="-updated_at",
    )
    return items
