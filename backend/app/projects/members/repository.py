from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.db.models.iam import User
from app.db.models.project import ProjectMember

_ACTIVE = "ACTIVE"


async def load_manager_member(
    session: AsyncSession,
    *,
    project_id: UUID,
    actor_user_id: UUID,
) -> ProjectMember | None:
    result = await session.execute(
        select(ProjectMember)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == actor_user_id,
            ProjectMember.assignment_status == _ACTIVE,
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def load_member(
    session: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
) -> ProjectMember | None:
    result = await session.execute(
        select(ProjectMember)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def load_user(session: AsyncSession, *, user_id: UUID) -> User | None:
    return await session.get(User, user_id)


async def activate_member(
    session: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
    project_role: str,
    assigned_at: datetime,
) -> ProjectMember:
    existing = await load_member(session, project_id=project_id, user_id=user_id)
    if existing is not None:
        if existing.assignment_status == _ACTIVE:
            raise DomainError(409, "MEMBER_ALREADY_EXISTS", "成员已存在")
        existing.project_role = project_role
        existing.assignment_status = _ACTIVE
        existing.assigned_at = assigned_at
        await session.flush()
        return existing
    try:
        async with session.begin_nested():
            member = ProjectMember(
                project_id=project_id,
                user_id=user_id,
                project_role=project_role,
                assignment_status=_ACTIVE,
                assigned_at=assigned_at,
            )
            session.add(member)
            await session.flush()
    except IntegrityError as exc:
        if _extract_constraint_name(exc) != "pk_project_member":
            raise
        existing = await load_member(session, project_id=project_id, user_id=user_id)
        if existing is None:
            raise
        if existing.assignment_status == _ACTIVE:
            raise DomainError(409, "MEMBER_ALREADY_EXISTS", "成员已存在") from exc
        existing.project_role = project_role
        existing.assignment_status = _ACTIVE
        existing.assigned_at = assigned_at
        await session.flush()
        return existing
    return member


async def mark_member_removed(session: AsyncSession, *, member: ProjectMember) -> None:
    member.assignment_status = "REMOVED"
    await session.flush()


def _extract_constraint_name(error: IntegrityError) -> str | None:
    original_error = getattr(error, "orig", None)
    diag = getattr(original_error, "diag", None)
    return getattr(diag, "constraint_name", None)
