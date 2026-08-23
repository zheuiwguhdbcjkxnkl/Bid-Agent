from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from datetime import datetime
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthenticatedContext, LoginService
from app.auth.service import require_business_access as _require_business_access
from app.core.config import Settings
from app.core.db import SessionFactory
from app.core.errors import DomainError
from app.core.rate_limit import FallbackLoginRateLimiter
from app.core.request_id import ensure_request_id


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_factory = cast(SessionFactory, request.app.state.session_factory)
    async with session_factory() as session:
        yield session


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_rate_limiter(request: Request) -> FallbackLoginRateLimiter:
    return cast(FallbackLoginRateLimiter, request.app.state.limiter)


def get_now_provider(request: Request) -> Callable[[], datetime]:
    return cast(Callable[[], datetime], request.app.state.clock)


async def get_authenticated_context(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    limiter: Annotated[FallbackLoginRateLimiter, Depends(get_rate_limiter)],
    now_provider: Annotated[Callable[[], datetime], Depends(get_now_provider)],
) -> AuthenticatedContext:
    session_token = request.cookies.get(settings.session_cookie_name)
    if session_token is None or session_token == "":
        raise DomainError(401, "UNAUTHENTICATED", "未登录")

    service = LoginService(settings=settings, limiter=limiter, now_provider=now_provider)
    context = await service.get_authenticated_context(
        session,
        session_token=session_token,
        request_id=ensure_request_id(request),
        for_update=False,
    )
    await session.commit()
    return context


async def require_authenticated_context(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
) -> AuthenticatedContext:
    return context


async def require_business_access(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
) -> AuthenticatedContext:
    return _require_business_access(context)
