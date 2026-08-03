"""Обработчики исключений FastAPI."""
import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=error_body(exc.code, exc.message))


def _drawing_meta_from_request(request: Request) -> dict:
    meta: dict = {}
    session_id = request.query_params.get("id")
    if session_id:
        meta["session_id"] = session_id
    return meta


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error")
    if settings.sentry_dsn:
        try:
            import sentry_sdk

            with sentry_sdk.push_scope() as scope:
                auth = request.headers.get("authorization") or ""
                if auth.lower().startswith("bearer "):
                    scope.set_tag("has_auth", "true")
                for k, v in _drawing_meta_from_request(request).items():
                    scope.set_tag(k, str(v))
                sentry_sdk.capture_exception(exc)
        except Exception:
            logger.exception("sentry capture failed")
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_ERROR", str(exc) or "Внутренняя ошибка"),
    )
"""Обработчики исключений FastAPI."""
import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=error_body(exc.code, exc.message))


def _drawing_meta_from_request(request: Request) -> dict:
    meta: dict = {}
    session_id = request.query_params.get("id")
    if session_id:
        meta["session_id"] = session_id
    return meta


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error")
    if settings.sentry_dsn:
        try:
            import sentry_sdk

            with sentry_sdk.push_scope() as scope:
                auth = request.headers.get("authorization") or ""
                if auth.lower().startswith("bearer "):
                    scope.set_tag("has_auth", "true")
                for k, v in _drawing_meta_from_request(request).items():
                    scope.set_tag(k, str(v))
                sentry_sdk.capture_exception(exc)
        except Exception:
            logger.exception("sentry capture failed")
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_ERROR", str(exc) or "Внутренняя ошибка"),
    )
