"""US2c: опциональный шаг расчёта припусков."""
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


def _team_id(headers):
    return client.get("/api/v1/admin/teams", headers=headers).json()["teams"][0]["id"]


def _set_blank_step(headers, team_id: str, enabled: bool):
    r = client.post(
        "/api/v1/admin/prompts/blank-allowance-step",
        json={"team_id": team_id, "enabled": enabled},
        headers=headers,
    )
    assert r.status_code == 200, r.text


def _new_session_with_passport_approved(headers):
    r = client.post("/api/v1/sessions", json={}, headers=headers)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    r = client.put(
        f"/api/v1/session/drawing?id={sid}",
        files={"file": ("t.png", io.BytesIO(png), "image/png")},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/session/analyze?id={sid}", headers=headers)
    assert r.status_code == 202, r.text
    body = None
    for _ in range(80):
        r = client.get(f"/api/v1/session?id={sid}", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] == "passport_review":
            break
        if body["status"] in ("passport_failed", "failed"):
            break
        time.sleep(0.05)
    assert body and body["status"] == "passport_review", body.get("status") if body else None
    r = client.post(f"/api/v1/session/passport/approve?id={sid}", headers=headers)
    assert r.status_code in (200, 202), r.text
    assert r.json()["status"] == "operations_selection", r.text
    return sid


def _wait_status(headers, sid, target: str, extra_ok=()):
    body = None
    for _ in range(80):
        r = client.get(f"/api/v1/session?id={sid}", headers=headers)
        body = r.json()
        if body["status"] == target:
            return body
        if body["status"] in extra_ok:
            return body
        if body["status"].endswith("_failed"):
            break
        time.sleep(0.05)
    assert body and body["status"] == target, body.get("status") if body else None
    return body


def test_blank_allowance_step_on_remark_approve_auto_technology(auth_headers):
    tid = _team_id(auth_headers)
    _set_blank_step(auth_headers, tid, True)
    sid = _new_session_with_passport_approved(auth_headers)
    generate_technology_with_catalog(client, auth_headers, sid)
    body = _wait_status(auth_headers, sid, "blank_allowance_review")
    assert body.get("blank_allowance")
    assert body["blank_allowance_approved"] is False

    r = client.post(
        f"/api/v1/session/blank-allowance/remarks?id={sid}",
        json={"text": "Уточнить припуск на торец"},
        headers=auth_headers,
    )
    assert r.status_code == 202
    body = _wait_status(auth_headers, sid, "blank_allowance_review")
    assert body.get("blank_allowance")

    r = client.post(
        f"/api/v1/session/blank-allowance/approve?id={sid}",
        json={},
        headers=auth_headers,
    )
    assert r.status_code == 202
    assert r.json()["status"] == "generating_technology"
    assert r.json()["blank_allowance_approved"] is True

    body = _wait_status(
        auth_headers, sid, "technology_review", extra_ok=("generating_technology",)
    )
    assert body["status"] == "technology_review"
    _set_blank_step(auth_headers, tid, False)


def test_reselect_operations_from_blank_allowance_review(auth_headers):
    tid = _team_id(auth_headers)
    _set_blank_step(auth_headers, tid, True)
    sid = _new_session_with_passport_approved(auth_headers)
    generate_technology_with_catalog(client, auth_headers, sid)
    body = _wait_status(auth_headers, sid, "blank_allowance_review")
    assert body.get("blank_allowance")

    r = client.post(
        f"/api/v1/session/technology/reselect-operations?id={sid}",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "operations_selection"
    assert data.get("blank_allowance")
    assert data["blank_allowance_approved"] is False
    assert data.get("selected_operations")
    _set_blank_step(auth_headers, tid, False)


def test_blank_allowance_step_off_skips_to_technology(auth_headers):
    tid = _team_id(auth_headers)
    _set_blank_step(auth_headers, tid, False)
    sid = _new_session_with_passport_approved(auth_headers)
    generate_technology_with_catalog(client, auth_headers, sid)
    r = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r.json()["status"] in ("generating_technology", "technology_review")
    assert not r.json().get("blank_allowance")


# --- 002-llm-conversation-memory ---


def _blank_history(sid):
    from uuid import UUID

    from app.db import SessionLocal
    from app.models import WorkSession

    db = SessionLocal()
    try:
        s = db.get(WorkSession, UUID(sid))
        return list((s.llm_history or {}).get("blank_allowance") or [])
    finally:
        db.close()


def test_blank_allowance_memory_two_remarks_t023(auth_headers):
    """T023/FR-008: два замечания → история расчёта накапливает версии и замечания."""
    tid = _team_id(auth_headers)
    _set_blank_step(auth_headers, tid, True)
    try:
        sid = _new_session_with_passport_approved(auth_headers)
        generate_technology_with_catalog(client, auth_headers, sid)
        _wait_status(auth_headers, sid, "blank_allowance_review")

        for text in ("Уточнить припуск на торец", "Пересчитать длину заготовки"):
            r = client.post(
                f"/api/v1/session/blank-allowance/remarks?id={sid}",
                json={"text": text},
                headers=auth_headers,
            )
            assert r.status_code == 202, r.text
            _wait_status(auth_headers, sid, "blank_allowance_review")

        turns = _blank_history(sid)
        kinds = [t["kind"] for t in turns]
        assert kinds == ["artifact", "remark", "artifact", "remark", "artifact"]
        assert turns[1]["content"] == "Уточнить припуск на торец"
        assert turns[3]["content"] == "Пересчитать длину заготовки"
        assert turns[0]["content"].get("blank")  # версия — JSON Appendix B
    finally:
        _set_blank_step(auth_headers, tid, False)
