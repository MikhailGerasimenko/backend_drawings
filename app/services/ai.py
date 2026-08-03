"""VLM-паспорт и LLM-технология через Openrouter (+ mock без ключа)."""
import json
import logging
import re
import time
from uuid import UUID
import base64

import httpx
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import SESSION_STATUS_DELETED, WorkSession, utcnow
from app.schemas.base import PartPassport
from app.schema_modules.passport import PASSPORT_JSON_APPENDIX
from app.schema_modules.operations_select_rules import OPERATIONS_CATALOG_SYSTEM_APPENDIX
from app.schema_modules.technology_operations_rules import (
    TECHNOLOGY_CATALOG_OPERATIONS_RULES,
    TECHNOLOGY_USER_OPERATIONS_RULES,
)
from app.schema_modules.technology import TECHNOLOGY_JSON_APPENDIX
from app.schema_modules.blank_allowance import BLANK_ALLOWANCE_JSON_APPENDIX
from app.services.blank_allowance_normalize import (
    mock_blank_allowance,
    normalize_blank_allowance,
    validate_blank_allowance_store,
)
from app.services.ai_config import AiConfig, ModelConnection, get_ai_config
from app.services.field_remarks import clear_stage_remarks
from app.services.llm_history import append_turn, build_messages
from app.services.llm_telemetry import (
    TelemetryCtx,
    record_llm_call,
    record_llm_call_failed,
)
from app.services.passport_normalize import mock_passport, normalize_passport
from app.services.technology_normalize import (
    mock_technology,
    normalize_technology,
    validate_technology_store,
)

# re-export для тестов и внешних импортов
__all__ = ["mock_passport", "normalize_passport", "process_session_ai"]
from app.services.drawing import resolve_preview_url
from app.services.operation_catalog import list_catalog
from app.services.session_ops import (
    format_catalog_system_block,
    session_operations_skipped,
    sync_selected_operations_from_route,
)
from app.services.prompts import get_active_prompt
from app.services import dxf_converter_client

logger = logging.getLogger(__name__)

# OpenRouter attribution; HTTP-заголовки — только ASCII (иначе UnicodeEncodeError на Windows).
OPENROUTER_X_TITLE = "Cifrovoy Tehnolog"


def _parse_json_content(text: str) -> dict:
    trimmed = text.strip()
    # Снять markdown-обёртку ```json ... ```
    if trimmed.startswith("```"):
        trimmed = re.sub(r"^```(?:json)?\s*", "", trimmed, flags=re.I)
        trimmed = re.sub(r"\s*```\s*$", "", trimmed).strip()

    last_error: json.JSONDecodeError | None = None

    try:
        parsed = json.loads(trimmed)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError as e:
        last_error = e

    start = trimmed.find("{")
    if start >= 0:
        try:
            parsed, _end = json.JSONDecoder().raw_decode(trimmed, start)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as e:
            last_error = e

    raise AppError(
        "AI_UNAVAILABLE",
        "Ответ AI не является корректным JSON",
        502,
    ) from last_error


async def call_openrouter(
    conn: ModelConnection,
    messages: list,
    json_mode: bool = True,
    *,
    verify_ssl: bool = True,
    telemetry: TelemetryCtx | None = None,
) -> dict:
    if not conn.api_key:
        raise AppError(
            "AI_UNAVAILABLE",
            "API key не задан — Панель администратора → Параметры подключения к модели",
            503,
        )
    body: dict = {
        "model": conn.model,
        "messages": messages,
        "temperature": conn.temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {conn.api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://cifrovoy-tehnolog",
        "X-Title": OPENROUTER_X_TITLE,
        "X-OpenRouter-Cache": "true",
    }
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=300.0, verify=verify_ssl) as client:
            res = await client.post(
                f"{conn.base_url}/chat/completions",
                headers=headers,
                json=body,
            )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if res.status_code >= 400:
            if telemetry:
                record_llm_call_failed(
                    telemetry, conn.model, messages, latency_ms=latency_ms
                )
                telemetry.db.commit()
            err = res.json().get("error", {}) if res.headers.get(
                "content-type", ""
            ).startswith("application/json") else {}
            msg = err.get("message") or res.text[:200] or f"HTTP {res.status_code}"
            raise AppError("AI_UNAVAILABLE", f"Openrouter: {msg}", 502)
        data = res.json()
        msg = (data.get("choices") or [{}])[0].get("message", {})
        text = msg.get("content")
        if not text:
            logger.warning(
                "Пустой content от %s. Поля message: %s. choices[0]: %s",
                conn.model,
                list(msg.keys()),
                json.dumps((data.get("choices") or [{}])[0], ensure_ascii=False)[:2000],
            )
            if telemetry:
                record_llm_call_failed(
                    telemetry, conn.model, messages, latency_ms=latency_ms
                )
                telemetry.db.commit()
            raise AppError("AI_UNAVAILABLE", "Пустой ответ Openrouter", 502)
        if telemetry:
            record_llm_call(telemetry, conn.model, messages, data, res, latency_ms)
            telemetry.db.commit()
        return _parse_json_content(text)
    except AppError:
        raise
    except Exception as exc:
        if telemetry:
            record_llm_call_failed(telemetry, conn.model, messages)
            telemetry.db.commit()
        raise AppError("AI_UNAVAILABLE", str(exc) or "Ошибка Openrouter", 502) from exc


async def generate_passport_from_drawing(
    db: Session,
    s: WorkSession,
    preview_url: str,
    config: AiConfig,
    *,
    user_id: UUID,
) -> dict:
    """FR-001: полная история этапа passport; чертёж — в каждой итерации (Q2)."""
    system_prompt = (
        get_active_prompt(db, s.team_id, "passport") + "\n\n" + PASSPORT_JSON_APPENDIX
    )
    initial_user_content: list[dict] = [
        {"type": "image_url", "image_url": {"url": preview_url}},
    ]
    messages = build_messages(
        "passport",
        s,
        system_prompt=system_prompt,
        initial_user_content=initial_user_content,
    )
    telemetry = TelemetryCtx(db, s.id, user_id, "passport")
    raw = await call_openrouter(
        config.passport,
        messages,
        json_mode=True,
        verify_ssl=config.verify_ssl,
        telemetry=telemetry,
    )
    return normalize_passport(raw)


async def generate_passport_from_dxf(
    db: Session,
    s: WorkSession,
    config: AiConfig,
    *,
    user_id: UUID,
) -> dict:
    """DXF-ветка: Markdown инженерного контекста → паспорт (без изображения).

    Шаги (R-05):
    1. Декодировать DXF из drawing_b64
    2. Получить llm_context от конвертера (POST /v1/convert render_png=false)
    3. Проверить непустоту контекста
    4. Сформировать initial_user_content как текстовый блок
    5. Вызвать build_messages + call_openrouter с config.dxf_passport
    """
    dxf_bytes = base64.b64decode(s.drawing_b64)
    md_text = await dxf_converter_client.get_llm_markdown(dxf_bytes)
    if not md_text or len(md_text) <= 50:
        from app.core.exceptions import AppError
        raise AppError(
            "DXF_EMPTY_CONTEXT",
            "Конвертер вернул пустой инженерный контекст",
            422,
        )

    system_prompt = (
        get_active_prompt(db, s.team_id, "passport_dxf") + "\n\n" + PASSPORT_JSON_APPENDIX
    )
    initial_user_content: list[dict] = [{"type": "text", "text": md_text}]
    messages = build_messages(
        "passport",
        s,
        system_prompt=system_prompt,
        initial_user_content=initial_user_content,
    )
    telemetry = TelemetryCtx(db, s.id, user_id, "passport", extra_meta={"drawing_source": "dxf"})
    raw = await call_openrouter(
        config.dxf_passport,
        messages,
        json_mode=True,
        verify_ssl=config.verify_ssl,
        telemetry=telemetry,
    )
    return normalize_passport(raw)


def _format_selected_operations(selected: list[dict]) -> str:
    lines = []
    for i, item in enumerate(selected, 1):
        op = item.get("operation") or ""
        eq = item.get("equipment") or ""
        lines.append(f"{i}. {op} ({eq})")
    return "\n".join(lines)


async def generate_blank_allowance(
    db: Session,
    s: WorkSession,
    passport: dict,
    selected_operations: list[dict],
    config: AiConfig,
    *,
    user_id: UUID,
    operations_skipped: bool = False,
) -> dict:
    """Расчёт заготовки и припусков (LLM, JSON Appendix B); FR-008 — с историей."""
    system_prompt = (
        get_active_prompt(db, s.team_id, "blank_allowance")
        + "\n\n"
        + BLANK_ALLOWANCE_JSON_APPENDIX
    )
    if operations_skipped:
        system_prompt += "\n\n" + OPERATIONS_CATALOG_SYSTEM_APPENDIX.format(
            catalog_json=format_catalog_system_block(db, s.team_id)
        )
        initial_user_content = "Паспорт детали:\n" + json.dumps(
            passport, ensure_ascii=False
        )
    else:
        ops_block = _format_selected_operations(selected_operations)
        initial_user_content = "\n\n".join(
            [
                "Выбранный маршрут (операция + оборудование):\n" + ops_block,
                "Паспорт детали:\n" + json.dumps(passport, ensure_ascii=False),
            ]
        )
    messages = build_messages(
        "blank_allowance",
        s,
        system_prompt=system_prompt,
        initial_user_content=initial_user_content,
    )
    telemetry = TelemetryCtx(db, s.id, user_id, "blank_allowance")
    raw = await call_openrouter(
        config.blank_allowance,
        messages,
        json_mode=True,
        verify_ssl=config.verify_ssl,
        telemetry=telemetry,
    )
    return validate_blank_allowance_store(normalize_blank_allowance(raw))


async def generate_technology(
    db: Session,
    s: WorkSession,
    passport: dict,
    selected_operations: list[dict],
    config: AiConfig,
    blank_allowance: dict | None = None,
    *,
    user_id: UUID,
    operations_skipped: bool = False,
) -> tuple[str, dict]:
    """FR-002: полная история этапа technology (вход + версии + замечания)."""
    catalog_block = ""
    route_rules = TECHNOLOGY_USER_OPERATIONS_RULES
    if operations_skipped:
        catalog_block = "\n\n" + OPERATIONS_CATALOG_SYSTEM_APPENDIX.format(
            catalog_json=format_catalog_system_block(db, s.team_id)
        )
        route_rules = TECHNOLOGY_CATALOG_OPERATIONS_RULES
    system_prompt = (
        get_active_prompt(db, s.team_id, "technology")
        + "\n\n"
        + TECHNOLOGY_JSON_APPENDIX
        + catalog_block
        + "\n\n"
        + route_rules
    )
    user_parts: list[str] = []
    if blank_allowance:
        user_parts.append(
            "Согласованный расчёт заготовки и припусков:\n"
            + json.dumps(blank_allowance, ensure_ascii=False, indent=2)
        )
    if operations_skipped:
        user_parts.append("Паспорт:\n" + json.dumps(passport, ensure_ascii=False))
    else:
        ops_block = _format_selected_operations(selected_operations)
        user_parts.extend(
            [
                "Выбранные операции (единственный допустимый перечень для поля route):\n"
                + ops_block,
                "Паспорт:\n" + json.dumps(passport, ensure_ascii=False),
            ]
        )
    messages = build_messages(
        "technology",
        s,
        system_prompt=system_prompt,
        initial_user_content="\n\n".join(user_parts),
    )
    telemetry = TelemetryCtx(db, s.id, user_id, "technology")
    raw = await call_openrouter(
        config.technology,
        messages,
        json_mode=True,
        verify_ssl=config.verify_ssl,
        telemetry=telemetry,
    )
    try:
        md, tj = normalize_technology(raw, passport)
    except ValueError as e:
        raise AppError("AI_UNAVAILABLE", str(e), 502) from e
    validate_technology_store(tj)
    return md, tj


def _ai_error_message(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.message
    return str(exc) or "Неизвестная ошибка AI"


def _push_event(
    db: Session,
    s: WorkSession,
    event_type: str,
    user_id: UUID,
    extra: dict | None = None,
) -> None:
    events = list(s.events or [])
    ev = {
        "type": event_type,
        "created_at": utcnow().isoformat(),
        "created_by": str(user_id),
    }
    if extra:
        ev.update(extra)
    events.append(ev)
    s.events = events[-50:]
    from app.services.user_audit import log_from_event

    log_from_event(
        db,
        user_id=user_id,
        team_id=s.team_id,
        session_id=s.id,
        event_type=event_type,
        meta=extra,
    )


async def process_session_ai(db: Session, s: WorkSession, user_id: UUID | None) -> None:
    """Переходы analyzing → passport_review; blank allowance; generating_technology → technology_review."""
    if s.status == SESSION_STATUS_DELETED:
        return
    config = get_ai_config(db)
    uid = user_id or s.created_by

    if s.status == "analyzing" and not s.passport:
        try:
            raw = None
            if s.drawing_mime == "application/dxf":
                # DXF-ветка: Markdown инженерного контекста → паспорт (без изображения)
                if not config.dxf_passport.use_mock:
                    raw = await generate_passport_from_dxf(db, s, config, user_id=uid)
            else:
                # Стандартная VLM-ветка: изображение чертежа → паспорт
                preview_url = resolve_preview_url(
                    s.drawing_preview_url, s.drawing_b64, s.drawing_mime
                )
                if not config.passport.use_mock and preview_url:
                    raw = await generate_passport_from_drawing(
                        db,
                        s,
                        preview_url,
                        config,
                        user_id=uid,
                    )
            passport = normalize_passport(raw)
            PartPassport.model_validate(passport)
            s.passport = passport
            # FR-005: версия в историю — только после успешной валидации
            append_turn(s, "passport", "assistant", "artifact", passport)
            # 006/F1: черновики замечаний очищаем после успешной перегенерации
            clear_stage_remarks(s, "passport")
            s.status = "passport_review"
            s.updated_at = utcnow()
            _push_event(db, s, "passport_generated", uid)
            db.commit()
            db.refresh(s)
        except Exception as exc:
            logger.exception("passport generation failed session=%s", s.id)
            s.status = "passport_failed"
            s.updated_at = utcnow()
            _push_event(db, s, "passport_failed", uid, {"error": _ai_error_message(exc)})
            db.commit()
            db.refresh(s)
            return

    skipped = session_operations_skipped(s)

    if s.status == "generating_blank_allowance" and s.passport and (
        s.selected_operations or skipped
    ):
        try:
            selected = list(s.selected_operations or [])
            ba = mock_blank_allowance(s.passport, selected)
            if not config.blank_allowance.use_mock and s.passport:
                ba = await generate_blank_allowance(
                    db,
                    s,
                    s.passport,
                    selected,
                    config,
                    user_id=uid,
                    operations_skipped=skipped,
                )
            s.blank_allowance = ba
            # FR-005: только успешный расчёт попадает в историю
            append_turn(s, "blank_allowance", "assistant", "artifact", ba)
            # 006/F1: очистка черновиков замечаний после успешной перегенерации
            clear_stage_remarks(s, "blank_allowance")
            s.blank_allowance_approved = False
            s.status = "blank_allowance_review"
            s.updated_at = utcnow()
            _push_event(db, s, "blank_allowance_generated", uid)
            db.commit()
            db.refresh(s)
        except Exception as exc:
            logger.exception("blank allowance failed session=%s", s.id)
            s.status = "blank_allowance_failed"
            s.updated_at = utcnow()
            _push_event(db, s, "blank_allowance_failed", uid, {"error": _ai_error_message(exc)})
            db.commit()
            db.refresh(s)
        return

    if s.status == "generating_technology" and s.passport and (
        s.selected_operations or skipped
    ):
        try:
            selected = list(s.selected_operations or [])
            if skipped and config.technology.use_mock:
                rows = list_catalog(db, s.team_id)
                selected = [
                    {
                        "catalog_id": str(r.id),
                        "operation": r.operation,
                        "equipment": r.equipment,
                    }
                    for r in rows[: min(3, len(rows))]
                ]
            md, tj = mock_technology(s.passport, selected_operations=selected)
            ba_ctx = s.blank_allowance if s.blank_allowance_approved else None
            if not config.technology.use_mock and s.passport:
                md, tj = await generate_technology(
                    db,
                    s,
                    s.passport,
                    selected,
                    config,
                    blank_allowance=ba_ctx,
                    user_id=uid,
                    operations_skipped=skipped,
                )
            if skipped:
                if config.technology.use_mock and selected:
                    s.selected_operations = selected
                elif not config.technology.use_mock:
                    route = (tj or {}).get("route") or []
                    synced = sync_selected_operations_from_route(
                        db, s.team_id, route
                    )
                    if synced:
                        s.selected_operations = synced
            s.technology_text = md
            s.technology_json = tj
            # FR-005: только успешная версия технологии попадает в историю
            append_turn(s, "technology", "assistant", "artifact", {"text": md, "json": tj})
            # 006/F1: очистка черновиков замечаний после успешной перегенерации
            clear_stage_remarks(s, "technology")
            s.status = "technology_review"
            s.updated_at = utcnow()
            _push_event(db, s, "technology_generated", uid)
        except Exception as exc:
            logger.exception("technology generation failed session=%s", s.id)
            s.status = "technology_failed"
            s.updated_at = utcnow()
            _push_event(db, s, "technology_failed", uid, {"error": _ai_error_message(exc)})
        db.commit()
        db.refresh(s)
