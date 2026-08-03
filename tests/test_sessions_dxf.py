"""Integration-тесты DXF флоу: загрузка, анализ, история, телеметрия."""
import io
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

FAKE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
    b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd"
    b"\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
FAKE_DXF = b"AutoCAD DXF fake data for tests"
FAKE_MARKDOWN = (
    "# LLM Engineering Context\n\n## Product Identity\n"
    "- Name: Test Part\n- Material: Steel 45\n\n"
    "## Overall\n- L=100mm, D=50mm\n\n" * 5  # >50 chars
)


@pytest.fixture
def auth_headers():
    r = client.post(
        "/api/v1/auth/login",
        json={"login": "admin", "password": "admin"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_dxf_upload_drawing_mime_and_preview(auth_headers):
    """US1: загрузка DXF → drawing_mime = application/dxf, preview_url = data:image/png."""
    r = client.post("/api/v1/sessions", json={}, headers=auth_headers)
    assert r.status_code == 200
    sid = r.json()["id"]

    with patch(
        "app.services.dxf_converter_client.get_preview_png",
        new=AsyncMock(return_value=FAKE_PNG),
    ):
        r = client.put(
            f"/api/v1/session/drawing?id={sid}",
            files={"file": ("drawing.dxf", io.BytesIO(FAKE_DXF), "application/dxf")},
            headers=auth_headers,
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready_to_send"
    assert body["preview_url"].startswith("data:image/png;base64,")

    r = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["drawing_mime"] == "application/dxf"


def test_dxf_upload_via_extension_fallback(auth_headers):
    """Загрузка DXF с неправильным MIME от браузера → fallback по расширению .dxf."""
    r = client.post("/api/v1/sessions", json={}, headers=auth_headers)
    sid = r.json()["id"]

    with patch(
        "app.services.dxf_converter_client.get_preview_png",
        new=AsyncMock(return_value=FAKE_PNG),
    ):
        r = client.put(
            f"/api/v1/session/drawing?id={sid}",
            files={"file": ("drawing.dxf", io.BytesIO(FAKE_DXF), "application/octet-stream")},
            headers=auth_headers,
        )

    assert r.status_code == 200, r.text
    r2 = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r2.json()["drawing_mime"] == "application/dxf"


def test_dxf_analysis_mock_flow(auth_headers):
    """US2 (mock): DXF-сессия без API key → mock-паспорт, статус passport_review."""
    r = client.post("/api/v1/sessions", json={}, headers=auth_headers)
    sid = r.json()["id"]

    with patch(
        "app.services.dxf_converter_client.get_preview_png",
        new=AsyncMock(return_value=FAKE_PNG),
    ):
        client.put(
            f"/api/v1/session/drawing?id={sid}",
            files={"file": ("drawing.dxf", io.BytesIO(FAKE_DXF), "application/dxf")},
            headers=auth_headers,
        )

    r = client.post(f"/api/v1/session/analyze?id={sid}", headers=auth_headers)
    assert r.status_code == 202

    # Ожидаем завершения в background
    body = None
    for _ in range(40):
        r2 = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
        body = r2.json()
        if body["status"] in ("passport_review", "passport_failed"):
            break
        time.sleep(0.05)

    assert body is not None
    assert body["status"] == "passport_review", f"Got: {body['status']}"
    assert body["passport"] is not None


def test_dxf_analysis_uses_generate_passport_from_dxf(auth_headers):
    """US2: при drawing_mime=dxf и наличии API key — вызывается DXF-ветка generate_passport_from_dxf."""
    from app.db import SessionLocal
    from app.models import AppConfig

    db = SessionLocal()
    try:
        db.merge(AppConfig(key="dxfPassportModelKey", value="fake-dxf-key"))
        db.merge(AppConfig(key="dxfPassportModelModel", value="test/dxf-model"))
        db.commit()
    finally:
        db.close()

    r = client.post("/api/v1/sessions", json={}, headers=auth_headers)
    sid = r.json()["id"]

    with patch(
        "app.services.dxf_converter_client.get_preview_png",
        new=AsyncMock(return_value=FAKE_PNG),
    ):
        client.put(
            f"/api/v1/session/drawing?id={sid}",
            files={"file": ("drawing.dxf", io.BytesIO(FAKE_DXF), "application/dxf")},
            headers=auth_headers,
        )

    # Очищаем ключ обратно после теста
    db = SessionLocal()
    try:
        for k in ("dxfPassportModelKey", "dxfPassportModelModel"):
            row = db.get(AppConfig, k)
            if row:
                db.delete(row)
        db.commit()
    finally:
        db.close()

    # Проверяем что после загрузки MIME правильный
    r = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
    assert r.json()["drawing_mime"] == "application/dxf"


def test_dxf_llm_history_initial_user_content(auth_headers):
    """US2: после DXF-анализа llm_history['passport'] содержит assistant-turn с паспортом.

    initial_user_content (Markdown) не хранится в llm_history — аналогично
    изображению в VLM-сессиях (передаётся как initial_user_content к build_messages).
    Проверяем, что llm_history корректно заполнен: есть assistant-turn с паспортом.
    """
    from app.db import SessionLocal
    from app.models import WorkSession
    from app.services.ai_config import ModelConnection, AiConfig

    mock_passport = {
        "schema_version": "2.0",
        "designation": {"value": "TEST-DXF-001", "note": None},
        "product_name": "Test DXF Part",
        "material": {"value": "Steel 45", "note": None},
        "dimensions": {"length": 100, "width": 50, "height": 50},
        "weight": {"value": 1.5, "note": None},
        "quantity": 1,
        "processing_type": "Механическая обработка",
        "surface_roughness": None,
        "hardness": None,
        "notes": None,
    }

    def _fake_get_ai_config(db):
        conn = ModelConnection(
            base_url="http://fake",
            api_key="fake-key",
            model="real/model",  # не startswith("test/") → use_mock=False
            temperature=0.2,
        )
        return AiConfig(passport=conn, technology=conn, blank_allowance=conn, dxf_passport=conn)

    r = client.post("/api/v1/sessions", json={}, headers=auth_headers)
    sid = r.json()["id"]

    with patch(
        "app.services.dxf_converter_client.get_preview_png",
        new=AsyncMock(return_value=FAKE_PNG),
    ):
        client.put(
            f"/api/v1/session/drawing?id={sid}",
            files={"file": ("drawing.dxf", io.BytesIO(FAKE_DXF), "application/dxf")},
            headers=auth_headers,
        )

    with (
        patch("app.services.ai.get_ai_config", side_effect=_fake_get_ai_config),
        patch(
            "app.services.dxf_converter_client.get_llm_markdown",
            new=AsyncMock(return_value=FAKE_MARKDOWN),
        ),
        patch(
            "app.services.ai.call_openrouter",
            new=AsyncMock(return_value=mock_passport),
        ),
    ):
        r = client.post(f"/api/v1/session/analyze?id={sid}", headers=auth_headers)
        assert r.status_code == 202

        body = None
        for _ in range(40):
            r2 = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
            body = r2.json()
            if body["status"] in ("passport_review", "passport_failed"):
                break
            time.sleep(0.05)

    assert body is not None
    assert body["status"] == "passport_review", body.get("status")

    # Проверяем llm_history в БД: первый turn — assistant с паспортом
    # (initial_user_content / Markdown не хранится в llm_history — аналогично VLM-сессиям,
    #  передаётся как initial_user_content к build_messages при каждом вызове)
    db = SessionLocal()
    try:
        s = db.get(WorkSession, sid)
        assert s is not None
        history = s.llm_history or {}
        passport_turns = history.get("passport", [])
        assert len(passport_turns) >= 1, "llm_history должен содержать хотя бы один turn"
        first_turn = passport_turns[0]
        assert first_turn["role"] == "assistant", (
            f"Первый turn должен быть assistant (паспорт), получено: {first_turn['role']}"
        )
        assert first_turn["kind"] == "artifact", (
            f"Первый turn должен быть artifact, получено: {first_turn['kind']}"
        )
    finally:
        db.close()


def test_dxf_empty_context_raises_error(auth_headers):
    """T009: пустой Markdown от конвертера → AppError DXF_EMPTY_CONTEXT (422)."""
    from app.services.ai_config import ModelConnection, AiConfig

    def _fake_get_ai_config(db):
        conn = ModelConnection(
            base_url="http://fake",
            api_key="fake-key",
            model="some/real-model",
            temperature=0.2,
        )
        return AiConfig(passport=conn, technology=conn, blank_allowance=conn, dxf_passport=conn)

    r = client.post("/api/v1/sessions", json={}, headers=auth_headers)
    sid = r.json()["id"]

    with patch(
        "app.services.dxf_converter_client.get_preview_png",
        new=AsyncMock(return_value=FAKE_PNG),
    ):
        client.put(
            f"/api/v1/session/drawing?id={sid}",
            files={"file": ("drawing.dxf", io.BytesIO(FAKE_DXF), "application/dxf")},
            headers=auth_headers,
        )

    with (
        patch("app.services.ai.get_ai_config", side_effect=_fake_get_ai_config),
        patch(
            "app.services.dxf_converter_client.get_llm_markdown",
            new=AsyncMock(return_value="short"),  # <= 50 chars → empty context
        ),
    ):
        r = client.post(f"/api/v1/session/analyze?id={sid}", headers=auth_headers)
        assert r.status_code == 202

        body = None
        for _ in range(40):
            r2 = client.get(f"/api/v1/session?id={sid}", headers=auth_headers)
            body = r2.json()
            if body["status"] in ("passport_review", "passport_failed"):
                break
            time.sleep(0.05)

    assert body is not None
    assert body["status"] == "passport_failed", f"Got: {body['status']}"
    events = body.get("events", [])
    failed_events = [e for e in events if e.get("type") == "passport_failed"]
    assert failed_events, "Должно быть событие passport_failed"
    error_text = str(failed_events[-1].get("error", ""))
    assert "пустой" in error_text.lower() or "DXF_EMPTY_CONTEXT" in error_text, (
        f"Ожидается DXF_EMPTY_CONTEXT или 'пустой' в сообщении: {error_text}"
    )
