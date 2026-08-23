from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_db_session, get_now_provider, get_rate_limiter, get_settings
from app.auth.schemas import LoginRequest, PasswordChangeRequest, SessionResponse
from app.auth.service import LoginService
from app.core.config import Settings
from app.core.csrf import assert_csrf_valid
from app.core.errors import DomainError
from app.core.origin import assert_request_origin_allowed
from app.core.rate_limit import FallbackLoginRateLimiter
from app.core.request_id import ensure_request_id

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
AppLimiter = Annotated[FallbackLoginRateLimiter, Depends(get_rate_limiter)]
NowProvider = Annotated[Callable[[], datetime], Depends(get_now_provider)]


@router.post("/login", response_model=SessionResponse, status_code=status.HTTP_200_OK)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: DbSession,
    settings: AppSettings,
    limiter: AppLimiter,
    now_provider: NowProvider,
) -> SessionResponse:
    assert_request_origin_allowed(
        origin=request.headers.get("Origin"),
        referer=request.headers.get("Referer"),
        allowed_origins=settings.allowed_origins,
    )
    source = (
        request.client.host if request.client is not None and request.client.host else "unknown"
    )
    service = LoginService(settings=settings, limiter=limiter, now_provider=now_provider)
    result = await service.login(
        session,
        login_name=payload.login_name,
        password=payload.password.get_secret_value(),
        source=source,
        request_id=ensure_request_id(request),
    )
    max_age = settings.session_absolute_hours * 3600
    session_cookie_kwargs = _build_set_cookie_kwargs(
        settings,
        max_age=max_age,
        httponly=True,
    )
    csrf_cookie_kwargs = _build_set_cookie_kwargs(
        settings,
        max_age=max_age,
        httponly=False,
    )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=result.session_token,
        **session_cookie_kwargs,
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=result.csrf_token,
        **csrf_cookie_kwargs,
    )
    return result.response


@router.get("/session", response_model=SessionResponse, status_code=status.HTTP_200_OK)
async def get_session(
    request: Request,
    session: DbSession,
    settings: AppSettings,
    limiter: AppLimiter,
    now_provider: NowProvider,
) -> SessionResponse:
    session_token = request.cookies.get(settings.session_cookie_name)
    if session_token is None or session_token == "":
        raise DomainError(401, "UNAUTHENTICATED", "未登录")

    service = LoginService(settings=settings, limiter=limiter, now_provider=now_provider)
    result = await service.get_session(
        session,
        session_token=session_token,
        request_id=ensure_request_id(request),
    )
    if result.error is not None:
        raise result.error
    assert result.response is not None
    return result.response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: DbSession,
    settings: AppSettings,
    limiter: AppLimiter,
    now_provider: NowProvider,
) -> None:
    assert_request_origin_allowed(
        origin=request.headers.get("Origin"),
        referer=request.headers.get("Referer"),
        allowed_origins=settings.allowed_origins,
    )
    session_token = request.cookies.get(settings.session_cookie_name)
    if session_token is None or session_token == "":
        raise DomainError(401, "UNAUTHENTICATED", "未登录")
    assert_csrf_valid(
        request.cookies.get(settings.csrf_cookie_name),
        request.headers.get("X-CSRF-Token"),
    )

    service = LoginService(settings=settings, limiter=limiter, now_provider=now_provider)
    await service.logout(
        session,
        session_token=session_token,
        request_id=ensure_request_id(request),
    )
    _clear_auth_cookies(response, settings)


@router.post("/password/change", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    session: DbSession,
    settings: AppSettings,
    limiter: AppLimiter,
    now_provider: NowProvider,
) -> None:
    assert_request_origin_allowed(
        origin=request.headers.get("Origin"),
        referer=request.headers.get("Referer"),
        allowed_origins=settings.allowed_origins,
    )
    session_token = request.cookies.get(settings.session_cookie_name)
    if session_token is None or session_token == "":
        raise DomainError(401, "UNAUTHENTICATED", "未登录")
    assert_csrf_valid(
        request.cookies.get(settings.csrf_cookie_name),
        request.headers.get("X-CSRF-Token"),
    )

    service = LoginService(settings=settings, limiter=limiter, now_provider=now_provider)
    await service.change_password(
        session,
        session_token=session_token,
        current_password=payload.current_password.get_secret_value(),
        new_password=payload.new_password.get_secret_value(),
        request_id=ensure_request_id(request),
    )
    response.status_code = status.HTTP_204_NO_CONTENT


def _build_cookie_kwargs(
    settings: Settings,
    *,
    httponly: bool,
) -> dict[str, Any]:
    return {
        "httponly": httponly,
        "secure": settings.session_cookie_secure,
        "samesite": "lax",
        "path": "/",
        "domain": settings.session_cookie_domain,
    }


def _build_set_cookie_kwargs(
    settings: Settings,
    *,
    max_age: int,
    httponly: bool,
) -> dict[str, Any]:
    return {
        **_build_cookie_kwargs(settings, httponly=httponly),
        "max_age": max_age,
    }


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        **_build_cookie_kwargs(settings, httponly=True),
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        **_build_cookie_kwargs(settings, httponly=False),
    )
