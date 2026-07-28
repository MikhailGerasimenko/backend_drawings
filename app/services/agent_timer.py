"""Серверный таймер агентских операций (FR-007/FR-011).

Замеряет wall-time агентской работы (выполнение функций + запросы LLM)
и накапливает её в sessions.agent_seconds. Вместе с user_active_seconds
даёт общее время формирования технологии (НЕ календарная разница).
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import WorkSession


def add_agent_seconds(db: Session, session_id: UUID, seconds: int) -> None:
    """Прибавляет секунды агентской работы к сессии (отдельный commit)."""
    if seconds <= 0:
        return
    s = db.get(WorkSession, session_id)
    if not s:
        return
    s.agent_seconds = (s.agent_seconds or 0) + int(seconds)
    db.commit()


@contextmanager
def track_agent_time(db: Session, session_id: UUID):
    """Контекст-менеджер: измеряет время блока и пишет в agent_seconds.

    Время накапливается даже при исключении внутри блока (finally).
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = int(round(time.perf_counter() - start))
        add_agent_seconds(db, session_id, elapsed)
