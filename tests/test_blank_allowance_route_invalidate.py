"""FR-049: смена маршрута после согласования расчёта сбрасывает blank_allowance."""
import io
import time

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


def test_route_change_invalidates_approved_blank(auth_headers):
    tid = client.get("/api/v1/admin/teams", headers=auth_headers).json()["teams"][0]["id"]
    client.post(
        "/api/v1/admin/prompts/blank-allowance-step",
        json={"team_id": tid, "enabled": True},
        headers=auth_headers,
    )

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
    r = client.post(f"/api/v1/session/analyze?id={sid}", headers=auth_headers)
    assert r.status_code == 202, r.text
    body = None
    for _ in range(80):
        r = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
        body = r.json()
        if body["status"] == "passport_review":
            break
        if body["status"] in ("passport_failed", "failed"):
            break
        time.sleep(0.05)
    assert body and body["status"] == "passport_review", body.get("status")
    r = client.post(f"/api/v1/session/passport/approve?id={sid}", headers=auth_headers)
    assert r.status_code in (200, 202), r.text
    assert r.json()["status"] == "operations_selection"

    catalog = client.get("/api/v1/operation-catalog", headers=auth_headers).json()[
        "entries"
    ]
    ids_a = [catalog[0]["id"]]
    generate_technology_with_catalog(client, auth_headers, sid)
    for _ in range(50):
        body = client.get(f"/api/v1/session?id={sid}", headers=auth_headers).json()
        if body["status"] == "blank_allowance_review":
            break
        time.sleep(0.05)

    client.post(
        f"/api/v1/session/blank-allowance/approve?id={sid}",
        json={},
        headers=auth_headers,
    )
    for _ in range(50):
        body = client.get(f"/api/v1/session?id={sid}", headers=auth_headers).json()
        if body["status"] == "technology_review":
            break
        time.sleep(0.05)

    client.post(
        f"/api/v1/session/technology/reselect-operations?id={sid}",
        headers=auth_headers,
    )
    assert (
        client.get(f"/api/v1/session?id={sid}", headers=auth_headers).json()["status"]
        == "operations_selection"
    )

    ids_b = [catalog[1]["id"]] if len(catalog) > 1 else ids_a
    r = client.post(
        f"/api/v1/session/technology/generate?id={sid}",
        json={"catalog_ids": ids_b},
        headers=auth_headers,
    )
    assert r.status_code == 202
    body = r.json()
    assert body["blank_allowance_approved"] is False
    assert body.get("blank_allowance") is None

    client.post(
        "/api/v1/admin/prompts/blank-allowance-step",
        json={"team_id": tid, "enabled": False},
        headers=auth_headers,
    )
