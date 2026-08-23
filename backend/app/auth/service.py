from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import append_audit_event
from app.auth.repository import (
    LoginUserRecord,
    UserSessionRecord,
    find_organization_by_tenant_key,
    find_other_active_sessions_for_update,
    find_session_by_token_hash,
    find_user_by_id_for_update,
    find_user_for_login,
    normalize_login_name,
)
from app.auth.schemas import SessionResponse, UserView
from app.core.config import Settings
from app.core.csrf import generate_csrf_token
from app.core.errors import DomainError
from app.core.rate_limit import FallbackLoginRateLimiter
from app.core.security import (
    PasswordHasher,
    build_session_deadlines,
    generate_session_token,
    hash_session_token,
    is_session_expired,
    next_idle_expiry,
)
from app.db.models.iam import User, UserSession

_INVALID_CREDENTIALS_CODE = "INVALID_CREDENTIALS"
_INVALID_CREDENTIALS_MESSAGE = "账号或密码错误"
_LOGIN_RATE_LIMITED_CODE = "LOGIN_RATE_LIMITED"
_LOGIN_RATE_LIMITED_MESSAGE = "登录失败次数过多，请稍后再试"
_PASSWORD_CHANGE_REQUIRED_CODE = "PASSWORD_CHANGE_REQUIRED"
_PASSWORD_CHANGE_REQUIRED_MESSAGE = "当前账号必须先修改密码"
_AUDIT_OBJECT_TYPE_USER = "USER"
_AUDIT_OBJECT_TYPE_USER_SESSION = "USER_SESSION"
_DUMMY_PASSWORD_HASH = PasswordHasher().hash_password("dummy-password-for-login")


def _require_aware_now(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("必须使用带时区的时间")
    return value


@dataclass(slots=True)
class LoginResult:
    response: SessionResponse
    session_token: str
    csrf_token: str


@dataclass(slots=True)
class SessionLookupResult:
    response: SessionResponse | None = None
    error: DomainError | None = None


@dataclass(slots=True)
class AuthenticatedContext:
    session_id: UUID
    user_id: UUID
    organization_id: UUID
    system_role: str
    must_change_password: bool


class LoginService:
    def __init__(
        self,
        *,
        settings: Settings,
        limiter: FallbackLoginRateLimiter,
        now_provider: Callable[[], datetime],
        password_hasher: PasswordHasher | None = None,
    ) -> None:
        self._settings = settings
        self._limiter = limiter
        self._now_provider = now_provider
        self._password_hasher = password_hasher or PasswordHasher()

    async def login(
        self,
        session: AsyncSession,
        *,
        login_name: str,
        password: str,
        source: str,
        request_id: str,
    ) -> LoginResult:
        now = _require_aware_now(self._now_provider())

        if await self._limiter.is_limited(login_name=login_name, source=source, now=now):
            raise DomainError(429, _LOGIN_RATE_LIMITED_CODE, _LOGIN_RATE_LIMITED_MESSAGE)

        auth_organization = await find_organization_by_tenant_key(
            session,
            self._settings.auth_tenant_key,
        )
        if auth_organization is None:
            raise DomainError(500, "INTERNAL_ERROR", "服务器内部错误")

        normalized_login_name = normalize_login_name(login_name)
        user_record = await find_user_for_login(
            session,
            organization_id=auth_organization.id,
            login_name=normalized_login_name,
        )
        password_hash = (
            user_record.password_hash if user_record is not None else _DUMMY_PASSWORD_HASH
        )
        password_is_valid = self._password_hasher.verify_password(password, password_hash)
        user_is_valid = (
            user_record is not None and password_is_valid and user_record.account_status == "ACTIVE"
        )

        if not user_is_valid:
            failure_count = await self._limiter.record_failure(
                login_name=login_name,
                source=source,
                now=now,
            )
            await self._record_failed_login_audit(
                session,
                login_name=normalized_login_name,
                source=source,
                request_id=request_id,
                now=now,
                user_record=user_record,
                organization_id=auth_organization.id,
            )
            await session.commit()
            if failure_count >= self._settings.login_failure_limit:
                raise DomainError(429, _LOGIN_RATE_LIMITED_CODE, _LOGIN_RATE_LIMITED_MESSAGE)
            raise DomainError(401, _INVALID_CREDENTIALS_CODE, _INVALID_CREDENTIALS_MESSAGE)

        assert user_record is not None
        successful_user = user_record

        await self._limiter.clear_after_success(login_name=login_name, source=source)
        deadlines = build_session_deadlines(
            now,
            idle_minutes=self._settings.session_idle_minutes,
            absolute_hours=self._settings.session_absolute_hours,
        )
        session_token = generate_session_token()
        csrf_token = generate_csrf_token()
        db_user = await session.get(User, successful_user.id)
        assert db_user is not None
        db_user.last_login_at = now
        session.add(
            UserSession(
                user_id=successful_user.id,
                token_hash=hash_session_token(session_token),
                last_seen_at=now,
                idle_expires_at=deadlines.idle_expires_at,
                absolute_expires_at=deadlines.absolute_expires_at,
            )
        )
        await append_audit_event(
            session,
            organization_id=successful_user.organization_id,
            project_id=None,
            event_type="LOGIN_SUCCEEDED",
            object_type=_AUDIT_OBJECT_TYPE_USER,
            object_id=successful_user.id,
            actor_user_id=successful_user.id,
            actor_type="USER",
            metadata_json={"source_hash": _hash_value(source)},
            request_id=request_id,
            occurred_at=now,
        )
        await session.commit()

        return LoginResult(
            response=SessionResponse(
                user=UserView(
                    id=successful_user.id,
                    organization_id=successful_user.organization_id,
                    login_name=successful_user.login_name,
                    display_name=successful_user.display_name,
                    system_role=successful_user.system_role,
                ),
                idle_expires_at=deadlines.idle_expires_at,
                absolute_expires_at=deadlines.absolute_expires_at,
                must_change_password=successful_user.must_change_password,
                allowed_actions=build_allowed_actions(
                    system_role=successful_user.system_role,
                    must_change_password=successful_user.must_change_password,
                ),
            ),
            session_token=session_token,
            csrf_token=csrf_token,
        )

    async def get_session(
        self,
        session: AsyncSession,
        *,
        session_token: str,
        request_id: str,
    ) -> SessionLookupResult:
        now = _require_aware_now(self._now_provider())
        record = await self._lookup_session_record(
            session,
            session_token=session_token,
            for_update=True,
        )
        if record is None:
            return SessionLookupResult(error=DomainError(401, "UNAUTHENTICATED", "未登录"))

        user_session = record.session
        user = record.user

        if user_session.revoked_at is not None:
            return SessionLookupResult(error=DomainError(401, "SESSION_EXPIRED", "会话已失效"))

        if user.account_status == "DISABLED":
            await self._revoke_session(
                session,
                user_session=user_session,
                user=user,
                now=now,
                request_id=request_id,
                reason="ACCOUNT_DISABLED",
            )
            await session.commit()
            return SessionLookupResult(error=DomainError(401, "UNAUTHENTICATED", "未登录"))

        if is_session_expired(
            now,
            user_session.idle_expires_at,
            user_session.absolute_expires_at,
        ):
            await self._revoke_session(
                session,
                user_session=user_session,
                user=user,
                now=now,
                request_id=request_id,
                reason="EXPIRED",
            )
            await session.commit()
            return SessionLookupResult(error=DomainError(401, "SESSION_EXPIRED", "会话已失效"))

        user_session.last_seen_at = now
        user_session.idle_expires_at = next_idle_expiry(
            now,
            user_session.absolute_expires_at,
            idle_minutes=self._settings.session_idle_minutes,
        )
        await session.commit()
        return SessionLookupResult(
            response=self._build_session_response(user=user, user_session=user_session)
        )

    async def get_authenticated_context(
        self,
        session: AsyncSession,
        *,
        session_token: str,
        request_id: str,
        for_update: bool = False,
    ) -> AuthenticatedContext:
        del request_id
        now = _require_aware_now(self._now_provider())
        record = await self._lookup_session_record(
            session,
            session_token=session_token,
            for_update=for_update,
        )
        if record is None:
            raise DomainError(401, "UNAUTHENTICATED", "未登录")
        self._assert_session_is_authenticated(record=record, now=now)
        return self._build_authenticated_context(record=record)

    async def logout(
        self,
        session: AsyncSession,
        *,
        session_token: str,
        request_id: str,
    ) -> None:
        now = _require_aware_now(self._now_provider())
        record = await self._lookup_session_record(
            session,
            session_token=session_token,
            for_update=True,
        )
        if record is None:
            raise DomainError(401, "UNAUTHENTICATED", "未登录")

        user_session = record.session
        user = record.user
        if user_session.revoked_at is not None:
            await session.commit()
            return
        if user.account_status != "ACTIVE":
            await session.commit()
            return
        if is_session_expired(
            now,
            user_session.idle_expires_at,
            user_session.absolute_expires_at,
        ):
            await session.commit()
            return

        user_session.revoked_at = now.astimezone(UTC)
        user_session.revoke_reason = "LOGOUT"
        await append_audit_event(
            session,
            organization_id=user.organization_id,
            project_id=None,
            event_type="LOGOUT",
            object_type=_AUDIT_OBJECT_TYPE_USER_SESSION,
            object_id=user_session.id,
            actor_user_id=user.id,
            actor_type="USER",
            request_id=request_id,
            occurred_at=now,
        )
        await session.commit()

    async def change_password(
        self,
        session: AsyncSession,
        *,
        session_token: str,
        current_password: str,
        new_password: str,
        request_id: str,
    ) -> None:
        now = _require_aware_now(self._now_provider())
        record = await self._lookup_session_record(
            session,
            session_token=session_token,
            for_update=True,
        )
        if record is None:
            raise DomainError(401, "UNAUTHENTICATED", "未登录")
        self._assert_session_is_authenticated(record=record, now=now)

        db_user = await find_user_by_id_for_update(session, user_id=record.user.id)
        assert db_user is not None
        if not self._password_hasher.verify_password(current_password, db_user.password_hash):
            raise DomainError(401, _INVALID_CREDENTIALS_CODE, _INVALID_CREDENTIALS_MESSAGE)

        self._assert_new_password_valid(
            current_password=current_password,
            new_password=new_password,
        )

        db_user.password_hash = self._password_hasher.hash_password(new_password)
        db_user.password_changed_at = now
        db_user.must_change_password = False

        record.session.last_seen_at = now
        record.session.idle_expires_at = next_idle_expiry(
            now,
            record.session.absolute_expires_at,
            idle_minutes=self._settings.session_idle_minutes,
        )

        revoked_session_count = 0
        other_sessions = await find_other_active_sessions_for_update(
            session,
            user_id=db_user.id,
            current_session_id=record.session.id,
        )
        for other_session in other_sessions:
            if is_session_expired(
                now,
                other_session.idle_expires_at,
                other_session.absolute_expires_at,
            ):
                continue
            other_session.revoked_at = now.astimezone(UTC)
            other_session.revoke_reason = "PASSWORD_CHANGED"
            revoked_session_count += 1
            await append_audit_event(
                session,
                organization_id=db_user.organization_id,
                project_id=None,
                event_type="SESSION_REVOKED",
                object_type=_AUDIT_OBJECT_TYPE_USER_SESSION,
                object_id=other_session.id,
                actor_user_id=db_user.id,
                actor_type="USER",
                metadata_json={"reason": "PASSWORD_CHANGED"},
                request_id=request_id,
                occurred_at=now,
            )

        await append_audit_event(
            session,
            organization_id=db_user.organization_id,
            project_id=None,
            event_type="PASSWORD_CHANGED",
            object_type=_AUDIT_OBJECT_TYPE_USER,
            object_id=db_user.id,
            actor_user_id=db_user.id,
            actor_type="USER",
            metadata_json={"revoked_session_count": revoked_session_count},
            request_id=request_id,
            occurred_at=now,
        )
        await session.commit()

    async def _lookup_session_record(
        self,
        session: AsyncSession,
        *,
        session_token: str,
        for_update: bool,
    ) -> UserSessionRecord | None:
        return await find_session_by_token_hash(
            session,
            token_hash=hash_session_token(session_token),
            for_update=for_update,
        )

    def _assert_session_is_authenticated(
        self,
        *,
        record: UserSessionRecord,
        now: datetime,
    ) -> None:
        if record.session.revoked_at is not None:
            raise DomainError(401, "SESSION_EXPIRED", "会话已失效")
        if record.user.account_status == "DISABLED":
            raise DomainError(401, "UNAUTHENTICATED", "未登录")
        if is_session_expired(
            now,
            record.session.idle_expires_at,
            record.session.absolute_expires_at,
        ):
            raise DomainError(401, "SESSION_EXPIRED", "会话已失效")

    def _build_authenticated_context(
        self,
        *,
        record: UserSessionRecord,
    ) -> AuthenticatedContext:
        return AuthenticatedContext(
            session_id=record.session.id,
            user_id=record.user.id,
            organization_id=record.user.organization_id,
            system_role=record.user.system_role,
            must_change_password=record.user.must_change_password,
        )

    def _build_session_response(
        self,
        *,
        user: User,
        user_session: UserSession,
    ) -> SessionResponse:
        return SessionResponse(
            user=UserView(
                id=user.id,
                organization_id=user.organization_id,
                login_name=user.login_name,
                display_name=user.display_name,
                system_role=user.system_role,
            ),
            idle_expires_at=user_session.idle_expires_at,
            absolute_expires_at=user_session.absolute_expires_at,
            must_change_password=user.must_change_password,
            allowed_actions=build_allowed_actions(
                system_role=user.system_role,
                must_change_password=user.must_change_password,
            ),
        )

    async def _revoke_session(
        self,
        session: AsyncSession,
        *,
        user_session: UserSession,
        user: User,
        now: datetime,
        request_id: str,
        reason: str,
    ) -> None:
        user_session.revoked_at = now.astimezone(UTC)
        user_session.revoke_reason = reason
        await append_audit_event(
            session,
            organization_id=user.organization_id,
            project_id=None,
            event_type="SESSION_REVOKED",
            object_type=_AUDIT_OBJECT_TYPE_USER_SESSION,
            object_id=user_session.id,
            actor_user_id=user.id,
            actor_type="USER",
            metadata_json={"reason": reason},
            request_id=request_id,
            occurred_at=now,
        )

    async def _record_failed_login_audit(
        self,
        session: AsyncSession,
        *,
        login_name: str,
        source: str,
        request_id: str,
        now: datetime,
        user_record: LoginUserRecord | None,
        organization_id: UUID,
    ) -> None:
        await append_audit_event(
            session,
            organization_id=organization_id,
            project_id=None,
            event_type="LOGIN_FAILED",
            object_type=_AUDIT_OBJECT_TYPE_USER_SESSION,
            object_id=None,
            actor_user_id=user_record.id if user_record is not None else None,
            actor_type="USER",
            metadata_json={
                "login_identifier_hash": _hash_value(login_name),
                "source_hash": _hash_value(source),
            },
            request_id=request_id,
            occurred_at=now,
        )

    def _assert_new_password_valid(self, *, current_password: str, new_password: str) -> None:
        if not new_password.strip():
            raise self._new_password_validation_error("新密码不能为空白")
        if current_password == new_password:
            raise self._new_password_validation_error("新密码不能与当前密码相同")
        if not any(character.isalpha() for character in new_password):
            raise self._new_password_validation_error("新密码必须至少包含一个字母")
        if not any(character.isdigit() for character in new_password):
            raise self._new_password_validation_error("新密码必须至少包含一个数字")

    def _new_password_validation_error(self, message: str) -> DomainError:
        return DomainError(
            422,
            "VALIDATION_ERROR",
            "请求参数校验失败",
            details={
                "errors": [
                    {
                        "loc": ["body", "new_password"],
                        "msg": message,
                        "type": "value_error",
                    }
                ]
            },
        )


def build_allowed_actions(*, system_role: str, must_change_password: bool) -> list[str]:
    if must_change_password:
        return ["SESSION_READ", "LOGOUT", "PASSWORD_CHANGE"]

    actions = [
        "SESSION_READ",
        "LOGOUT",
        "PASSWORD_CHANGE",
        "WORKBENCH_READ",
        "PROJECT_READ",
    ]
    if system_role == "BID_MANAGER":
        actions.append("PROJECT_CREATE")
    return actions


def require_business_access(context: AuthenticatedContext) -> AuthenticatedContext:
    if context.must_change_password:
        raise DomainError(403, _PASSWORD_CHANGE_REQUIRED_CODE, _PASSWORD_CHANGE_REQUIRED_MESSAGE)
    return context


def _hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
