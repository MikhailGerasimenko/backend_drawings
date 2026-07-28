"""Схемы health endpoint."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str | None = None
    database_configured: bool | None = None
    sentry: bool | None = None
