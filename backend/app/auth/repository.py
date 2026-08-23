from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.iam import Organization, User, UserSession


def normalize_login_name(value: str) -> str:
    return value.strip().lower()


@dataclass(slots=True)
class LoginUserRecord:
    id: UUID
    organization_id: UUID
    login_name: str
    display_name: str
    account_status: str
    system_role: str
    password_hash: str
    must_change_password: bool


async def find_organization_by_tenant_key(
    session: AsyncSession,
    tenant_key: str,
) -> Organization | None:
    statement = select(Organization).where(Organization.tenant_key == tenant_key)
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def find_user_for_login(
    session: AsyncSession,
    *,
    organization_id: UUID,
    login_name: str,
) -> LoginUserRecord | None:
    normalized_login_name = normalize_login_name(login_name)
    statement = select(User).where(
        User.organization_id == organization_id,
        User.login_name == normalized_login_name,
    )
    result = await session.execute(statement)
    user = result.scalar_one_or_none()
    if user is None:
        return None
    return LoginUserRecord(
        id=user.id,
        organization_id=user.organization_id,
        login_name=user.login_name,
        display_name=user.display_name,
        account_status=user.account_status,
        system_role=user.system_role,
        password_hash=user.password_hash,
        must_change_password=user.must_change_password,
    )


@dataclass(slots=True)
class UserSessionRecord:
    session: UserSession
    user: User


async def find_session_by_token_hash(
    session: AsyncSession,
    *,
    token_hash: str,
    for_update: bool,
) -> UserSessionRecord | None:
    statement = (
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == token_hash)
    )
    if for_update:
        statement = statement.with_for_update()

    result = await session.execute(statement)
    row = result.first()
    if row is None:
        return None
    db_session, user = row
    return UserSessionRecord(session=db_session, user=user)


async def find_user_by_id_for_update(session: AsyncSession, *, user_id: UUID) -> User | None:
    statement = select(User).where(User.id == user_id).with_for_update()
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def find_other_active_sessions_for_update(
    session: AsyncSession,
    *,
    user_id: UUID,
    current_session_id: UUID,
) -> list[UserSession]:
    statement = (
        select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.id != current_session_id,
            UserSession.revoked_at.is_(None),
        )
        .with_for_update()
    )
    result = await session.execute(statement)
    return list(result.scalars().all())
