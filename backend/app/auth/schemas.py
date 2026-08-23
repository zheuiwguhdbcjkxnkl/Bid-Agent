from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.auth.repository import normalize_login_name

_AWARE_DATETIME_ERROR = "必须使用带时区的时间"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(_AWARE_DATETIME_ERROR)
    return value


class LoginRequest(_StrictModel):
    login_name: str = Field(min_length=1, max_length=128)
    password: SecretStr

    @field_validator("login_name", mode="before")
    @classmethod
    def _normalize_login_name(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        return normalize_login_name(value)


class UserView(_StrictModel):
    id: UUID
    organization_id: UUID
    login_name: str
    display_name: str
    system_role: str


class SessionResponse(_StrictModel):
    user: UserView
    idle_expires_at: datetime
    absolute_expires_at: datetime
    must_change_password: bool
    allowed_actions: list[str]

    @field_validator("idle_expires_at", "absolute_expires_at")
    @classmethod
    def _validate_datetimes(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)


class PasswordChangeRequest(_StrictModel):
    current_password: SecretStr
    new_password: SecretStr = Field(min_length=12)
