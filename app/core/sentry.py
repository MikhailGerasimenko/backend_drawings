"""Sentry integration for error monitoring."""

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

from app.core.config import settings


def init_sentry(app: FastAPI) -> None:  # type: ignore[name-defined]
    """Initialize Sentry if DSN is configured."""
    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=1.0,
        environment="production",  # Can be overridden via env
        integrations=[FastApiIntegration()],
    )
