from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2 import Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_AWARE_DATETIME_ERROR = "必须使用带时区的时间"


@dataclass(frozen=True, slots=True)
class SessionDeadlines:
    idle_expires_at: datetime
    absolute_expires_at: datetime


class PasswordHasher:
    def __init__(self) -> None:
        self._hasher = Argon2PasswordHasher(type=Type.ID)

    def hash_password(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False


def _require_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(_AWARE_DATETIME_ERROR)
    return value


def _normalize_aware_datetime(value: datetime) -> datetime:
    return _require_aware_datetime(value).astimezone(UTC)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_session_deadlines(
    now: datetime,
    idle_minutes: int = 30,
    absolute_hours: int = 8,
) -> SessionDeadlines:
    normalized_now = _normalize_aware_datetime(now)
    return SessionDeadlines(
        idle_expires_at=normalized_now + timedelta(minutes=idle_minutes),
        absolute_expires_at=normalized_now + timedelta(hours=absolute_hours),
    )


def next_idle_expiry(
    now: datetime,
    absolute_expires_at: datetime,
    idle_minutes: int = 30,
) -> datetime:
    normalized_now = _normalize_aware_datetime(now)
    normalized_absolute = _normalize_aware_datetime(absolute_expires_at)
    return min(normalized_now + timedelta(minutes=idle_minutes), normalized_absolute)


def is_session_expired(
    now: datetime,
    idle_expires_at: datetime,
    absolute_expires_at: datetime,
) -> bool:
    normalized_now = _normalize_aware_datetime(now)
    normalized_idle = _normalize_aware_datetime(idle_expires_at)
    normalized_absolute = _normalize_aware_datetime(absolute_expires_at)
    return normalized_now >= normalized_idle or normalized_now >= normalized_absolute


def is_session_active(
    *,
    revoked_at: datetime | None,
    now: datetime,
    idle_expires_at: datetime,
    absolute_expires_at: datetime,
) -> bool:
    if revoked_at is not None:
        _require_aware_datetime(revoked_at)
        return False
    return not is_session_expired(now, idle_expires_at, absolute_expires_at)
