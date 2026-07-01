from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.handlers import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.middleware import RequestIDMiddleware
from app.core.sentry import init_sentry
from app.core.db import init_db


@asynccontextmanager
async def lifespan(application: FastAPI):  # type: ignore[name-defined]
    """Application lifespan: startup and shutdown events."""
    # Startup
    application.state.start_time = _get_current_timestamp()
    await init_db()
    yield
    # Shutdown
    application.state.start_time = None


app = FastAPI(
    title=settings.app_name,
    description="Template project with health check and hello world endpoints",
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

init_sentry(app)

app.add_middleware(RequestIDMiddleware)

app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to FastAPI Template",
        "version": settings.app_version,
        "docs": "/docs",
    }


def _get_current_timestamp() -> str:
    """Return current ISO timestamp with timezone."""
    from pytz import timezone

    return str(
        datetime.now(timezone(settings.time_zone)).isoformat()
    )
