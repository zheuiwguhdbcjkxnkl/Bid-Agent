from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.db.models.iam import User
from app.db.models.project import ProjectMember
from app.projects.members.schemas import MemberItem

_ACTIVE = "ACTIVE"


async def list_members(
    session: AsyncSession,
    *,
    project_id: UUID,
    actor_user_id: UUID,
) -> list[MemberItem]:
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

    rows = (
        await session.execute(
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.assignment_status == _ACTIVE,
            )
            .order_by(ProjectMember.assigned_at.asc())
        )
    ).all()
    return [
        MemberItem(
            user_id=member.user_id,
            display_name=user.display_name,
            project_role=member.project_role,
            assigned_at=member.assigned_at,
        )
        for member, user in rows
    ]
