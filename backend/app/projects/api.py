from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    get_db_session,
    get_now_provider,
    get_settings,
    require_business_access,
)
from app.auth.service import AuthenticatedContext
from app.core.config import Settings
from app.core.csrf import assert_csrf_valid
from app.core.errors import DomainError
from app.core.origin import assert_request_origin_allowed
from app.core.request_id import ensure_request_id
from app.projects import queries
from app.projects.idempotency import normalize_idempotency_key
from app.projects.schemas import (
    CreateProjectRequest,
    ProjectCreatedResponse,
    ProjectListResponse,
    ProjectOverviewResponse,
    WorkbenchResponse,
)
from app.projects.service import ProjectCreateService

router = APIRouter(prefix="/projects", tags=["projects"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
NowProvider = Annotated[Callable[[], datetime], Depends(get_now_provider)]
BusinessContext = Annotated[AuthenticatedContext, Depends(require_business_access)]


async def require_project_origin(
    request: Request,
    settings: AppSettings,
) -> None:
    assert_request_origin_allowed(
        origin=request.headers.get("Origin"),
        referer=request.headers.get("Referer"),
        allowed_origins=settings.allowed_origins,
    )


async def require_project_business_context(
    _: Annotated[None, Depends(require_project_origin)],
    context: BusinessContext,
) -> AuthenticatedContext:
    return context


async def require_project_csrf(
    request: Request,
    settings: AppSettings,
    context: Annotated[AuthenticatedContext, Depends(require_project_business_context)],
) -> AuthenticatedContext:
    assert_csrf_valid(
        request.cookies.get(settings.csrf_cookie_name),
        request.headers.get("X-CSRF-Token"),
    )
    return context


async def require_project_idempotency(
    request: Request,
    context: Annotated[AuthenticatedContext, Depends(require_project_csrf)],
) -> tuple[AuthenticatedContext, str]:
    return context, normalize_idempotency_key(request.headers.get("Idempotency-Key"))


async def parse_create_project_request(
    request: Request,
    state: Annotated[tuple[AuthenticatedContext, str], Depends(require_project_idempotency)],
) -> tuple[AuthenticatedContext, str, CreateProjectRequest]:
    body: object | None = None
    try:
        body = await request.json()
        payload = CreateProjectRequest.model_validate(body)
    except json.JSONDecodeError as exc:
        raise RequestValidationError(
            [
                {
                    "type": "json_invalid",
                    "loc": ("body", exc.pos),
                    "msg": "JSON decode error",
                    "input": {},
                    "ctx": {"error": exc.msg},
                }
            ],
            body=None,
        ) from exc
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(), body=body) from exc
    return state[0], state[1], payload


ProjectCreateInput = Annotated[
    tuple[AuthenticatedContext, str, CreateProjectRequest],
    Depends(parse_create_project_request),
]


@router.post("", response_model=ProjectCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: Request,
    response: Response,
    session: DbSession,
    now_provider: NowProvider,
    project_input: ProjectCreateInput,
) -> ProjectCreatedResponse:
    context, idempotency_key, payload = project_input
    service = ProjectCreateService(
        now_provider=now_provider,
        hooks=request.app.state.project_creation_hooks,
    )
    status_code, result = await service.create_project(
        session,
        context=context,
        payload=payload,
        idempotency_key=idempotency_key,
        request_id=ensure_request_id(request),
    )
    response.status_code = status_code
    return result


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    session: DbSession,
    context: BusinessContext,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    keyword: Annotated[str | None, Query(max_length=255)] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    owner_user_id: UUID | None = None,
    only_my_projects: bool = False,
    sort: Annotated[str, Query(pattern="^(-)?created_at$")] = "-created_at",
) -> ProjectListResponse:
    items, total = await queries.list_projects(
        session,
        actor_user_id=context.user_id,
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=status_filter,
        owner_user_id=owner_user_id,
        only_my_projects=only_my_projects,
        sort=sort,
    )
    return ProjectListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/{project_id}/overview", response_model=ProjectOverviewResponse)
async def get_project_overview(
    session: DbSession,
    context: BusinessContext,
    project_id: UUID,
) -> ProjectOverviewResponse:
    overview = await queries.get_project_overview(
        session,
        project_id=project_id,
        actor_user_id=context.user_id,
    )
    if overview is None:
        raise DomainError(404, "NOT_FOUND", "项目不存在")
    return overview


me_router = APIRouter(prefix="/me", tags=["workbench"])


@me_router.get("/workbench", response_model=WorkbenchResponse)
async def get_workbench(
    session: DbSession,
    context: BusinessContext,
) -> WorkbenchResponse:
    recent_projects = await queries.get_workbench(
        session,
        actor_user_id=context.user_id,
    )
    return WorkbenchResponse(
        personal_todos=[],
        recent_projects=recent_projects,
        running_tasks=[],
        failed_tasks=[],
    )
