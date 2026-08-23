from __future__ import annotations

import secrets

from app.core.errors import DomainError

_CSRF_ERROR_CODE = "CSRF_VALIDATION_FAILED"
_CSRF_ERROR_MESSAGE = "CSRF 校验失败"


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def assert_csrf_valid(cookie_token: str | None, header_token: str | None) -> None:
    if cookie_token is None or header_token is None:
        raise DomainError(403, _CSRF_ERROR_CODE, _CSRF_ERROR_MESSAGE)
    if not cookie_token.strip() or not header_token.strip():
        raise DomainError(403, _CSRF_ERROR_CODE, _CSRF_ERROR_MESSAGE)
    if not secrets.compare_digest(cookie_token, header_token):
        raise DomainError(403, _CSRF_ERROR_CODE, _CSRF_ERROR_MESSAGE)
