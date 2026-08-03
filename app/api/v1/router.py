from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    admin_operations,
    admin_prompts,
    auth,
    health,
    sessions,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(sessions.router)
api_router.include_router(admin.router)
api_router.include_router(admin_prompts.router)
api_router.include_router(admin_operations.router)
api_router.include_router(health.router)
