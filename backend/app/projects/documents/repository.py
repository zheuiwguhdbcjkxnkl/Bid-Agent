from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import DocumentVersion, ProcurementDocument
from app.db.models.iam import User
from app.db.models.project import BidProject, ProjectMember

_ACTIVE = "ACTIVE"
_MANAGER = "BID_MANAGER"


async def load_active_manager(
    session: AsyncSession,
    *,
    project_id: UUID,
    actor_user_id: UUID,
    organization_id: UUID,
) -> ProjectMember | None:
    project = await session.scalar(
        select(BidProject)
        .where(
            BidProject.id == project_id,
            BidProject.organization_id == organization_id,
        )
        .with_for_update()
    )
    if project is None:
        return None
    result = await session.execute(
        select(ProjectMember)
        .join(User, User.id == ProjectMember.user_id)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == actor_user_id,
            ProjectMember.project_role == _MANAGER,
            ProjectMember.assignment_status == _ACTIVE,
            User.organization_id == organization_id,
            User.account_status == _ACTIVE,
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def content_hash_exists(
    session: AsyncSession,
    *,
    project_id: UUID,
    content_hash: str,
) -> bool:
    result = await session.execute(
        select(DocumentVersion.id)
        .join(ProcurementDocument, ProcurementDocument.id == DocumentVersion.document_id)
        .where(
            ProcurementDocument.project_id == project_id,
            DocumentVersion.content_hash == content_hash,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def create_document_with_version(
    session: AsyncSession,
    *,
    document_id: UUID,
    version_id: UUID,
    project_id: UUID,
    document_type: str,
    display_name: str,
    file_name: str,
    content_type: str,
    file_size: int,
    content_hash: str,
    storage_uri: str,
    uploaded_at: datetime,
) -> tuple[ProcurementDocument, DocumentVersion]:
    document = ProcurementDocument(
        id=document_id,
        project_id=project_id,
        document_type=document_type,
        display_name=display_name,
        document_status="ACTIVE",
        created_at=uploaded_at,
    )
    session.add(document)
    await session.flush()
    version = DocumentVersion(
        id=version_id,
        document_id=document_id,
        version_no="v1",
        file_name=file_name,
        content_type=content_type,
        file_size=file_size,
        content_hash=content_hash,
        storage_uri=storage_uri,
        parse_status="PENDING",
        uploaded_at=uploaded_at,
    )
    session.add(version)
    await session.flush()
    document.current_version_id = version.id
    await session.flush()
    return document, version
