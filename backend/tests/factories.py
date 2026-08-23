from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.auth.repository import normalize_login_name
from app.core.security import PasswordHasher
from app.db.models.iam import Organization, User


@dataclass
class MutableClock:
    current: datetime

    def now(self) -> datetime:
        return self.current

    def set(self, value: datetime) -> None:
        self.current = value.astimezone(UTC)

    def advance(self, *, minutes: int = 0, hours: int = 0) -> None:
        self.current = (self.current + timedelta(minutes=minutes, hours=hours)).astimezone(UTC)


_PASSWORD_HASHER = PasswordHasher()


def create_organization(
    *,
    name: str = "测试组织",
    tenant_key: str | None = "yunqi",
) -> Organization:
    return Organization(
        id=uuid4(),
        name=name,
        organization_type="CLIENT",
        tenant_key=tenant_key or f"tenant-{uuid4()}",
        data_classification="INTERNAL",
    )


def create_user(
    *,
    organization_id: UUID,
    login_name: str = "admin",
    display_name: str = "管理员",
    account_status: str = "ACTIVE",
    system_role: str = "BID_MANAGER",
    must_change_password: bool = False,
    password: str = "Password-123!",
) -> User:
    return User(
        id=uuid4(),
        organization_id=organization_id,
        login_name=normalize_login_name(login_name),
        display_name=display_name,
        account_status=account_status,
        system_role=system_role,
        password_hash=_PASSWORD_HASHER.hash_password(password),
        must_change_password=must_change_password,
        password_changed_at=datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
    )
