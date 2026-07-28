"""Phase 4: mock-паспорт после analyze, approve, PDF."""
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
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


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
    return sid


def test_passport_mock_flow(auth_headers):
    sid = _session_with_drawing(auth_headers)
    r = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "passport_review"
    assert body["passport"]["schema_version"] == "2.0"
    assert body["passport"]["designation"]["value"]

    r = client.post(
        f"/api/v1/session/passport/approve?id={sid}",
        headers=auth_headers,
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "operations_selection"
    assert body["title"] == "Деталь-001 - Тело вращения (втулка)"

    generate_technology_with_catalog(client, auth_headers, sid)
    r = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "technology_review"
    assert body["technology_text"]
    assert body["selected_operations"]

    r = client.get(
        f"/api/v1/session/exports/passport_pdf?id={sid}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["download_url"].startswith("data:application/pdf;base64,")


def test_passport_remark_rejects_blank_text(auth_headers):
    """FR-008: пустое замечание к паспорту отклоняется."""
    sid = _session_with_drawing(auth_headers)
    client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    r = client.post(
        f"/api/v1/session/passport/remarks?id={sid}",
        json={"text": "   "},
        headers=auth_headers,
    )
    assert r.status_code == 422


# --- 002-llm-conversation-memory ---


def _passport_history(sid):
    from uuid import UUID

    from app.db import SessionLocal
    from app.models import WorkSession

    db = SessionLocal()
    try:
        s = db.get(WorkSession, UUID(sid))
        return list((s.llm_history or {}).get("passport") or [])
    finally:
        db.close()


def _send_passport_remark(headers, sid, text):
    r = client.post(
        f"/api/v1/session/passport/remarks?id={sid}",
        json={"text": text},
        headers=headers,
    )
    assert r.status_code == 202, r.text
    r = client.get(f"/api/v1/session?id={sid}", headers=headers)
    assert r.json()["status"] == "passport_review", r.json()["status"]


def test_passport_memory_two_remarks_sc001(auth_headers):
    """T013/SC-001: два замечания → история v1→r1→v2→r2→v3; prompt содержит всё."""
    sid = _session_with_drawing(auth_headers)
    client.get(f"/api/v1/session?id={sid}", headers=auth_headers)

    _send_passport_remark(auth_headers, sid, "Уточни материал")
    _send_passport_remark(auth_headers, sid, "Исправь габариты")

    turns = _passport_history(sid)
    kinds = [t["kind"] for t in turns]
    assert kinds == ["artifact", "remark", "artifact", "remark", "artifact"]
    assert turns[1]["content"] == "Уточни материал"
    assert turns[3]["content"] == "Исправь габариты"

    # Собранный prompt содержит обе прошлые версии и оба замечания (SC-001)
    from uuid import UUID

    from app.db import SessionLocal
    from app.models import WorkSession
    from app.services.llm_history import build_messages

    db = SessionLocal()
    try:
        s = db.get(WorkSession, UUID(sid))
        messages = build_messages(
            "passport", s, system_prompt="SYS", initial_user_content="DRAWING"
        )
    finally:
        db.close()
    roles = [m["role"] for m in messages]
    assert roles == ["system", "user", "assistant", "user", "assistant", "user", "assistant"]
    text = " ".join(m["content"] for m in messages if isinstance(m["content"], str))
    assert "Уточни материал" in text and "Исправь габариты" in text


def test_passport_failed_generation_not_in_history_fr005(auth_headers, monkeypatch):
    """T014/FR-005: ошибка генерации не добавляет версию; retry добавляет одну."""
    sid = _session_with_drawing(auth_headers)
    client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert len(_passport_history(sid)) == 1  # v1

    import app.services.ai as ai_module

    def _boom(_raw):
        raise ValueError("forced failure")

    monkeypatch.setattr(ai_module, "normalize_passport", _boom)
    r = client.post(
        f"/api/v1/session/passport/remarks?id={sid}",
        json={"text": "Замечание при сбое"},
        headers=auth_headers,
    )
    assert r.status_code == 202
    r = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r.json()["status"] == "passport_failed"

    turns = _passport_history(sid)
    # v1 + remark; неуспешная генерация версию НЕ добавила
    assert [t["kind"] for t in turns] == ["artifact", "remark"]

    monkeypatch.undo()
    r = client.post(f"/api/v1/session/retry?id={sid}", headers=auth_headers)
    assert r.status_code == 202
    r = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r.json()["status"] == "passport_review"

    turns = _passport_history(sid)
    assert [t["kind"] for t in turns] == ["artifact", "remark", "artifact"]


def test_llm_history_not_in_api_response_t025(auth_headers):
    """T025: llm_history не отдаётся клиенту (приватность payload)."""
    sid = _session_with_drawing(auth_headers)
    r = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r.status_code == 200
    assert "llm_history" not in r.json()
    r = client.get("/api/v1/sessions", headers=auth_headers)
    assert "llm_history" not in str(r.json())


def test_telemetry_records_history_prompt_fr009_t024(auth_headers):
    """T024/FR-009: запись телеметрии с history-prompt — payload, токены, cost."""
    import httpx
    from uuid import UUID

    from app.db import SessionLocal
    from app.models import LlmRequestLog, WorkSession
    from app.services.llm_history import build_messages
    from app.services.llm_telemetry import TelemetryCtx, record_llm_call

    sid = _session_with_drawing(auth_headers)
    client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    _send_passport_remark(auth_headers, sid, "Уточни материал")

    db = SessionLocal()
    try:
        s = db.get(WorkSession, UUID(sid))
        messages = build_messages(
            "passport", s, system_prompt="SYS", initial_user_content="DRAWING"
        )
        ctx = TelemetryCtx(db, s.id, s.created_by, "passport")
        response_data = {
            "choices": [{"message": {"content": "{}"}}],
            # Стоимость берётся напрямую из ответа модели (usage.cost), без тарифов
            "usage": {"prompt_tokens": 1500, "completion_tokens": 300, "cost": 0.0042},
        }
        record_llm_call(
            ctx,
            "anthropic/claude-3.5-sonnet",
            messages,
            response_data,
            httpx.Response(200),
            latency_ms=10,
        )
        db.commit()

        row = (
            db.query(LlmRequestLog)
            .filter(LlmRequestLog.session_id == s.id)
            .order_by(LlmRequestLog.timestamp.desc())
            .first()
        )
        assert row is not None
        assert row.prompt_tokens == 1500 and row.completion_tokens == 300
        assert row.cost is not None and row.cost > 0
        assert "Уточни материал" in (row.payload_prompt or "")
        db.delete(row)
        db.commit()
    finally:
        db.close()
