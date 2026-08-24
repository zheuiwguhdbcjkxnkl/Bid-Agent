from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import append_audit_event
from app.auth.service import AuthenticatedContext
from app.core.errors import DomainError
from app.projects.idempotency import (
    build_member_add_scope,
    claim_or_replay,
    compute_request_hash,
    mark_succeeded,
)
from app.projects.members import repository
from app.projects.members.roles import assert_actor_is_manager, assert_role_assignment_allowed
from app.projects.members.schemas import AddMemberRequest, MemberItem

_ACTIVE = "ACTIVE"
_REMOVED = "REMOVED"
_AUDIT_EVENT_ADDED = "MEMBER_ADDED"
_AUDIT_EVENT_REMOVED = "MEMBER_REMOVED"
_AUDIT_EVENT_ROLE_CHANGED = "MEMBER_ROLE_CHANGED"
_AUDIT_OBJECT_TYPE = "PROJECT_MEMBER"


class MemberService:
    def __init__(self, *, now_provider: Callable[[], datetime]) -> None:
        self._now_provider = now_provider

    async def add_member(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedContext,
        project_id: UUID,
        payload: AddMemberRequest,
        idempotency_key: str,
        request_id: str,
    ) -> tuple[int, MemberItem]:
        now = self._now_provider().astimezone(UTC)
        request_payload = payload.model_dump(mode="json")
        request_hash = compute_request_hash(request_payload)
        scope = build_member_add_scope(
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            project_id=project_id,
            key=idempotency_key,
        )

        async with session.begin():
            manager = await repository.load_manager_member(
                session, project_id=project_id, actor_user_id=context.user_id
            )
            if manager is None:
                raise DomainError(403, "FORBIDDEN", "仅项目负责人可管理成员")
            assert_actor_is_manager(manager.project_role)

            claimed = await claim_or_replay(session, scope=scope, request_hash=request_hash)
            if claimed.replay is not None:
                return claimed.replay.response_status, MemberItem.model_validate(
                    claimed.replay.response_body
                )

            user = await repository.load_user(session, user_id=payload.user_id)
            if user is None:
                raise DomainError(404, "MEMBER_NOT_FOUND", "成员不存在")
            if user.organization_id != context.organization_id:
                raise DomainError(422, "MEMBER_ROLE_MISMATCH", "成员不属于当前组织")
            if user.account_status != _ACTIVE:
                raise DomainError(422, "MEMBER_ROLE_MISMATCH", "成员账号不可用")
            assert_role_assignment_allowed(
                system_role=user.system_role, project_role=payload.project_role.value
            )

            member = await repository.activate_member(
                session,
                project_id=project_id,
                user_id=payload.user_id,
                project_role=payload.project_role.value,
                assigned_at=now,
            )

            item = MemberItem(
                user_id=member.user_id,
                display_name=user.display_name,
                project_role=member.project_role,
                assigned_at=member.assigned_at,
            )
            response_body = item.model_dump(mode="json")

            await append_audit_event(
                session,
                organization_id=context.organization_id,
                project_id=project_id,
                event_type=_AUDIT_EVENT_ADDED,
                object_type=_AUDIT_OBJECT_TYPE,
                object_id=member.user_id,
                actor_user_id=context.user_id,
                request_id=request_id,
                occurred_at=now,
                after_snapshot=response_body,
            )

            mark_succeeded(
                claimed.record,
                status_code=201,
                body=response_body,
                resource_type=_AUDIT_OBJECT_TYPE,
                resource_id=member.user_id,
                completed_at=now,
            )
            return 201, item

    async def remove_member(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedContext,
        project_id: UUID,
        user_id: UUID,
        request_id: str,
    ) -> None:
        now = self._now_provider().astimezone(UTC)
        async with session.begin():
            manager = await repository.load_manager_member(
                session, project_id=project_id, actor_user_id=context.user_id
            )
            if manager is None:
                raise DomainError(403, "FORBIDDEN", "仅项目负责人可管理成员")
            assert_actor_is_manager(manager.project_role)
            member = await repository.load_member(session, project_id=project_id, user_id=user_id)
            if member is None:
                raise DomainError(404, "MEMBER_NOT_FOUND", "成员不存在")
            if member.assignment_status == _REMOVED:
                return
            if member.project_role == "BID_MANAGER":
                raise DomainError(403, "FORBIDDEN", "项目负责人不可移除")
            before_snapshot = {"project_role": member.project_role}
            await repository.mark_member_removed(session, member=member)
            await append_audit_event(
                session,
                organization_id=context.organization_id,
                project_id=project_id,
                event_type=_AUDIT_EVENT_REMOVED,
                object_type=_AUDIT_OBJECT_TYPE,
                object_id=member.user_id,
                actor_user_id=context.user_id,
                request_id=request_id,
                occurred_at=now,
                before_snapshot=before_snapshot,
            )

    async def update_role(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedContext,
        project_id: UUID,
        user_id: UUID,
        project_role: str,
        request_id: str,
    ) -> MemberItem:
        now = self._now_provider().astimezone(UTC)
        async with session.begin():
            manager = await repository.load_manager_member(
                session, project_id=project_id, actor_user_id=context.user_id
            )
            if manager is None:
                raise DomainError(403, "FORBIDDEN", "仅项目负责人可管理成员")
            assert_actor_is_manager(manager.project_role)
            member = await repository.load_member(session, project_id=project_id, user_id=user_id)
            if member is None or member.assignment_status == _REMOVED:
                raise DomainError(404, "MEMBER_NOT_FOUND", "成员不存在或已移除")
            if member.project_role == "BID_MANAGER":
                raise DomainError(403, "FORBIDDEN", "项目负责人职责不可变更")
            user = await repository.load_user(session, user_id=user_id)
            if user is None:
                raise DomainError(404, "MEMBER_NOT_FOUND", "成员不存在")
            assert_role_assignment_allowed(system_role=user.system_role, project_role=project_role)
            before_role = member.project_role
            member.project_role = project_role
            await session.flush()
            item = MemberItem(
                user_id=member.user_id,
                display_name=user.display_name,
                project_role=member.project_role,
                assigned_at=member.assigned_at,
            )
            if before_role != project_role:
                await append_audit_event(
                    session,
                    organization_id=context.organization_id,
                    project_id=project_id,
                    event_type=_AUDIT_EVENT_ROLE_CHANGED,
                    object_type=_AUDIT_OBJECT_TYPE,
                    object_id=member.user_id,
                    actor_user_id=context.user_id,
                    request_id=request_id,
                    occurred_at=now,
                    before_snapshot={"project_role": before_role},
                    after_snapshot={"project_role": project_role},
                )
            return item
