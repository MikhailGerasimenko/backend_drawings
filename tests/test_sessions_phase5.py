"""Phase 5: технология — approve, remarks, PDF, statistics."""
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
    assert r.status_code == 200
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _session_at_technology_review(headers):
    sid = _session_with_drawing(headers)
    session_at_technology_review(client, headers, sid)
    return sid


def _session_with_drawing(headers):
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
    return sid


def test_technology_reselect_operations(auth_headers):
    sid = _session_at_technology_review(auth_headers)
    r = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r.json()["selected_operations"]

    r = client.post(
        f"/api/v1/session/technology/reselect-operations?id={sid}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "operations_selection"
    assert body["technology_text"]
    assert body["selected_operations"]


def test_technology_approve_and_exports(auth_headers):
    sid = _session_at_technology_review(auth_headers)
    body = client.get(f"/api/v1/session?id={sid}", headers=auth_headers).json()
    tj = body["technology_json"]
    assert tj["schema_version"] == "2.0"
    assert tj["header"]["part_designation"]
    assert len(tj["route"]) >= 1

    r = client.post(
        f"/api/v1/session/technology/approve?id={sid}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "completed"

    r = client.get(
        f"/api/v1/session/exports/technology_json?id={sid}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    exported = r.json()
    assert exported["schema_version"] == "2.0"
    assert exported["route"][0].get("transitions") is not None

    r = client.get(
        f"/api/v1/session/exports/technology_pdf?id={sid}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["download_url"].startswith("data:application/pdf;base64,")


def test_technology_remarks_regenerates(auth_headers):
    sid = _session_at_technology_review(auth_headers)
    r = client.post(
        f"/api/v1/session/technology/remarks?id={sid}",
        headers=auth_headers,
        json={"text": "Добавить термообработку"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] in ("generating_technology", "technology_review")
    r2 = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r2.json()["status"] == "technology_review"
    assert r2.json()["technology_text"]


def test_statistics(auth_headers):
    r = client.get("/api/v1/statistics", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "sessions_total" in data
    assert "remarks_technology_total" in data


# --- 002-llm-conversation-memory ---


def _technology_history(sid):
    from uuid import UUID

    from app.db import SessionLocal
    from app.models import WorkSession

    db = SessionLocal()
    try:
        s = db.get(WorkSession, UUID(sid))
        return list((s.llm_history or {}).get("technology") or [])
    finally:
        db.close()


def _send_technology_remark(headers, sid, text):
    r = client.post(
        f"/api/v1/session/technology/remarks?id={sid}",
        headers=headers,
        json={"text": text},
    )
    assert r.status_code == 202, r.text
    r = client.get(f"/api/v1/session?id={sid}", headers=headers)
    assert r.json()["status"] == "technology_review", r.json()["status"]


def test_technology_memory_two_remarks_sc002(auth_headers):
    """T019/SC-002: два замечания → история v1→r1→v2→r2→v3; prompt полный."""
    sid = _session_at_technology_review(auth_headers)

    _send_technology_remark(auth_headers, sid, "Добавить термообработку")
    _send_technology_remark(auth_headers, sid, "Уточнить переход шлифовки")

    turns = _technology_history(sid)
    kinds = [t["kind"] for t in turns]
    assert kinds == ["artifact", "remark", "artifact", "remark", "artifact"]
    assert turns[1]["content"] == "Добавить термообработку"
    assert turns[3]["content"] == "Уточнить переход шлифовки"
    # Версии — пары text+json
    assert turns[0]["content"].get("text") and turns[0]["content"].get("json")

    # Собранный prompt: вход + все версии + оба замечания (SC-002)
    from uuid import UUID

    from app.db import SessionLocal
    from app.models import WorkSession
    from app.services.llm_history import build_messages

    db = SessionLocal()
    try:
        s = db.get(WorkSession, UUID(sid))
        messages = build_messages(
            "technology",
            s,
            system_prompt="SYS",
            initial_user_content="ВХОД: маршрут + паспорт",
        )
    finally:
        db.close()
    roles = [m["role"] for m in messages]
    assert roles == ["system", "user", "assistant", "user", "assistant", "user", "assistant"]
    text = " ".join(m["content"] for m in messages if isinstance(m["content"], str))
    assert "Добавить термообработку" in text
    assert "Уточнить переход шлифовки" in text


def test_route_change_resets_technology_history_fr011(auth_headers):
    """T018: смена маршрута после согласования — история этапа начинается заново."""
    sid = _session_at_technology_review(auth_headers)
    _send_technology_remark(auth_headers, sid, "Первое замечание")
    assert len(_technology_history(sid)) >= 3

    r = client.post(
        f"/api/v1/session/technology/reselect-operations?id={sid}",
        headers=auth_headers,
    )
    assert r.status_code == 200

    # Новый маршрут: другой состав операций (одна вместо двух)
    entries = client.get("/api/v1/operation-catalog", headers=auth_headers).json()["entries"]
    r = client.post(
        f"/api/v1/session/technology/generate?id={sid}",
        json={"catalog_ids": [entries[-1]["id"]]},
        headers=auth_headers,
    )
    assert r.status_code == 202, r.text
    r = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r.json()["status"] == "technology_review"

    turns = _technology_history(sid)
    # Старая переписка сброшена; в истории только свежая версия нового маршрута
    assert [t["kind"] for t in turns] == ["artifact"]
