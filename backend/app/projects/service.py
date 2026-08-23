from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import append_audit_event
from app.auth.service import AuthenticatedContext
from app.core.errors import DomainError
from app.projects.idempotency import (
    build_project_create_scope,
    claim_or_replay,
    compute_request_hash,
    mark_succeeded,
)
from app.projects.repository import (
    ActorIdentity,
    allocate_project_code,
    assert_actor_can_create_project,
    assert_owner_eligible,
    create_member_row,
    create_package_row,
    create_project_row,
    load_owner_candidate,
)
from app.projects.schemas import CreateProjectRequest, ProjectCreatedResponse

_AUDIT_EVENT_TYPE = "PROJECT_CREATED"
_AUDIT_OBJECT_TYPE = "BID_PROJECT"
_RESOURCE_TYPE = "BID_PROJECT"
_PROJECT_CODE_CONFLICT = "PROJECT_CODE_CONFLICT"
_PROJECT_CODE_CONSTRAINT = "uq_bid_project_organization_project_code"


class ProjectCreationHooks(Protocol):
    async def after_claim(self) -> None: ...
    async def after_project(self) -> None: ...
    async def after_package(self) -> None: ...
    async def after_member(self) -> None: ...
    async def after_audit(self) -> None: ...


class NoOpProjectCreationHooks:
    async def after_claim(self) -> None:
        return None

    async def after_project(self) -> None:
        return None

    async def after_package(self) -> None:
        return None

    async def after_member(self) -> None:
        return None

    async def after_audit(self) -> None:
        return None


class ProjectCreateService:
    def __init__(
        self,
        *,
        now_provider: Callable[[], datetime],
        hooks: ProjectCreationHooks | None = None,
    ) -> None:
        self._now_provider = now_provider
        self._hooks = hooks or NoOpProjectCreationHooks()

    async def create_project(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedContext,
        payload: CreateProjectRequest,
        idempotency_key: str,
        request_id: str,
    ) -> tuple[int, ProjectCreatedResponse]:
        now = self._now_provider().astimezone(UTC)
        actor = ActorIdentity(
            user_id=context.user_id,
            organization_id=context.organization_id,
            account_status="ACTIVE",
            system_role=context.system_role,
        )
        assert_actor_can_create_project(actor)

        request_payload = payload.model_dump(mode="json")
        request_hash = compute_request_hash(request_payload)
        scope = build_project_create_scope(
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            key=idempotency_key,
        )

        async with session.begin():
            claimed = await claim_or_replay(session, scope=scope, request_hash=request_hash)
            if claimed.replay is not None:
                response_model = ProjectCreatedResponse.model_validate(claimed.replay.response_body)
                return claimed.replay.response_status, response_model

            await self._hooks.after_claim()

            owner = await load_owner_candidate(session, owner_user_id=payload.owner_user_id)
            assert_owner_eligible(actor_organization_id=context.organization_id, owner=owner)

            project_code = await allocate_project_code(session, now=now)
            try:
                project = await create_project_row(
                    session,
                    organization_id=context.organization_id,
                    project_code=project_code,
                    project_name=payload.project_name,
                    procurement_method=payload.procurement_method.value,
                    regime_type=payload.regime_type.value,
                    deadline_at=payload.deadline_at,
                )
            except IntegrityError as exc:
                if _extract_constraint_name(exc) == _PROJECT_CODE_CONSTRAINT:
                    raise DomainError(409, _PROJECT_CODE_CONFLICT, "项目编号冲突") from exc
                raise

            await self._hooks.after_project()

            package = await create_package_row(
                session,
                project_id=project.id,
                project_name=payload.project_name,
            )
            await self._hooks.after_package()

            await create_member_row(
                session,
                project_id=project.id,
                owner_user_id=payload.owner_user_id,
                assigned_at=now,
            )
            await self._hooks.after_member()

            response_model = ProjectCreatedResponse(
                id=project.id,
                project_code=project.project_code,
                project_name=project.project_name,
                project_status=project.project_status,
                owner_user_id=payload.owner_user_id,
                package_id=package.id,
                created_at=project.created_at,
            )
            response_body = response_model.model_dump(mode="json")

            await append_audit_event(
                session,
                organization_id=context.organization_id,
                project_id=project.id,
                event_type=_AUDIT_EVENT_TYPE,
                object_type=_AUDIT_OBJECT_TYPE,
                object_id=project.id,
                actor_user_id=context.user_id,
                actor_type="USER",
                request_id=request_id,
                occurred_at=now,
                after_snapshot=response_body,
            )
            await self._hooks.after_audit()

            mark_succeeded(
                claimed.record,
                status_code=201,
                body=response_body,
                resource_type=_RESOURCE_TYPE,
                resource_id=project.id,
                completed_at=now,
            )
            return 201, response_model


def _extract_constraint_name(error: IntegrityError) -> str | None:
    original_error = getattr(error, "orig", None)
    diag = getattr(original_error, "diag", None)
    return getattr(diag, "constraint_name", None)
