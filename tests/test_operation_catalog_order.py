"""Порядок catalog_ids при генерации технологии."""
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


def test_generate_preserves_catalog_ids_order(auth_headers):
    sid = _session_at_operations_selection(auth_headers)
    catalog = client.get("/api/v1/operation-catalog", headers=auth_headers).json()["entries"]
    assert len(catalog) >= 2
    id_a, id_b = catalog[0]["id"], catalog[1]["id"]
    # Намеренно обратный порядок относительно справочника
    r = client.post(
        f"/api/v1/session/technology/generate?id={sid}",
        json={"catalog_ids": [id_b, id_a]},
        headers=auth_headers,
    )
    assert r.status_code == 202, r.text
    body = client.get(f"/api/v1/session?id={sid}", headers=auth_headers).json()
    ops = body["selected_operations"]
    assert [o["catalog_id"] for o in ops] == [id_b, id_a]
    assert [o["operation"] for o in ops] == [catalog[1]["operation"], catalog[0]["operation"]]
