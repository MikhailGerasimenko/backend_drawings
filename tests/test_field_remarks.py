"""API-тесты замечаний к полям и пакетной отправки — specs/006 (US2/US3/US4)."""
import io
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import StatisticsAgg, WorkSession

client = TestClient(app)

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def auth_headers():
    r = client.post("/api/v1/auth/login", json={"login": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def _new_session(headers) -> str:
    return client.post("/api/v1/sessions", json={}, headers=headers).json()["id"]


def _session_at_passport_review(headers) -> str:
    sid = _new_session(headers)
    client.put(
        f"/api/v1/session/drawing?id={sid}",
        files={"file": ("t.png", io.BytesIO(_PNG), "image/png")},
        headers=headers,
    )
    client.post(f"/api/v1/session/analyze?id={sid}", headers=headers)
    for _ in range(40):
        body = client.get(f"/api/v1/session?id={sid}", headers=headers).json()
        if body["status"] == "passport_review":
            return sid
        if body["status"] in ("passport_failed", "failed"):
            break
        time.sleep(0.05)
    raise AssertionError("session did not reach passport_review")


def _wait_status(headers, sid, target, tries=40):
    for _ in range(tries):
        body = client.get(f"/api/v1/session?id={sid}", headers=headers).json()
        if body["status"] == target:
            return body
        time.sleep(0.05)
    raise AssertionError(f"status != {target}")


# ---------------- T018: черновики точечных замечаний ----------------

def test_put_field_remarks_upsert_and_restore(auth_headers):
    sid = _session_at_passport_review(auth_headers)
    r = client.put(
        f"/api/v1/session/field-remarks?id={sid}",
        json={"applied": [{"field": "part_type", "label": "Тип детали", "text": "Уточнить тип"}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["has_field_remarks"] is True
    # черновик восстанавливается при повторном GET
    body = client.get(f"/api/v1/session?id={sid}", headers=auth_headers).json()
    applied = body["field_remarks"]["passport"]["applied"]
    assert len(applied) == 1
    assert applied[0]["field"] == "part_type"
    assert applied[0]["text"] == "Уточнить тип"


def test_put_field_remarks_unknown_field_400(auth_headers):
    sid = _session_at_passport_review(auth_headers)
    r = client.put(
        f"/api/v1/session/field-remarks?id={sid}",
        json={"applied": [{"field": "nonexistent", "label": "X", "text": "t"}]},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_put_field_remarks_text_limit_400(auth_headers):
    sid = _session_at_passport_review(auth_headers)
    r = client.put(
        f"/api/v1/session/field-remarks?id={sid}",
        json={"applied": [{"field": "part_type", "label": "Тип", "text": "a" * 2001}]},
        headers=auth_headers,
    )
    assert r.status_code in (400, 422)


def test_put_field_remarks_outside_review_409(auth_headers):
    # свежая сессия без анализа — не на review-этапе
    sid = _new_session(auth_headers)
    r = client.put(
        f"/api/v1/session/field-remarks?id={sid}",
        json={"applied": [{"field": "part_type", "label": "Тип", "text": "t"}]},
        headers=auth_headers,
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INVALID_STATE"


def test_put_field_remarks_forbidden_for_other_user(auth_headers):
    sid = _session_at_passport_review(auth_headers)
    teams = client.get("/api/v1/admin/teams", headers=auth_headers).json()["teams"]
    login = "fr_user_" + uuid.uuid4().hex[:8]
    client.post(
        "/api/v1/admin/users",
        json={
            "login": login,
            "display_name": "FR Tester",
            "password": "testpass123",
            "team_id": teams[0]["id"],
            "role": "user",
        },
        headers=auth_headers,
    )
    tok = client.post(
        "/api/v1/auth/login", json={"login": login, "password": "testpass123"}
    ).json()["token"]
    other = {"Authorization": "Bearer " + tok}
    r = client.put(
        f"/api/v1/session/field-remarks?id={sid}",
        json={"applied": [{"field": "part_type", "label": "Тип", "text": "t"}]},
        headers=other,
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


# ---------------- T011a (C1): diff остаётся видимым при добавлении замечаний ----------------

def _inject_passport_versions(sid: str):
    """Две разные artifact-версии паспорта в истории → ненулевой diff."""
    db = SessionLocal()
    try:
        s = db.get(WorkSession, uuid.UUID(sid))
        v1 = {
            "schema_version": "2.0",
            "part_type": {"value": "Тело вращения", "missing_on_drawing": False},
            "designation": {"value": "ОБ-1", "missing_on_drawing": False},
        }
        v2 = {
            "schema_version": "2.0",
            "part_type": {"value": "Толкатель", "missing_on_drawing": False},
            "designation": {"value": "ОБ-1", "missing_on_drawing": False},
        }
        s.passport = v2
        s.llm_history = {
            "passport": [
                {"kind": "artifact", "role": "assistant", "content": v1},
                {"kind": "artifact", "role": "assistant", "content": v2},
            ]
        }
        db.commit()
    finally:
        db.close()


def test_diff_visible_and_unchanged_after_adding_remark(auth_headers):
    sid = _session_at_passport_review(auth_headers)
    _inject_passport_versions(sid)

    before = client.get(f"/api/v1/session?id={sid}", headers=auth_headers).json()
    diffs_before = before["field_diffs"].get("passport") or []
    assert any(d["field"] == "part_type" for d in diffs_before)

    # добавляем замечание к другому полю — diff должен остаться (FR-018)
    client.put(
        f"/api/v1/session/field-remarks?id={sid}",
        json={"applied": [{"field": "designation", "label": "Обозначение", "text": "Проверить"}]},
        headers=auth_headers,
    )
    after = client.get(f"/api/v1/session?id={sid}", headers=auth_headers).json()
    assert after["field_diffs"].get("passport") == diffs_before


# ---------------- T025 (F1): отправка пакета и жизненный цикл черновиков ----------------

def _stage_remarks_db(sid: str) -> dict:
    db = SessionLocal()
    try:
        s = db.get(WorkSession, uuid.UUID(sid))
        return dict(s.field_remarks or {})
    finally:
        db.close()


def _stats_counter(sid: str) -> int:
    db = SessionLocal()
    try:
        s = db.get(WorkSession, uuid.UUID(sid))
        st = db.get(StatisticsAgg, s.team_id)
        return st.remarks_passport_total if st else 0
    finally:
        db.close()


def test_submit_records_event_counter_and_keeps_draft(auth_headers, monkeypatch):
    """F1: submit не очищает черновик; одно событие + payload + счётчик +1.

    enqueue_session_ai мокаем, иначе TestClient синхронно выполнит перегенерацию
    и черновик будет очищен ещё до проверки.
    """
    sid = _session_at_passport_review(auth_headers)
    # патчим после выхода на review, иначе не сгенерируется паспорт
    monkeypatch.setattr(
        "app.api.v1.sessions.enqueue_session_ai", lambda *a, **k: None
    )
    fr = [
        {"field": "part_type", "label": "Тип детали", "text": "Не тело вращения"},
        {"field": "designation", "label": "Обозначение", "text": "Сверить"},
    ]
    client.put(
        f"/api/v1/session/field-remarks?id={sid}",
        json={"applied": fr, "general_draft": "Общая правка"},
        headers=auth_headers,
    )
    cnt_before = _stats_counter(sid)

    r = client.post(
        f"/api/v1/session/remarks/submit?id={sid}",
        json={"field_remarks": fr, "general_text": "Общая правка"},
        headers=auth_headers,
    )
    assert r.status_code == 202, r.text
    data = r.json()
    assert data["status"] == "analyzing"

    events = [e for e in data["events"] if e["type"] == "remark_passport"]
    ev = events[-1]
    assert ev.get("general_text") == "Общая правка"
    assert len(ev.get("field_remarks") or []) == 2
    assert "Тип детали" in (ev.get("text") or "")

    # +1 к счётчику замечаний паспорта
    assert _stats_counter(sid) == cnt_before + 1
    # F1: черновик НЕ очищен submit-эндпоинтом
    assert "passport" in _stage_remarks_db(sid)


def test_draft_cleared_after_successful_generation(auth_headers):
    """F1: реальная (mock) перегенерация успешна → черновик очищается."""
    sid = _session_at_passport_review(auth_headers)
    client.put(
        f"/api/v1/session/field-remarks?id={sid}",
        json={"applied": [{"field": "part_type", "label": "Тип", "text": "Уточнить"}]},
        headers=auth_headers,
    )
    client.post(
        f"/api/v1/session/remarks/submit?id={sid}",
        json={"field_remarks": [{"field": "part_type", "label": "Тип", "text": "Уточнить"}]},
        headers=auth_headers,
    )
    _wait_status(auth_headers, sid, "passport_review")
    assert "passport" not in _stage_remarks_db(sid)


def test_submit_empty_package_400(auth_headers):
    sid = _session_at_passport_review(auth_headers)
    r = client.post(
        f"/api/v1/session/remarks/submit?id={sid}",
        json={"field_remarks": [], "general_text": ""},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_submit_general_only_ok(auth_headers):
    sid = _session_at_passport_review(auth_headers)
    r = client.post(
        f"/api/v1/session/remarks/submit?id={sid}",
        json={"field_remarks": [], "general_text": "Только общие замечания"},
        headers=auth_headers,
    )
    assert r.status_code == 202, r.text


def test_draft_retained_on_generation_error(auth_headers, monkeypatch):
    """F1/FR-012: при провале генерации черновик сохраняется (очистка только по успеху)."""
    sid = _session_at_passport_review(auth_headers)
    monkeypatch.setattr(
        "app.api.v1.sessions.enqueue_session_ai", lambda *a, **k: None
    )
    client.put(
        f"/api/v1/session/field-remarks?id={sid}",
        json={"applied": [{"field": "part_type", "label": "Тип", "text": "t"}]},
        headers=auth_headers,
    )
    client.post(
        f"/api/v1/session/remarks/submit?id={sid}",
        json={"field_remarks": [{"field": "part_type", "label": "Тип", "text": "t"}]},
        headers=auth_headers,
    )
    # эмулируем провал генерации: очистка происходит только в ai.py по успеху
    db = SessionLocal()
    try:
        s = db.get(WorkSession, uuid.UUID(sid))
        s.status = "passport_failed"
        db.commit()
    finally:
        db.close()
    assert "passport" in _stage_remarks_db(sid)


# ---------------- T027a (C2): блокировка во время перегенерации ----------------

def _force_status(sid: str, status: str):
    db = SessionLocal()
    try:
        s = db.get(WorkSession, uuid.UUID(sid))
        s.status = status
        db.commit()
    finally:
        db.close()


def test_submit_and_put_blocked_during_regeneration(auth_headers):
    sid = _session_at_passport_review(auth_headers)
    _force_status(sid, "analyzing")

    r1 = client.post(
        f"/api/v1/session/remarks/submit?id={sid}",
        json={"field_remarks": [{"field": "part_type", "label": "Тип", "text": "t"}]},
        headers=auth_headers,
    )
    assert r1.status_code == 409
    assert r1.json()["error"]["code"] == "INVALID_STATE"

    r2 = client.put(
        f"/api/v1/session/field-remarks?id={sid}",
        json={"applied": [{"field": "part_type", "label": "Тип", "text": "t"}]},
        headers=auth_headers,
    )
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "INVALID_STATE"


# ---------------- T029 (US4): согласование без замечаний ----------------

def test_approve_passport_without_field_remarks(auth_headers):
    sid = _session_at_passport_review(auth_headers)
    body = client.get(f"/api/v1/session?id={sid}", headers=auth_headers).json()
    assert body["has_field_remarks"] is False
    r = client.post(f"/api/v1/session/passport/approve?id={sid}", headers=auth_headers)
    assert r.status_code in (200, 202), r.text
    assert r.json()["status"] != "passport_review"
