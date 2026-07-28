"""Промпты и model-config в админке."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _login(login, password):
    r = client.post("/api/v1/auth/login", json={"login": login, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def super_headers():
    return _login("admin", "admin")


def test_prompts_version_and_restore(super_headers):
    teams = client.get("/api/v1/admin/teams", headers=super_headers).json()["teams"]
    tid = teams[0]["id"]
    r = client.get(f"/api/v1/admin/prompts?team_id={tid}", headers=super_headers)
    assert r.status_code == 200
    assert r.json()["passport"]["current_text"]

    r = client.post(
        "/api/v1/admin/prompts",
        headers=super_headers,
        json={"team_id": tid, "kind": "passport", "text": "Тестовый промпт v2"},
    )
    assert r.status_code == 200
    assert r.json()["version_no"] >= 2

    r = client.get(f"/api/v1/admin/prompts?team_id={tid}", headers=super_headers)
    versions = r.json()["passport"]["versions"]
    old = next(v for v in versions if v["version_no"] == 1)
    r = client.post(
        "/api/v1/admin/prompts/restore",
        headers=super_headers,
        json={"team_id": tid, "version_id": old["id"]},
    )
    assert r.status_code == 200
    r = client.get(f"/api/v1/admin/prompts?team_id={tid}", headers=super_headers)
    assert r.json()["passport"]["active_version_id"] == old["id"]


def test_model_config_superuser_only(super_headers):
    r = client.get("/api/v1/admin/model-config", headers=super_headers)
    assert r.status_code == 200
    data = r.json()
    assert "passport" in data
    assert "technology" in data
    assert data["passport"]["temperature"] == 0.2
    assert data["technology"]["temperature"] == 0.2

    r = client.post(
        "/api/v1/admin/model-config",
        headers=super_headers,
        json={
            "passport": {"model": "test/passport-model", "temperature": 0.1},
            "technology": {"model": "test/tech-model", "temperature": 0.5},
        },
    )
    assert r.status_code == 200

    r = client.get("/api/v1/admin/model-config", headers=super_headers)
    cfg = r.json()
    assert cfg["passport"]["temperature"] == 0.1
    assert cfg["technology"]["temperature"] == 0.5
