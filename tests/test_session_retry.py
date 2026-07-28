"""Повтор после technology_failed — паспорт сохраняется."""
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import WorkSession, utcnow
from app.schemas.base import PartPassport
from app.services.ai import mock_passport

client = TestClient(app)


@pytest.fixture
def auth_headers():
    r = client.post("/api/v1/auth/login", json={"login": "admin", "password": "admin"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_retry_keeps_passport(auth_headers, monkeypatch):
    r = client.post("/api/v1/sessions", json={}, headers=auth_headers)
    sid = UUID(r.json()["id"])
    passport = mock_passport()
    PartPassport.model_validate(passport)

    db = SessionLocal()
    s = db.get(WorkSession, sid)
    s.passport = passport
    s.status = "technology_failed"
    s.technology_text = None
    s.updated_at = utcnow()
    db.commit()
    db.close()

    async def fake_bg(session_id, user_id):
        db2 = SessionLocal()
        try:
            sess = db2.get(WorkSession, session_id)
            sess.technology_text = "Технология"
            sess.technology_json = {
                "schema_version": "1.0",
                "part_designation": "Деталь",
                "operations": [{"number": 1, "name": "Оп", "description": "Описание"}],
            }
            sess.status = "technology_review"
            db2.commit()
        finally:
            db2.close()

    monkeypatch.setattr(
        "app.services.session_ai.run_session_ai_background", fake_bg
    )

    res = client.post(f"/api/v1/session/retry?id={sid}", headers=auth_headers)
    assert res.status_code == 202
    data = res.json()
    assert data["passport"]
    assert data["status"] == "generating_technology"
    res2 = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert res2.json()["status"] == "technology_review"
