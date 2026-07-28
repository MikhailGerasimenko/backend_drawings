"""Оценка сессии после согласования технологии — specs/005."""
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.db import SessionLocal
from app.main import app
from app.models import WorkSession
from tests.session_flow_helpers import session_at_technology_review

client = TestClient(app)


@pytest.fixture
def auth_headers():
    r = client.post(
        "/api/v1/auth/login",
        json={"login": "admin", "password": "admin"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def _session_at_technology_review(headers):
    r = client.post("/api/v1/sessions", json={}, headers=headers)
    sid = r.json()["id"]
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    client.put(
        f"/api/v1/session/drawing?id={sid}",
        files={"file": ("t.png", io.BytesIO(png), "image/png")},
        headers=headers,
    )
    client.post(f"/api/v1/session/analyze?id={sid}", headers=headers)
    session_at_technology_review(client, headers, sid)
    return sid


def _approve_technology(headers, sid: str) -> dict:
    r = client.post(
        f"/api/v1/session/technology/approve?id={sid}",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_feedback_happy_path_five_stars(auth_headers):
    sid = _session_at_technology_review(auth_headers)
    body = _approve_technology(auth_headers, sid)
    assert body["status"] == "completed"
    assert body["show_feedback_prompt"] is True
    assert body["feedback_submitted"] is False

    r = client.post(
        f"/api/v1/session/feedback?id={sid}",
        json={"stars": 5},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feedback_submitted"] is True
    assert data["show_feedback_prompt"] is False


def test_feedback_low_stars_requires_comment(auth_headers):
    sid = _session_at_technology_review(auth_headers)
    _approve_technology(auth_headers, sid)

    r = client.post(
        f"/api/v1/session/feedback?id={sid}",
        json={"stars": 3},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"

    r2 = client.post(
        f"/api/v1/session/feedback?id={sid}",
        json={"stars": 3, "comment": "Часто ошибается в термообработке"},
        headers=auth_headers,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["feedback_submitted"] is True

    sid2 = _session_at_technology_review(auth_headers)
    _approve_technology(auth_headers, sid2)
    r3 = client.post(
        f"/api/v1/session/feedback?id={sid2}",
        json={"stars": 4},
        headers=auth_headers,
    )
    assert r3.status_code == 400


def test_feedback_duplicate_conflict(auth_headers):
    sid = _session_at_technology_review(auth_headers)
    _approve_technology(auth_headers, sid)
    client.post(
        f"/api/v1/session/feedback?id={sid}",
        json={"stars": 5},
        headers=auth_headers,
    )
    r = client.post(
        f"/api/v1/session/feedback?id={sid}",
        json={"stars": 4, "comment": "повтор"},
        headers=auth_headers,
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_feedback_prompt_until_submitted(auth_headers):
    sid = _session_at_technology_review(auth_headers)
    _approve_technology(auth_headers, sid)
    r = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r.json()["show_feedback_prompt"] is True

    client.post(
        f"/api/v1/session/feedback?id={sid}",
        json={"stars": 5},
        headers=auth_headers,
    )
    r2 = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r2.json()["show_feedback_prompt"] is False


def test_legacy_completed_no_prompt(auth_headers):
    sid = _session_at_technology_review(auth_headers)
    db = SessionLocal()
    try:
        s = db.get(WorkSession, uuid.UUID(sid))
        s.status = "completed"
        s.completed_at = s.updated_at
        s.completed_by = None
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r.json()["show_feedback_prompt"] is False


def test_feedback_forbidden_for_other_user(auth_headers):
    sid = _session_at_technology_review(auth_headers)
    _approve_technology(auth_headers, sid)
    client.post(
        f"/api/v1/session/feedback?id={sid}",
        json={"stars": 5},
        headers=auth_headers,
    )

    teams = client.get("/api/v1/admin/teams", headers=auth_headers).json()["teams"]
    team_id = teams[0]["id"]
    login = "feedback_test_user_" + uuid.uuid4().hex[:8]
    client.post(
        "/api/v1/admin/users",
        json={
            "login": login,
            "display_name": "Feedback Tester",
            "password": "testpass123",
            "team_id": team_id,
            "role": "user",
        },
        headers=auth_headers,
    )
    r_login = client.post(
        "/api/v1/auth/login",
        json={"login": login, "password": "testpass123"},
    )
    other_headers = {"Authorization": "Bearer " + r_login.json()["token"]}

    r_get = client.get(f"/api/v1/session?id={sid}", headers=other_headers)
    assert r_get.status_code == 200
    assert r_get.json()["show_feedback_prompt"] is False
    assert r_get.json()["session_feedback"] is not None
    assert r_get.json()["session_feedback"]["editable"] is False

    r_post = client.post(
        f"/api/v1/session/feedback?id={sid}",
        json={"stars": 5},
        headers=other_headers,
    )
    assert r_post.status_code == 403
    assert r_post.json()["error"]["code"] == "FORBIDDEN"


def test_feedback_update_within_24h(auth_headers):
    sid = _session_at_technology_review(auth_headers)
    _approve_technology(auth_headers, sid)
    client.post(
        f"/api/v1/session/feedback?id={sid}",
        json={"stars": 5},
        headers=auth_headers,
    )

    r = client.put(
        f"/api/v1/session/feedback?id={sid}",
        json={"stars": 2, "comment": "Нужно улучшить точность маршрута"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    fb = r.json()["session_feedback"]
    assert fb["stars"] == 2
    assert fb["comment"] == "Нужно улучшить точность маршрута"
    assert fb["editable"] is True


def test_feedback_update_after_24h_forbidden(auth_headers):
    from datetime import timedelta

    from app.models import SessionFeedback, utcnow

    sid = _session_at_technology_review(auth_headers)
    _approve_technology(auth_headers, sid)
    client.post(
        f"/api/v1/session/feedback?id={sid}",
        json={"stars": 5},
        headers=auth_headers,
    )

    db = SessionLocal()
    try:
        row = db.scalar(
            select(SessionFeedback).where(SessionFeedback.session_id == uuid.UUID(sid))
        )
        row.created_at = utcnow() - timedelta(hours=25)
        db.commit()
    finally:
        db.close()

    r = client.put(
        f"/api/v1/session/feedback?id={sid}",
        json={"stars": 3, "comment": "Поздно"},
        headers=auth_headers,
    )
    assert r.status_code == 403
    assert "24" in r.json()["error"]["message"]
