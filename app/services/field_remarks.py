"""Черновики замечаний к полям и сборка пакета для перегенерации.

Хранение в sessions.field_remarks (JSONB) per-stage:
{ stage: { "applied": [ {field, label, text} ], "general_draft": str|null } }

specs/006-field-remarks-diff/research.md (R-03, R-05).
"""
from __future__ import annotations

from app.core.exceptions import AppError
from app.models import WorkSession
from app.services import field_paths as fp

MAX_TEXT = 2000


def get_stage_remarks(s: WorkSession, stage: str) -> dict:
    """Черновик этапа: {applied:[...], general_draft}."""
    data = s.field_remarks or {}
    entry = data.get(stage) or {}
    return {
        "applied": list(entry.get("applied") or []),
        "general_draft": entry.get("general_draft"),
    }


def _validate_applied(doc_type: str, applied: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    seen: set[str] = set()
    for item in applied:
        field = str(item.get("field") or "").strip()
        text = str(item.get("text") or "").strip()
        if not field or not fp.is_valid_field(doc_type, field):
            raise AppError("VALIDATION_ERROR", f"Неизвестное поле: {field}", 400)
        if not text:
            raise AppError("VALIDATION_ERROR", "Текст замечания обязателен", 400)
        if len(text) > MAX_TEXT:
            raise AppError("VALIDATION_ERROR", "Замечание слишком длинное", 400)
        if field in seen:
            continue  # одно замечание на поле — последнее побеждает
        seen.add(field)
        label = fp.field_label(doc_type, field) or field
        cleaned.append({"field": field, "label": label, "text": text})
    return cleaned


def set_stage_remarks(
    s: WorkSession,
    stage: str,
    applied: list[dict],
    general_draft: str | None,
) -> dict:
    """Перезаписать черновик этапа (autosave). Возвращает сохранённую запись."""
    doc_type = fp.doc_type_for_stage(stage)
    if not doc_type:
        raise AppError("INVALID_STATE", "Этап не на согласовании", 409)
    cleaned = _validate_applied(doc_type, applied or [])
    gd = (general_draft or "").strip() or None
    if gd and len(gd) > MAX_TEXT:
        raise AppError("VALIDATION_ERROR", "Общий текст слишком длинный", 400)
    entry = {"applied": cleaned, "general_draft": gd}
    # JSONB не отслеживает мутации in-place — переприсваиваем новый dict
    data = dict(s.field_remarks or {})
    data[stage] = entry
    s.field_remarks = data
    return entry


def clear_stage_remarks(s: WorkSession, stage: str) -> None:
    """Очистить черновик этапа (после успешной перегенерации, F1)."""
    data = dict(s.field_remarks or {})
    if stage in data:
        data.pop(stage)
        s.field_remarks = data


def has_field_remarks(s: WorkSession, stage: str) -> bool:
    """Есть ли хотя бы одно применённое замечание на этапе (FR-008)."""
    return bool(get_stage_remarks(s, stage)["applied"])


def compose_remark_text(field_remarks: list[dict], general_text: str | None) -> str:
    """Единый текст замечания: точечные + общий блок (FR-011, R-05)."""
    parts: list[str] = []
    if field_remarks:
        parts.append("Замечания к полям:")
        for item in field_remarks:
            label = item.get("label") or item.get("field")
            parts.append(f"- Поле «{label}»: {item.get('text')}")
    gt = (general_text or "").strip()
    if gt:
        if parts:
            parts.append("")
        parts.append("Общие замечания:")
        parts.append(gt)
    return "\n".join(parts).strip()
