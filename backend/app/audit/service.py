from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditEvent


async def append_audit_event(
    session: AsyncSession,
    *,
    organization_id: UUID,
    event_type: str,
    object_type: str,
    request_id: str,
    occurred_at: datetime,
    project_id: UUID | None = None,
    object_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    actor_type: str = "USER",
    reason: str | None = None,
    metadata_json: dict[str, Any] | None = None,
    before_snapshot: dict[str, Any] | None = None,
    after_snapshot: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        project_id=project_id,
        event_type=event_type,
        object_type=object_type,
        object_id=object_id,
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        reason=reason,
        metadata_json=metadata_json,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        request_id=request_id,
        occurred_at=occurred_at,
    )
    session.add(event)
    return event
