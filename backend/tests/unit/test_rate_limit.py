from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from redis.exceptions import RedisError

from app.core.rate_limit import (
    FallbackLoginRateLimiter,
    InMemoryFailureStore,
    RedisFailureStore,
)


class TestInMemoryFailureStore:
    @pytest.mark.asyncio
    async def test_counts_and_resets_after_window_boundary(self) -> None:
        store = InMemoryFailureStore()
        key = "login-key"
        start = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        assert await store.current_count(key, start) == 0
        assert await store.register_failure(key, start, 60) == 1
        assert await store.current_count(key, start + timedelta(seconds=59)) == 1
        assert await store.register_failure(key, start + timedelta(seconds=60), 60) == 1
        assert await store.current_count(key, start + timedelta(seconds=60)) == 1

    @pytest.mark.asyncio
    async def test_clears_expired_keys_while_operating(self) -> None:
        store = InMemoryFailureStore()
        expired_now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
        later = expired_now + timedelta(seconds=61)

        await store.register_failure("expired", expired_now, 60)
        await store.register_failure("active", later, 60)

        assert await store.current_count("expired", later) == 0
        assert await store.current_count("active", later) == 1

    @pytest.mark.asyncio
    async def test_tracks_different_keys_independently(self) -> None:
        store = InMemoryFailureStore()
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        await store.register_failure("a", now, 60)
        await store.register_failure("b", now, 60)
        await store.register_failure("b", now, 60)

        assert await store.current_count("a", now) == 1
        assert await store.current_count("b", now) == 2

    @pytest.mark.asyncio
    async def test_rejects_naive_datetime(self) -> None:
        store = InMemoryFailureStore()
        naive_now = datetime(2026, 8, 21, 12, 0)

        with pytest.raises(ValueError, match="必须使用带时区的时间"):
            await store.current_count("key", naive_now)


class FakeRedisClient:
    def __init__(self) -> None:
        self.eval_calls: list[tuple[str, int, str, int]] = []
        self.get_calls: list[str] = []
        self.delete_calls: list[str] = []
        self.get_value: bytes | str | None = None
        self.eval_error: Exception | None = None
        self.get_error: Exception | None = None
        self.delete_error: Exception | None = None

    async def eval(self, script: str, numkeys: int, key: str, window_seconds: int) -> int:
        if self.eval_error is not None:
            raise self.eval_error
        self.eval_calls.append((script, numkeys, key, window_seconds))
        return 3

    async def get(self, key: str) -> bytes | str | None:
        if self.get_error is not None:
            raise self.get_error
        self.get_calls.append(key)
        return self.get_value

    async def delete(self, key: str) -> int:
        if self.delete_error is not None:
            raise self.delete_error
        self.delete_calls.append(key)
        return 1


class TestRedisFailureStore:
    @pytest.mark.asyncio
    async def test_register_failure_uses_prefixed_key_and_window(self) -> None:
        client = FakeRedisClient()
        store = RedisFailureStore(client)
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        count = await store.register_failure("abc", now, 300)

        assert count == 3
        assert len(client.eval_calls) == 1
        script, numkeys, key, window_seconds = client.eval_calls[0]
        assert "INCR" in script
        assert "EXPIRE" in script
        assert numkeys == 1
        assert key == "login-failure:abc"
        assert window_seconds == 300

    @pytest.mark.asyncio
    async def test_current_count_reads_existing_value(self) -> None:
        client = FakeRedisClient()
        client.get_value = b"4"
        store = RedisFailureStore(client)
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        assert await store.current_count("abc", now) == 4
        assert client.get_calls == ["login-failure:abc"]

    @pytest.mark.asyncio
    async def test_clear_deletes_prefixed_key(self) -> None:
        client = FakeRedisClient()
        store = RedisFailureStore(client)

        await store.clear("abc")

        assert client.delete_calls == ["login-failure:abc"]

    @pytest.mark.asyncio
    async def test_wraps_redis_errors_as_connection_error(self) -> None:
        client = FakeRedisClient()
        client.eval_error = RedisError("boom")
        store = RedisFailureStore(client)
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        with pytest.raises(ConnectionError):
            await store.register_failure("abc", now, 60)

    @pytest.mark.asyncio
    async def test_rejects_naive_datetime_even_though_redis_uses_ttl(self) -> None:
        client = FakeRedisClient()
        store = RedisFailureStore(client)
        naive_now = datetime(2026, 8, 21, 12, 0)

        with pytest.raises(ValueError, match="必须使用带时区的时间"):
            await store.current_count("abc", naive_now)


class FailingStore:
    def __init__(self) -> None:
        self.current_calls = 0
        self.register_calls = 0
        self.clear_calls = 0

    async def current_count(self, key: str, now: datetime) -> int:
        self.current_calls += 1
        raise ConnectionError("primary down")

    async def register_failure(self, key: str, now: datetime, window_seconds: int) -> int:
        self.register_calls += 1
        raise ConnectionError("primary down")

    async def clear(self, key: str) -> None:
        self.clear_calls += 1
        raise ConnectionError("primary down")


class RecordingStore:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.current_keys: list[str] = []
        self.register_keys: list[str] = []
        self.clear_keys: list[str] = []

    async def current_count(self, key: str, now: datetime) -> int:
        self.current_keys.append(key)
        return self.counts.get(key, 0)

    async def register_failure(self, key: str, now: datetime, window_seconds: int) -> int:
        self.register_keys.append(key)
        next_count = self.counts.get(key, 0) + 1
        self.counts[key] = next_count
        return next_count

    async def clear(self, key: str) -> None:
        self.clear_keys.append(key)
        self.counts.pop(key, None)


class RecoveringStore:
    def __init__(self, *, counts: dict[str, int] | None = None, fail_current: bool = False) -> None:
        self.counts = counts or {}
        self.fail_current = fail_current
        self.current_keys: list[str] = []
        self.register_keys: list[str] = []
        self.clear_keys: list[str] = []

    async def current_count(self, key: str, now: datetime) -> int:
        self.current_keys.append(key)
        if self.fail_current:
            raise ConnectionError("primary down")
        return self.counts.get(key, 0)

    async def register_failure(self, key: str, now: datetime, window_seconds: int) -> int:
        self.register_keys.append(key)
        next_count = self.counts.get(key, 0) + 1
        self.counts[key] = next_count
        return next_count

    async def clear(self, key: str) -> None:
        self.clear_keys.append(key)
        self.counts.pop(key, None)


class TestFallbackLoginRateLimiter:
    @pytest.mark.asyncio
    async def test_limits_on_fifth_failure(self) -> None:
        fallback = RecordingStore()
        limiter = FallbackLoginRateLimiter(
            primary=None,
            fallback=fallback,
            limit=5,
            window_seconds=300,
        )
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        for _ in range(4):
            count = await limiter.record_failure(
                login_name="Alice",
                source="10.0.0.1",
                now=now,
            )
            assert count < 5
            assert (
                await limiter.is_limited(
                    login_name="Alice",
                    source="10.0.0.1",
                    now=now,
                )
                is False
            )

        count = await limiter.record_failure(
            login_name="Alice",
            source="10.0.0.1",
            now=now,
        )

        assert count == 5
        assert (
            await limiter.is_limited(
                login_name="Alice",
                source="10.0.0.1",
                now=now,
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_falls_back_when_primary_is_unavailable(self) -> None:
        primary = FailingStore()
        fallback = RecordingStore()
        limiter = FallbackLoginRateLimiter(
            primary=primary,
            fallback=fallback,
            limit=5,
            window_seconds=300,
        )
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        count = await limiter.record_failure(
            login_name="Alice",
            source="10.0.0.1",
            now=now,
        )

        assert count == 1
        assert primary.register_calls == 1
        assert len(fallback.register_keys) == 1

    @pytest.mark.asyncio
    async def test_clear_after_success_also_clears_fallback_when_primary_clear_fails(self) -> None:
        primary = FailingStore()
        fallback = RecordingStore()
        limiter = FallbackLoginRateLimiter(
            primary=primary,
            fallback=fallback,
            limit=5,
            window_seconds=300,
        )
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        await limiter.record_failure(login_name="Alice", source="10.0.0.1", now=now)
        await limiter.clear_after_success(login_name="Alice", source="10.0.0.1")

        assert primary.clear_calls == 1
        assert len(fallback.clear_keys) == 1
        assert fallback.counts == {}

    @pytest.mark.asyncio
    async def test_uses_unknown_for_blank_source_and_hides_raw_login_name_in_key(self) -> None:
        fallback = RecordingStore()
        limiter = FallbackLoginRateLimiter(
            primary=None,
            fallback=fallback,
            limit=5,
            window_seconds=300,
        )
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        await limiter.record_failure(login_name="Alice@example.com", source="   ", now=now)

        stored_key = fallback.register_keys[0]
        assert stored_key != "Alice@example.com"
        assert "alice@example.com" not in stored_key
        assert len(stored_key) == 64

    @pytest.mark.asyncio
    async def test_remains_limited_when_primary_recovers_but_fallback_has_higher_count(
        self,
    ) -> None:
        fallback = RecordingStore()
        limiter = FallbackLoginRateLimiter(
            primary=FailingStore(),
            fallback=fallback,
            limit=5,
            window_seconds=300,
        )
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        for _ in range(5):
            await limiter.record_failure(login_name="Alice", source="10.0.0.1", now=now)

        limiter = FallbackLoginRateLimiter(
            primary=RecoveringStore(counts={}, fail_current=False),
            fallback=fallback,
            limit=5,
            window_seconds=300,
        )

        assert (
            await limiter.is_limited(
                login_name="Alice",
                source="10.0.0.1",
                now=now,
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_uses_higher_count_between_primary_and_fallback_without_double_counting(
        self,
    ) -> None:
        primary = RecoveringStore(counts={})
        fallback = RecordingStore()
        limiter = FallbackLoginRateLimiter(
            primary=primary,
            fallback=fallback,
            limit=5,
            window_seconds=300,
        )
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
        storage_key = limiter._build_storage_key("Alice", "10.0.0.1")
        primary.counts[storage_key] = 6
        fallback.counts[storage_key] = 2

        assert (
            await limiter.is_limited(
                login_name="Alice",
                source="10.0.0.1",
                now=now,
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_recovers_after_fallback_window_expires_and_primary_count_is_zero(self) -> None:
        primary = RecoveringStore(counts={})
        fallback = InMemoryFailureStore()
        limiter = FallbackLoginRateLimiter(
            primary=primary,
            fallback=fallback,
            limit=5,
            window_seconds=60,
        )
        start = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        for _ in range(5):
            await fallback.register_failure(
                limiter._build_storage_key("Alice", "10.0.0.1"),
                start,
                60,
            )

        assert (
            await limiter.is_limited(
                login_name="Alice",
                source="10.0.0.1",
                now=start,
            )
            is True
        )
        assert (
            await limiter.is_limited(
                login_name="Alice",
                source="10.0.0.1",
                now=start + timedelta(seconds=61),
            )
            is False
        )

    @pytest.mark.asyncio
    async def test_rejects_naive_datetime(self) -> None:
        fallback = RecordingStore()
        limiter = FallbackLoginRateLimiter(
            primary=None,
            fallback=fallback,
            limit=5,
            window_seconds=300,
        )
        naive_now = datetime(2026, 8, 21, 12, 0)

        with pytest.raises(ValueError, match="必须使用带时区的时间"):
            await limiter.is_limited(login_name="Alice", source="10.0.0.1", now=naive_now)
