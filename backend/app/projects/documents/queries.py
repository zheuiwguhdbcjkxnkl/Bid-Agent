from __future__ import annotations

from collections import OrderedDict
from uuid import UUID

from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.db.models.document import DocumentVersion, ProcurementDocument
from app.db.models.iam import User
from app.db.models.project import BidProject, ProjectMember
from app.projects.documents.schemas import DocumentItem, DocumentVersionItem

_ACTIVE = "ACTIVE"


async def list_documents(
    session: AsyncSession,
    *,
    project_id: UUID,
    actor_user_id: UUID,
) -> list[DocumentItem]:
    membership = (
        await session.execute(
            select(ProjectMember)
            .join(BidProject, BidProject.id == ProjectMember.project_id)
            .join(User, User.id == ProjectMember.user_id)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == actor_user_id,
                ProjectMember.assignment_status == _ACTIVE,
                User.organization_id == BidProject.organization_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise DomainError(403, "FORBIDDEN", "无项目访问权限")

    rows = (
        await session.execute(
            select(ProcurementDocument, DocumentVersion)
            .outerjoin(
                DocumentVersion,
                DocumentVersion.document_id == ProcurementDocument.id,
            )
            .where(ProcurementDocument.project_id == project_id)
            .order_by(
                ProcurementDocument.created_at.asc(),
                func.substring(DocumentVersion.version_no, 2).cast(Integer).asc(),
            )
        )
    ).all()

    documents: OrderedDict[UUID, DocumentItem] = OrderedDict()
    for document, version in rows:
        item = documents.setdefault(
            document.id,
            DocumentItem(
                id=document.id,
                document_type=document.document_type,
                display_name=document.display_name,
                document_status=document.document_status,
                current_version_id=document.current_version_id,
                versions=[],
            ),
        )
        if version is not None:
            item.versions.append(
                DocumentVersionItem(
                    id=version.id,
                    version_no=version.version_no,
                    file_name=version.file_name,
                    content_type=version.content_type,
                    file_size=version.file_size,
                    content_hash=version.content_hash,
                    storage_uri=version.storage_uri,
                    parse_status=version.parse_status,
                    uploaded_at=version.uploaded_at,
                )
            )
    return list(documents.values())
