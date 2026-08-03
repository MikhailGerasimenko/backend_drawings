"""US2: накопление чистого активного времени пользователя через API (FR-008…FR-010)."""
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_headers():
    r = client.post("/api/v1/auth/login", json={"login": "admin", "password": "admin"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _new_session(headers) -> str:
    r = client.post("/api/v1/sessions", json={}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_active_time_accumulates(auth_headers):
    sid = _new_session(auth_headers)
    r = client.post(
        f"/api/v1/session/active-time?id={sid}",
        json={"delta_seconds": 12},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["user_active_seconds"] == 12

    # Вторая дельта суммируется с первой
    r = client.post(
        f"/api/v1/session/active-time?id={sid}",
        json={"delta_seconds": 8},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["user_active_seconds"] == 20


def test_active_time_rejects_negative(auth_headers):
    sid = _new_session(auth_headers)
    r = client.post(
        f"/api/v1/session/active-time?id={sid}",
        json={"delta_seconds": -5},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_active_time_unknown_session_404(auth_headers):
    import uuid

    r = client.post(
        f"/api/v1/session/active-time?id={uuid.uuid4()}",
        json={"delta_seconds": 5},
        headers=auth_headers,
    )
    assert r.status_code == 404
