from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core.security import (
    build_session_deadlines,
    is_session_active,
    is_session_expired,
    next_idle_expiry,
)


class TestSessionPolicy:
    def test_is_session_expired_when_now_equals_idle_boundary(self) -> None:
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        assert is_session_expired(now, now, now + timedelta(hours=1)) is True

    def test_is_session_expired_when_now_equals_absolute_boundary(self) -> None:
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        assert is_session_expired(now, now + timedelta(minutes=1), now) is True

    def test_next_idle_expiry_uses_idle_before_absolute(self) -> None:
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
        absolute_expires_at = now + timedelta(hours=8)

        assert next_idle_expiry(now, absolute_expires_at) == now + timedelta(minutes=30)

    def test_next_idle_expiry_never_exceeds_absolute(self) -> None:
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
        absolute_expires_at = now + timedelta(minutes=10)

        assert next_idle_expiry(now, absolute_expires_at) == absolute_expires_at

    def test_is_session_active_returns_false_when_revoked_with_aware_time(self) -> None:
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        assert (
            is_session_active(
                revoked_at=now,
                now=now,
                idle_expires_at=now + timedelta(minutes=30),
                absolute_expires_at=now + timedelta(hours=8),
            )
            is False
        )

    def test_is_session_active_rejects_naive_revoked_time(self) -> None:
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        with pytest.raises(ValueError, match="必须使用带时区的时间"):
            is_session_active(
                revoked_at=datetime(2026, 8, 21, 12, 0),
                now=now,
                idle_expires_at=now + timedelta(minutes=30),
                absolute_expires_at=now + timedelta(hours=8),
            )

    def test_is_session_active_returns_true_for_unrevoked_valid_session(self) -> None:
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        assert (
            is_session_active(
                revoked_at=None,
                now=now,
                idle_expires_at=now + timedelta(minutes=30),
                absolute_expires_at=now + timedelta(hours=8),
            )
            is True
        )

    def test_is_session_active_returns_false_at_expiry_boundary(self) -> None:
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        assert (
            is_session_active(
                revoked_at=None,
                now=now,
                idle_expires_at=now,
                absolute_expires_at=now + timedelta(hours=8),
            )
            is False
        )

    def test_naive_datetime_inputs_are_rejected(self) -> None:
        now = datetime(2026, 8, 21, 12, 0)
        absolute_expires_at = datetime(2026, 8, 21, 20, 0, tzinfo=UTC)

        with pytest.raises(ValueError, match="必须使用带时区的时间"):
            build_session_deadlines(now)

        with pytest.raises(ValueError, match="必须使用带时区的时间"):
            next_idle_expiry(now, absolute_expires_at)

        with pytest.raises(ValueError, match="必须使用带时区的时间"):
            is_session_expired(now, absolute_expires_at, absolute_expires_at)

    def test_aware_datetime_comparison_supports_utc_and_plus_8(self) -> None:
        now_utc = datetime(2026, 8, 21, 1, 0, tzinfo=UTC)
        now_plus_8 = datetime(2026, 8, 21, 9, 0, tzinfo=timezone(timedelta(hours=8)))

        deadlines = build_session_deadlines(now_plus_8)

        assert deadlines.idle_expires_at.astimezone(UTC) == now_utc + timedelta(minutes=30)
        assert deadlines.absolute_expires_at.astimezone(UTC) == now_utc + timedelta(hours=8)
