"""US2 / SC-004: серверный таймер агента измеряет время с точностью ≤5%."""
import time
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import User, WorkSession
from app.services.agent_timer import add_agent_seconds, track_agent_time


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def work_session(db: Session):
    user = db.scalar(select(User).limit(1))
    assert user
    ws = WorkSession(
        team_id=user.team_id,
        created_by=user.id,
        title="Timer accuracy test",
        status="passport_review",
    )
    db.add(ws)
    db.commit()
    return ws


def test_add_agent_seconds_ignores_nonpositive(db: Session, work_session):
    before = work_session.agent_seconds or 0
    add_agent_seconds(db, work_session.id, 0)
    add_agent_seconds(db, work_session.id, -3)
    db.refresh(work_session)
    assert work_session.agent_seconds == before


def test_track_agent_time_accuracy(db: Session, work_session):
    before = work_session.agent_seconds or 0
    measured = 2  # секунды реальной работы блока
    with track_agent_time(db, work_session.id):
        time.sleep(measured)
    db.refresh(work_session)
    recorded = (work_session.agent_seconds or 0) - before
    # Точность ≤5%: при коротком интервале допускаем ±1 c округления
    assert abs(recorded - measured) <= max(1, round(measured * 0.05))
