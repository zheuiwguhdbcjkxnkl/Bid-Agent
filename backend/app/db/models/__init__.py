"""集中导入全部 ORM 模型，确保元数据完整注册。"""

from app.db.models.audit import AuditEvent
from app.db.models.document import (
    DocumentPage,
    DocumentParse,
    DocumentSegment,
    DocumentVersion,
    ProcurementDocument,
)
from app.db.models.iam import IdempotencyRecord, Organization, User, UserSession
from app.db.models.project import BidPackage, BidProject, ProjectMember
from app.db.models.workflow import TaskRun

__all__ = [
    "AuditEvent",
    "BidPackage",
    "BidProject",
    "DocumentPage",
    "DocumentParse",
    "DocumentSegment",
    "DocumentVersion",
    "IdempotencyRecord",
    "Organization",
    "ProcurementDocument",
    "ProjectMember",
    "TaskRun",
    "User",
    "UserSession",
]
