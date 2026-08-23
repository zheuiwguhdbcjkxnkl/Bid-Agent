from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from redis.exceptions import RedisError

_AWARE_DATETIME_ERROR = "必须使用带时区的时间"
_REDIS_KEY_PREFIX = "login-failure:"
_REDIS_REGISTER_FAILURE_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
""".strip()


class FailureStore(Protocol):
    async def current_count(self, key: str, now: datetime) -> int: ...

    async def register_failure(self, key: str, now: datetime, window_seconds: int) -> int: ...

    async def clear(self, key: str) -> None: ...


@dataclass(slots=True)
class _FailureWindow:
    started_at: datetime
    count: int
    window_seconds: int


def _require_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(_AWARE_DATETIME_ERROR)
    return value.astimezone(UTC)


class InMemoryFailureStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._windows: dict[str, _FailureWindow] = {}

    def _cleanup_expired_windows(self, now: datetime) -> None:
        expired_keys = [
            key
            for key, window in self._windows.items()
            if now >= window.started_at + timedelta(seconds=window.window_seconds)
        ]
        for key in expired_keys:
            self._windows.pop(key, None)

    async def current_count(self, key: str, now: datetime) -> int:
        normalized_now = _require_aware_datetime(now)
        async with self._lock:
            self._cleanup_expired_windows(normalized_now)
            window = self._windows.get(key)
            if window is None:
                return 0
            return window.count

    async def register_failure(self, key: str, now: datetime, window_seconds: int) -> int:
        normalized_now = _require_aware_datetime(now)
        async with self._lock:
            self._cleanup_expired_windows(normalized_now)
            window = self._windows.get(key)
            if window is None:
                next_count = 1
                self._windows[key] = _FailureWindow(
                    started_at=normalized_now,
                    count=next_count,
                    window_seconds=window_seconds,
                )
                return next_count

            if normalized_now >= window.started_at + timedelta(seconds=window.window_seconds):
                next_count = 1
                self._windows[key] = _FailureWindow(
                    started_at=normalized_now,
                    count=next_count,
                    window_seconds=window_seconds,
                )
                return next_count

            window.count += 1
            window.window_seconds = window_seconds
            return window.count

    async def clear(self, key: str) -> None:
        async with self._lock:
            self._windows.pop(key, None)


class RedisFailureStore:
    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    @staticmethod
    def _build_key(key: str) -> str:
        return f"{_REDIS_KEY_PREFIX}{key}"

    async def current_count(self, key: str, now: datetime) -> int:
        _require_aware_datetime(now)
        redis_key = self._build_key(key)
        try:
            raw_value = await self._redis.get(redis_key)
        except RedisError as error:
            raise ConnectionError("Redis 不可用") from error
        if raw_value is None:
            return 0
        if isinstance(raw_value, bytes):
            return int(raw_value.decode("utf-8"))
        return int(raw_value)

    async def register_failure(self, key: str, now: datetime, window_seconds: int) -> int:
        _require_aware_datetime(now)
        redis_key = self._build_key(key)
        try:
            result = await self._redis.eval(
                _REDIS_REGISTER_FAILURE_SCRIPT,
                1,
                redis_key,
                window_seconds,
            )
        except RedisError as error:
            raise ConnectionError("Redis 不可用") from error
        return int(result)

    async def clear(self, key: str) -> None:
        redis_key = self._build_key(key)
        try:
            await self._redis.delete(redis_key)
        except RedisError as error:
            raise ConnectionError("Redis 不可用") from error


class FallbackLoginRateLimiter:
    def __init__(
        self,
        *,
        primary: FailureStore | None,
        fallback: FailureStore,
        limit: int,
        window_seconds: int,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._limit = limit
        self._window_seconds = window_seconds

    @staticmethod
    def _build_storage_key(login_name: str, source: str) -> str:
        normalized_login_name = login_name.strip().casefold()
        normalized_source = source.strip() or "unknown"
        raw_value = f"{normalized_login_name}\0{normalized_source}"
        return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()

    def _require_aware_now(self, now: datetime) -> datetime:
        return _require_aware_datetime(now)

    async def current(self, *, login_name: str, source: str, now: datetime) -> int:
        normalized_now = self._require_aware_now(now)
        storage_key = self._build_storage_key(login_name, source)
        fallback_count = await self._fallback.current_count(storage_key, normalized_now)
        if self._primary is not None:
            try:
                primary_count = await self._primary.current_count(storage_key, normalized_now)
            except ConnectionError:
                return fallback_count
            return max(primary_count, fallback_count)
        return fallback_count

    async def is_limited(self, *, login_name: str, source: str, now: datetime) -> bool:
        count = await self.current(login_name=login_name, source=source, now=now)
        return count >= self._limit

    async def record_failure(self, *, login_name: str, source: str, now: datetime) -> int:
        normalized_now = self._require_aware_now(now)
        storage_key = self._build_storage_key(login_name, source)
        if self._primary is not None:
            try:
                return await self._primary.register_failure(
                    storage_key,
                    normalized_now,
                    self._window_seconds,
                )
            except ConnectionError:
                pass
        return await self._fallback.register_failure(
            storage_key,
            normalized_now,
            self._window_seconds,
        )

    async def clear_after_success(self, *, login_name: str, source: str) -> None:
        storage_key = self._build_storage_key(login_name, source)
        if self._primary is not None:
            try:
                await self._primary.clear(storage_key)
            except ConnectionError:
                await self._fallback.clear(storage_key)
                return
        await self._fallback.clear(storage_key)
