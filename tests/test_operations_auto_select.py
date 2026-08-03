"""Пропуск ручного выбора операций (auto-select)."""
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import ai as ai_module

client = TestClient(app)


@pytest.fixture
def auth_headers():
    r = client.post(
        "/api/v1/auth/login",
        json={"login": "admin", "password": "admin"},
    )
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _session_at_operations_selection(auth_headers):
    r = client.post("/api/v1/sessions", json={}, headers=auth_headers)
    sid = r.json()["id"]
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    client.put(
        f"/api/v1/session/drawing?id={sid}",
        files={"file": ("t.png", io.BytesIO(png), "image/png")},
        headers=auth_headers,
    )
    client.post(f"/api/v1/session/analyze?id={sid}", headers=auth_headers)
    client.post(f"/api/v1/session/passport/approve?id={sid}", headers=auth_headers)
    return sid


def test_auto_select_empty_catalog_400(auth_headers, monkeypatch):
    sid = _session_at_operations_selection(auth_headers)
    monkeypatch.setattr(
        "app.api.v1.sessions.list_catalog",
        lambda db, team_id: [],
    )
    r = client.post(
        f"/api/v1/session/technology/auto-select?id={sid}",
        json={},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "пуст" in r.json()["error"]["message"].lower()


def test_auto_select_mock_success(auth_headers):
    sid = _session_at_operations_selection(auth_headers)
    catalog = client.get("/api/v1/operation-catalog", headers=auth_headers).json()["entries"]
    assert catalog
    r = client.post(
        f"/api/v1/session/technology/auto-select?id={sid}",
        json={},
        headers=auth_headers,
    )
    assert r.status_code == 202
    # Сразу расчёт припусков или технология (без generating_operations)
    assert r.json()["status"] in ("generating_technology", "generating_blank_allowance")
    assert not r.json()["selected_operations"]
    # BackgroundTasks в TestClient выполняются синхронно
    body = client.get(f"/api/v1/session?id={sid}", headers=auth_headers).json()
    assert body["status"] in (
        "technology_review",
        "generating_blank_allowance",
        "blank_allowance_review",
    )
    if body["status"] == "technology_review":
        assert body["selected_operations"]


def test_auto_select_llm_error_returns_failed(auth_headers, monkeypatch):
    sid = _session_at_operations_selection(auth_headers)

    async def fail_technology(*args, **kwargs):
        from app.core.exceptions import AppError

        raise AppError("AI_UNAVAILABLE", "test fail", 502)

    monkeypatch.setattr(ai_module, "generate_technology", fail_technology)

    class FakeConn:
        use_mock = False
        api_key = "k"
        model = "test/model"
        base_url = "http://test"
        temperature = 0.2

    class FakeCfg:
        technology = FakeConn()
        blank_allowance = FakeConn()
        verify_ssl = True

    monkeypatch.setattr(ai_module, "get_ai_config", lambda db: FakeCfg())

    r = client.post(
        f"/api/v1/session/technology/auto-select?id={sid}",
        json={},
        headers=auth_headers,
    )
    assert r.status_code == 202
    body = client.get(f"/api/v1/session?id={sid}", headers=auth_headers).json()
    assert body["status"] in ("technology_failed", "blank_allowance_failed")
