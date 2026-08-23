from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from ipaddress import ip_address
from typing import NoReturn
from urllib.parse import urlsplit

from app.core.errors import DomainError

_ORIGIN_ERROR_CODE = "ORIGIN_NOT_ALLOWED"
_ORIGIN_ERROR_MESSAGE = "请求来源不受信任"
_ALLOWED_SCHEMES = {"http", "https"}
_DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass(frozen=True, slots=True)
class _NormalizedOrigin:
    scheme: str
    hostname: str
    port: int


def _raise_origin_not_allowed() -> NoReturn:
    raise DomainError(403, _ORIGIN_ERROR_CODE, _ORIGIN_ERROR_MESSAGE)


def _normalize_hostname(hostname: str) -> str:
    lowered_hostname = hostname.lower()
    try:
        return str(ip_address(lowered_hostname))
    except ValueError:
        return lowered_hostname


def _normalize_origin_value(raw_value: str, *, allow_path: bool) -> _NormalizedOrigin:
    candidate = raw_value.strip()
    if not candidate:
        raise ValueError("origin 不能为空")

    parsed = urlsplit(candidate)
    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError("origin 协议非法")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("origin 不允许包含用户信息")

    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise ValueError("origin 主机或端口非法") from error

    if not hostname:
        raise ValueError("origin 缺少主机")
    if not allow_path and (parsed.path or parsed.query or parsed.fragment):
        raise ValueError("origin 不允许包含路径或查询")

    normalized_hostname = _normalize_hostname(hostname)
    normalized_port = port or _DEFAULT_PORTS[scheme]
    return _NormalizedOrigin(
        scheme=scheme,
        hostname=normalized_hostname,
        port=normalized_port,
    )


def assert_request_origin_allowed(
    *,
    origin: str | None,
    referer: str | None,
    allowed_origins: Collection[str],
) -> None:
    normalized_allowlist = {
        _normalize_origin_value(configured_origin, allow_path=False)
        for configured_origin in allowed_origins
    }

    if origin is not None and origin.strip():
        try:
            normalized_origin = _normalize_origin_value(origin, allow_path=False)
        except ValueError as error:
            raise DomainError(403, _ORIGIN_ERROR_CODE, _ORIGIN_ERROR_MESSAGE) from error
        if normalized_origin not in normalized_allowlist:
            _raise_origin_not_allowed()
        return

    if referer is None or not referer.strip():
        _raise_origin_not_allowed()

    try:
        normalized_referer_origin = _normalize_origin_value(referer, allow_path=True)
    except ValueError as error:
        raise DomainError(403, _ORIGIN_ERROR_CODE, _ORIGIN_ERROR_MESSAGE) from error

    if normalized_referer_origin not in normalized_allowlist:
        _raise_origin_not_allowed()
