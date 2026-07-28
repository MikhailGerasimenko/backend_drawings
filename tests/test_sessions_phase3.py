"""Smoke: сессия, загрузка чертежа, analyze (Phase 3)."""
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_headers():
    r = client.post(
        "/api/v1/auth/login",
        json={"login": "admin", "password": "admin"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_session_drawing_and_analyze(auth_headers):
    r = client.post("/api/v1/sessions", json={}, headers=auth_headers)
    assert r.status_code == 200
    sid = r.json()["id"]

    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    r = client.put(
        f"/api/v1/session/drawing?id={sid}",
        files={"file": ("test.png", io.BytesIO(png), "image/png")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready_to_send"
    assert body["preview_url"].startswith("data:image/png;base64,")

    r = client.post(f"/api/v1/session/analyze?id={sid}", headers=auth_headers)
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "analyzing"
    assert r.json()["drawing_sent_at"]

    # Повторная замена после отправки — запрещена
    r = client.put(
        f"/api/v1/session/drawing?id={sid}",
        files={"file": ("test2.png", io.BytesIO(png), "image/png")},
        headers=auth_headers,
    )
    assert r.status_code == 409
