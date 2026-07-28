"""Ротация payload в llm_requests_log (очистка тел запросов/ответов по сроку).

specs/007-analytics-grafana-rebuild — переименование из finops_aggregate.
Агрегация аналитики вынесена в SQL-представления для Grafana (миграция 013),
поэтому здесь остаётся только очистка payload по сроку хранения.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import LlmRequestLog


def purge_old_payloads(db: Session) -> int:
    """Обнуляет payload_prompt/payload_response старше срока хранения.

    0 или меньше — бессрочное хранение полных payload (purge отключён).
    """
    days = settings.llm_payload_retention_days
    if days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    res = db.execute(
        update(LlmRequestLog)
        .where(LlmRequestLog.timestamp < cutoff)
        .where(
            LlmRequestLog.payload_prompt.isnot(None)
            | LlmRequestLog.payload_response.isnot(None)
        )
        .values(payload_prompt=None, payload_response=None)
    )
    db.commit()
    return res.rowcount or 0
