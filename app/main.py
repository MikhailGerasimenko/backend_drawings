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

app = FastAPI(
    title=settings.app_name,
    description="Template project with health check and hello world endpoints",
    version=settings.app_version,
    debug=settings.debug,
)

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
