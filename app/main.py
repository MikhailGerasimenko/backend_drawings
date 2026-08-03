"""
Цифровой Технолог API — FastAPI.
PostgreSQL, auth, sessions, admin; продуктовые метрики — в Grafana (SQL-представления).
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.handlers import app_error_handler, unhandled_error_handler
from app.db import SessionLocal
from app.seed import seed_db

logger = logging.getLogger(__name__)


def _init_sentry() -> None:
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            integrations=[FastApiIntegration()],
            traces_sample_rate=0.0,
        )
        logger.info("Sentry initialized")
    except Exception:
        logger.exception("Sentry init failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _init_sentry()
    db = SessionLocal()
    try:
        seed_db(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Цифровой Технолог API",
    version="0.7.0-metrics",
    description="REST API: specs/001-drawing-tech-assistant/",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(api_router, prefix="/api/v1")


@app.middleware("http")
async def sentry_request_context(request: Request, call_next):
    if settings.sentry_dsn:
        try:
            import sentry_sdk

            with sentry_sdk.configure_scope() as scope:
                scope.set_tag("path", request.url.path)
        except Exception:
            pass
    return await call_next(request)
