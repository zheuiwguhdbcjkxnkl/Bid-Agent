from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.auth.repository import normalize_login_name
from app.auth.schemas import LoginRequest, SessionResponse, UserView
from app.core.security import (
    PasswordHasher,
    build_session_deadlines,
    generate_session_token,
    hash_session_token,
)


class TestPasswordHasher:
    def test_hash_and_verify_password(self) -> None:
        hasher = PasswordHasher()

        password_hash = hasher.hash_password("S3cure-Passw0rd")

        assert password_hash != "S3cure-Passw0rd"
        assert hasher.verify_password("S3cure-Passw0rd", password_hash) is True
        assert hasher.verify_password("wrong-password", password_hash) is False

    def test_verify_password_returns_false_for_invalid_hash(self) -> None:
        hasher = PasswordHasher()

        assert hasher.verify_password("any-password", "not-a-valid-hash") is False

    def test_verify_password_returns_false_for_damaged_hash(self) -> None:
        hasher = PasswordHasher()
        password_hash = hasher.hash_password("S3cure-Passw0rd")
        damaged_hash = f"{password_hash}tampered"

        assert hasher.verify_password("S3cure-Passw0rd", damaged_hash) is False


class TestSessionToken:
    def test_generate_session_token_is_random_and_long_enough(self) -> None:
        first_token = generate_session_token()
        second_token = generate_session_token()

        assert first_token != second_token
        assert len(first_token) >= 43
        assert len(second_token) >= 43

    def test_hash_session_token_returns_sha256_hex(self) -> None:
        token = "plain-session-token"

        hashed = hash_session_token(token)

        assert hashed != token
        assert token not in hashed
        assert len(hashed) == 64
        assert all(character in "0123456789abcdef" for character in hashed)


class TestSessionSchemas:
    def test_login_request_uses_secret_password_and_forbids_extra(self) -> None:
        request = LoginRequest(login_name="admin", password="secret-password")
        invalid_payload: dict[str, object] = {
            "login_name": "admin",
            "password": "secret-password",
            "extra_field": True,
        }

        assert request.password.get_secret_value() == "secret-password"
        assert request.login_name == "admin"

        with pytest.raises(ValidationError):
            LoginRequest.model_validate(invalid_payload)

    @pytest.mark.parametrize(
        "login_name",
        ["", "   ", "a" * 129],
    )
    def test_login_request_rejects_blank_or_too_long_login_name(self, login_name: str) -> None:
        with pytest.raises(ValidationError):
            LoginRequest(login_name=login_name, password="secret-password")

    def test_login_request_normalizes_login_name_by_strip_and_lower(self) -> None:
        request = LoginRequest(login_name=" Admin ", password="secret-password")

        assert request.login_name == "admin"


class TestLoginNameNormalization:
    def test_normalize_login_name_uses_strip_and_lower_only(self) -> None:
        assert normalize_login_name(" Admin ") == "admin"

    def test_session_response_requires_aware_datetimes(self) -> None:
        user = UserView(
            id="4ab1545f-365d-4661-84d1-a4c22de0d8ba",
            organization_id="fe8f7f57-e4b8-44bf-a7ac-0c2d272fef37",
            login_name="admin",
            display_name="管理员",
            system_role="ADMIN",
        )

        response = SessionResponse(
            user=user,
            idle_expires_at=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
            absolute_expires_at=datetime(2026, 8, 21, 18, 0, tzinfo=UTC),
            must_change_password=False,
            allowed_actions=["SESSION_VIEW", "LOGOUT"],
        )

        assert response.idle_expires_at.tzinfo is UTC

        with pytest.raises(ValueError, match="必须使用带时区的时间"):
            SessionResponse(
                user=user,
                idle_expires_at=datetime(2026, 8, 21, 12, 0),
                absolute_expires_at=datetime(2026, 8, 21, 18, 0, tzinfo=UTC),
                must_change_password=False,
                allowed_actions=["SESSION_VIEW", "LOGOUT"],
            )


class TestSessionDeadlines:
    def test_build_session_deadlines_returns_aware_datetimes_for_plus_8_input(self) -> None:
        now = datetime(2026, 8, 21, 9, 0, tzinfo=timezone(timedelta(hours=8)))

        deadlines = build_session_deadlines(now)

        assert deadlines.idle_expires_at == datetime(2026, 8, 21, 1, 30, tzinfo=UTC)
        assert deadlines.absolute_expires_at == datetime(2026, 8, 21, 9, 0, tzinfo=UTC)
        assert deadlines.idle_expires_at.tzinfo is not None
        assert deadlines.absolute_expires_at.tzinfo is not None
