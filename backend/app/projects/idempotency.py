from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.db.models.iam import IdempotencyRecord

_IDEMPOTENCY_REQUIRED_CODE = "IDEMPOTENCY_KEY_REQUIRED"
_IDEMPOTENCY_REQUIRED_MESSAGE = "请求缺少有效的 Idempotency-Key"
_IDEMPOTENCY_CONFLICT_CODE = "IDEMPOTENCY_CONFLICT"
_ROUTE_TEMPLATE = "/api/v1/projects"
_HTTP_METHOD_POST = "POST"
_PROCESSING = "PROCESSING"
_SUCCEEDED = "SUCCEEDED"
_SCOPE_CONSTRAINT_NAME = "uq_idempotency_record_scope"


@dataclass(frozen=True, slots=True)
class IdempotencyScope:
    organization_id: UUID
    actor_user_id: UUID
    http_method: str
    route_template: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class IdempotencyReplay:
    response_status: int
    response_body: dict[str, object]


@dataclass(frozen=True, slots=True)
class IdempotencyClaimed:
    record: IdempotencyRecord
    replay: IdempotencyReplay | None


def normalize_idempotency_key(raw_value: str | None) -> str:
    if raw_value is None:
        raise DomainError(400, _IDEMPOTENCY_REQUIRED_CODE, _IDEMPOTENCY_REQUIRED_MESSAGE)
    normalized = raw_value.strip()
    if not normalized:
        raise DomainError(400, _IDEMPOTENCY_REQUIRED_CODE, _IDEMPOTENCY_REQUIRED_MESSAGE)
    if len(normalized) > 255:
        raise DomainError(400, _IDEMPOTENCY_REQUIRED_CODE, _IDEMPOTENCY_REQUIRED_MESSAGE)
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise DomainError(400, _IDEMPOTENCY_REQUIRED_CODE, _IDEMPOTENCY_REQUIRED_MESSAGE)
    return normalized


def build_project_create_scope(
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    key: str,
) -> IdempotencyScope:
    return IdempotencyScope(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        http_method=_HTTP_METHOD_POST,
        route_template=_ROUTE_TEMPLATE,
        idempotency_key=key,
    )


def compute_request_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def claim_or_replay(
    session: AsyncSession,
    *,
    scope: IdempotencyScope,
    request_hash: str,
) -> IdempotencyClaimed:
    record = IdempotencyRecord(
        organization_id=scope.organization_id,
        actor_user_id=scope.actor_user_id,
        http_method=scope.http_method,
        route_template=scope.route_template,
        idempotency_key=scope.idempotency_key,
        request_hash=request_hash,
        processing_status=_PROCESSING,
    )

    owner = False
    try:
        async with session.begin_nested():
            session.add(record)
            await session.flush()
            owner = True
    except IntegrityError as exc:
        if _extract_constraint_name(exc) != _SCOPE_CONSTRAINT_NAME:
            raise

    if owner:
        return IdempotencyClaimed(record=record, replay=None)

    existing = await _load_scope_record_for_update(session, scope=scope)
    if existing is None:
        raise DomainError(500, "INTERNAL_ERROR", "服务器内部错误")
    if existing.request_hash != request_hash:
        raise DomainError(409, _IDEMPOTENCY_CONFLICT_CODE, "幂等键已对应其他请求")
    if existing.processing_status == _SUCCEEDED:
        if existing.response_status is None or existing.response_body is None:
            raise DomainError(500, "INTERNAL_ERROR", "服务器内部错误")
        return IdempotencyClaimed(
            record=existing,
            replay=IdempotencyReplay(
                response_status=existing.response_status,
                response_body=existing.response_body,
            ),
        )
    raise DomainError(500, "INTERNAL_ERROR", "服务器内部错误")


def mark_succeeded(
    record: IdempotencyRecord,
    *,
    status_code: int,
    body: dict[str, object],
    resource_type: str,
    resource_id: UUID,
    completed_at: datetime,
) -> None:
    record.processing_status = _SUCCEEDED
    record.response_status = status_code
    record.response_body = body
    record.resource_type = resource_type
    record.resource_id = resource_id
    record.completed_at = completed_at


async def _load_scope_record_for_update(
    session: AsyncSession,
    *,
    scope: IdempotencyScope,
) -> IdempotencyRecord | None:
    statement = (
        select(IdempotencyRecord)
        .where(
            IdempotencyRecord.organization_id == scope.organization_id,
            IdempotencyRecord.actor_user_id == scope.actor_user_id,
            IdempotencyRecord.http_method == scope.http_method,
            IdempotencyRecord.route_template == scope.route_template,
            IdempotencyRecord.idempotency_key == scope.idempotency_key,
        )
        .with_for_update()
    )
    result = await session.execute(statement)
    return result.scalar_one_or_none()


def _extract_constraint_name(error: IntegrityError) -> str | None:
    original_error = getattr(error, "orig", None)
    diag = getattr(original_error, "diag", None)
    return getattr(diag, "constraint_name", None)
