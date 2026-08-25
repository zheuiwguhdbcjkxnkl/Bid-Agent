from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import DocumentParse, DocumentVersion, ProcurementDocument
from app.db.models.iam import User
from app.db.models.project import BidProject, ProjectMember
from app.db.models.workflow import TaskRun

_ACTIVE = "ACTIVE"
_MANAGER = "BID_MANAGER"


async def load_version_for_manager(
    session: AsyncSession,
    *,
    document_version_id: UUID,
    actor_user_id: UUID,
    organization_id: UUID,
) -> tuple[DocumentVersion, ProcurementDocument] | None:
    result = await session.execute(
        select(DocumentVersion, ProcurementDocument)
        .join(
            ProcurementDocument,
            ProcurementDocument.id == DocumentVersion.document_id,
        )
        .join(BidProject, BidProject.id == ProcurementDocument.project_id)
        .join(
            ProjectMember,
            ProjectMember.project_id == ProcurementDocument.project_id,
        )
        .join(User, User.id == ProjectMember.user_id)
        .where(
            DocumentVersion.id == document_version_id,
            BidProject.organization_id == organization_id,
            ProjectMember.user_id == actor_user_id,
            ProjectMember.project_role == _MANAGER,
            ProjectMember.assignment_status == _ACTIVE,
            User.organization_id == organization_id,
            User.account_status == _ACTIVE,
        )
        .with_for_update()
    )
    row = result.one_or_none()
    if row is None:
        return None
    return row.DocumentVersion, row.ProcurementDocument


async def create_parse_and_task(
    session: AsyncSession,
    *,
    document_parse: DocumentParse,
    task_run: TaskRun,
) -> None:
    session.add_all([document_parse, task_run])
    await session.flush()
