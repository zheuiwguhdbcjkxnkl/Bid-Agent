from __future__ import annotations

from fastapi import APIRouter

from app.auth.api import router as auth_router
from app.projects.api import me_router
from app.projects.api import router as projects_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(projects_router)
api_router.include_router(me_router)
