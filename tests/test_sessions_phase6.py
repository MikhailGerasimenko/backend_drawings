"""Phase 6–8: выгрузки, статистика, удаление (R-10), admin config."""
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
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


@pytest.fixture
def super_headers(auth_headers):
    return auth_headers


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
    client.get(f"/api/v1/session?id={sid}", headers=headers)
    session_at_technology_review(client, headers, sid)
    return sid


def _complete_technology(headers, sid: str) -> None:
    r = client.post(
        f"/api/v1/session/technology/approve?id={sid}",
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_technology_export_blocked_before_approve(super_headers):
    """FR-017: выгрузка технологии недоступна на этапе согласования."""
    sid = _session_at_technology_review(super_headers)
    r = client.get(
        f"/api/v1/session/exports/technology_json?id={sid}",
        headers=super_headers,
    )
    assert r.status_code == 409
    assert "согласован" in (r.json().get("error") or {}).get("message", "").lower()


def test_technology_json_export_v2_structure(super_headers):
    """T025: JSON технологии — поля v2, не один blob description."""
    sid = _session_at_technology_review(super_headers)
    _complete_technology(super_headers, sid)
    tj = client.get(
        f"/api/v1/session/exports/technology_json?id={sid}",
        headers=super_headers,
    ).json()
    assert tj["schema_version"] == "2.0"
    assert tj["header"]["part_designation"]
    assert len(tj["route"]) >= 1
    step = tj["route"][0]
    assert step.get("code") or step.get("name")
    assert "transitions" in step
    assert "description" not in tj or tj.get("format") != "text_v1"


def test_passport_and_technology_pdf_export(super_headers):
    sid = _session_at_technology_review(super_headers)
    _complete_technology(super_headers, sid)
    r = client.get(
        f"/api/v1/session/exports/passport_pdf?id={sid}",
        headers=super_headers,
    )
    assert r.status_code == 200
    assert r.json()["download_url"].startswith("data:application/pdf;base64,")

    r = client.get(
        f"/api/v1/session/exports/technology_pdf?id={sid}",
        headers=super_headers,
    )
    assert r.status_code == 200
    assert r.json()["download_url"].startswith("data:application/pdf;base64,")


def test_delete_session_retains_statistics(super_headers):
    """T030 R-10: мягкое удаление — агрегаты statistics_agg не уменьшаются, строка в БД остаётся."""
    stats_before = client.get("/api/v1/statistics", headers=super_headers).json()
    total_before = stats_before["sessions_total"]

    r = client.post("/api/v1/sessions", json={}, headers=super_headers)
    sid = r.json()["id"]
    stats_after_create = client.get("/api/v1/statistics", headers=super_headers).json()
    assert stats_after_create["sessions_total"] == total_before + 1

    r = client.delete(
        f"/api/v1/session?id={sid}&confirm=true",
        headers=super_headers,
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True

    stats_after_delete = client.get("/api/v1/statistics", headers=super_headers).json()
    assert stats_after_delete["sessions_total"] == stats_after_create["sessions_total"]
    assert client.get(f"/api/v1/session?id={sid}", headers=super_headers).status_code == 404


def test_admin_config_alias(super_headers):
    """T027: GET/POST /admin/config."""
    r = client.get("/api/v1/admin/config", headers=super_headers)
    assert r.status_code == 200
    assert "passport" in r.json() and "technology" in r.json()

    r = client.post(
        "/api/v1/admin/config",
        headers=super_headers,
        json={"aiVerifySsl": True},
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True
