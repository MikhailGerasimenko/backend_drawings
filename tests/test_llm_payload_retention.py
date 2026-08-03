"""Ротация payload в llm_requests_log: при retention=0 отключена (FR-024)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import SessionLocal
from app.models import LlmRequestLog, User, WorkSession
from app.services.llm_payload_retention import purge_old_payloads


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def old_log_with_payload(db: Session):
    user = db.scalar(select(User).limit(1))
    assert user
    ws = WorkSession(
        team_id=user.team_id,
        created_by=user.id,
        title="Retention test",
        status="passport_review",
    )
    db.add(ws)
    db.flush()
    row = LlmRequestLog(
        id=uuid.uuid4(),
        session_id=ws.id,
        user_id=user.id,
        model_name="test/retention",
        timestamp=datetime.now(timezone.utc) - timedelta(days=10),
        payload_prompt='{"test": true}',
        payload_response='{"ok": true}',
        prompt_tokens=1,
        completion_tokens=1,
    )
    db.add(row)
    db.commit()
    return row


def test_purge_skipped_when_retention_zero(db: Session, old_log_with_payload, monkeypatch):
    monkeypatch.setattr(settings, "llm_payload_retention_days", 0)
    n = purge_old_payloads(db)
    assert n == 0
    db.refresh(old_log_with_payload)
    assert old_log_with_payload.payload_prompt is not None
    assert old_log_with_payload.payload_response is not None


def test_purge_clears_when_retention_positive(db: Session, old_log_with_payload, monkeypatch):
    monkeypatch.setattr(settings, "llm_payload_retention_days", 3)
    n = purge_old_payloads(db)
    assert n >= 1
    db.refresh(old_log_with_payload)
    assert old_log_with_payload.payload_prompt is None
    assert old_log_with_payload.payload_response is None
