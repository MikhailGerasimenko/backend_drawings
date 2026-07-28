"""Health check endpoints."""

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/api/v1/health")
def api_v1_health():
    return {
        "status": "ok",
        "version": "0.7.0-metrics",
        "database_configured": bool(settings.database_url),
        "sentry": bool(settings.sentry_dsn),
    }
