"""Справочник операций и генерация технологии."""
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.session_flow_helpers import generate_technology_with_catalog

client = TestClient(app)


@pytest.fixture
def auth_headers():
    r = client.post(
        "/api/v1/auth/login",
        json={"login": "admin", "password": "admin"},
    )
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_operation_catalog_default_and_generate(auth_headers):
    r = client.get("/api/v1/operation-catalog", headers=auth_headers)
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert len(entries) >= 10
    assert entries[0]["operation"] and entries[0]["equipment"]

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
    r = client.post(f"/api/v1/session/passport/approve?id={sid}", headers=auth_headers)
    assert r.json()["status"] == "operations_selection"

    r = client.post(
        f"/api/v1/session/technology/generate?id={sid}",
        json={"catalog_ids": []},
        headers=auth_headers,
    )
    assert r.status_code == 422

    generate_technology_with_catalog(client, auth_headers, sid)
    r = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r.json()["status"] == "generating_technology" or r.json()["status"] == "technology_review"


def test_admin_put_operation_catalog(auth_headers):
    teams = client.get("/api/v1/admin/teams", headers=auth_headers).json()["teams"]
    tid = teams[0]["id"]
    r = client.put(
        "/api/v1/admin/operation-catalog",
        json={
            "team_id": tid,
            "entries": [
                {"operation": "Тестовая", "equipment": "Станок-1"},
                {"operation": "Отпуск низкий", "equipment": "печь НК6.6/5И4"},
            ],
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert len(r.json()["entries"]) == 2


def test_admin_catalog_preserves_entry_order(auth_headers):
    teams = client.get("/api/v1/admin/teams", headers=auth_headers).json()["teams"]
    tid = teams[0]["id"]
    entries = [
        {"operation": "Z-last", "equipment": "Станок-Z"},
        {"operation": "A-first", "equipment": "Станок-A"},
    ]
    r = client.put(
        "/api/v1/admin/operation-catalog",
        json={"team_id": tid, "entries": entries},
        headers=auth_headers,
    )
    assert r.status_code == 200
    saved = r.json()["entries"]
    assert [e["operation"] for e in saved] == ["Z-last", "A-first"]
    assert [e["sort_order"] for e in saved] == [0, 1]

    r = client.get("/api/v1/operation-catalog", headers=auth_headers)
    assert r.status_code == 200
    listed = r.json()["entries"]
    assert [e["operation"] for e in listed[:2]] == ["Z-last", "A-first"]


def test_admin_catalog_preserves_uuid_on_update(auth_headers):
    """Порядок, название и оборудование меняются — id строки остаётся прежним."""
    teams = client.get("/api/v1/admin/teams", headers=auth_headers).json()["teams"]
    tid = teams[0]["id"]
    r = client.put(
        "/api/v1/admin/operation-catalog",
        json={
            "team_id": tid,
            "entries": [
                {"operation": "Op-A", "equipment": "Eq-A"},
                {"operation": "Op-B", "equipment": "Eq-B"},
            ],
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    first = r.json()["entries"]
    id_a, id_b = first[0]["id"], first[1]["id"]

    r = client.put(
        "/api/v1/admin/operation-catalog",
        json={
            "team_id": tid,
            "entries": [
                {"id": id_b, "operation": "Op-B-renamed", "equipment": "Eq-B-new"},
                {"id": id_a, "operation": "Op-A-renamed", "equipment": "Eq-A-new"},
            ],
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    updated = r.json()["entries"]
    assert updated[0]["id"] == id_b
    assert updated[1]["id"] == id_a
    assert updated[0]["operation"] == "Op-B-renamed"
    assert updated[1]["operation"] == "Op-A-renamed"
    assert [e["sort_order"] for e in updated] == [0, 1]
