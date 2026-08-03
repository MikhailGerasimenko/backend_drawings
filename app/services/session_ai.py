"""Фоновая генерация паспорта/технологии (не блокирует HTTP-ответ)."""
import logging
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import SESSION_STATUS_DELETED, WorkSession
from app.services.agent_timer import track_agent_time
from app.services.ai import process_session_ai

logger = logging.getLogger(__name__)


async def run_session_ai_background(session_id: UUID, user_id: UUID) -> None:
    db = SessionLocal()
    try:
        s = db.get(WorkSession, session_id)
        if not s or s.status == SESSION_STATUS_DELETED:
            return
        # FR-007/FR-011: время агентской работы (функции + LLM) копится в agent_seconds
        with track_agent_time(db, session_id):
            await process_session_ai(db, s, user_id)
    except Exception:
        logger.exception("background AI failed session=%s", session_id)
    finally:
        db.close()


def enqueue_session_ai(
    background_tasks: BackgroundTasks, session_id: UUID, user_id: UUID
) -> None:
    background_tasks.add_task(run_session_ai_background, session_id, user_id)
