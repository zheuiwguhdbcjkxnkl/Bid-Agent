"""审计模块导出。"""

from app.audit.service import append_audit_event

__all__ = ["append_audit_event"]
