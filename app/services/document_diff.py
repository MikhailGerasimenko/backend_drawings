"""Вычисление diff отображаемых полей между двумя версиями документа.

Предыдущая версия берётся из памяти переписки (sessions.llm_history[stage],
фича 002): сравниваются две последние artifact-версии этапа. Отдельная
колонка-снимок не вводится.

specs/006-field-remarks-diff/research.md (R-01, R-02).
"""
from __future__ import annotations

from typing import Any

from app.models import WorkSession
from app.services import field_paths as fp
from app.services.passport_normalize import normalize_passport

KIND_ARTIFACT = "artifact"

# Маркер отсутствующего значения паспорта (совпадает с рендером фронтенда)
_MISSING = "не указано на чертеже"


def previous_artifact(s: WorkSession, stage: str) -> Any | None:
    """Предпоследняя artifact-версия этапа из llm_history; None если версий < 2."""
    history = s.llm_history or {}
    turns = [t for t in (history.get(stage) or []) if t.get("kind") == KIND_ARTIFACT]
    if len(turns) < 2:
        return None
    return turns[-2].get("content")


def _norm(value: Any) -> str | None:
    """Нормализация значения к отображаемой строке (или None)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _passport_value(doc: dict, field: str) -> str | None:
    if field == "notes":
        return _norm(doc.get("notes"))
    f = doc.get(field) or {}
    if isinstance(f, dict):
        if f.get("missing_on_drawing"):
            return _MISSING
        return _norm(f.get("value"))
    return _norm(f)


def _dotted(doc: dict, path: str) -> Any:
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _route_index(doc: dict) -> dict[str, dict]:
    """Строки маршрута технологии по стабильному ключу OPxx."""
    out: dict[str, dict] = {}
    for idx, step in enumerate(doc.get("route") or []):
        if not isinstance(step, dict):
            continue
        code = step.get("code") or "OP" + str(step.get("number") or idx + 1).zfill(2)
        out[code] = step
    return out


def _passport_diffs(prev: dict, curr: dict) -> list[dict]:
    diffs: list[dict] = []
    prev = normalize_passport(prev)
    curr = normalize_passport(curr)
    for field, label in fp.PASSPORT_FIELDS.items():
        old = _passport_value(prev, field)
        new = _passport_value(curr, field)
        if old != new:
            diffs.append({"field": field, "label": label, "old": old, "new": new})
    return diffs


def _flat_diffs(prev: dict, curr: dict, fields: dict[str, str]) -> list[dict]:
    diffs: list[dict] = []
    for field, label in fields.items():
        old = _norm(_dotted(prev, field))
        new = _norm(_dotted(curr, field))
        if old != new:
            diffs.append({"field": field, "label": label, "old": old, "new": new})
    return diffs


def _route_title(step: dict, code: str) -> str:
    name = step.get("name")
    return code + (": " + str(name) if name else "")


def _technology_diffs(prev: dict, curr: dict) -> list[dict]:
    diffs = _flat_diffs(prev, curr, fp.TECHNOLOGY_FIELDS)
    prev_rows = _route_index(prev)
    curr_rows = _route_index(curr)
    common = prev_rows.keys() & curr_rows.keys()
    removed = prev_rows.keys() - curr_rows.keys()
    added = curr_rows.keys() - prev_rows.keys()

    # Изменённые ячейки операций, присутствующих в обеих версиях
    for code in sorted(common):
        prow = prev_rows[code]
        crow = curr_rows[code]
        for attr in fp.TECHNOLOGY_ROUTE_ATTRS:
            old = _norm(prow.get(attr))
            new = _norm(crow.get(attr))
            if old != new:
                field = fp.route_field(code, attr)
                diffs.append(
                    {
                        "field": field,
                        "label": fp.field_label(fp.STAGE_TECHNOLOGY, field) or field,
                        "old": old,
                        "new": new,
                    }
                )

    # Удалённые целиком операции — фронтенд рисует их красным/зачёркнутым
    for code in sorted(removed):
        step = prev_rows[code]
        diffs.append(
            {
                "field": "route[" + code + "]",
                "label": _route_title(step, code),
                "kind": "route_removed",
                "step": step,
            }
        )

    # Добавленные целиком операции — фронтенд рисует их зелёным
    for code in sorted(added):
        step = curr_rows[code]
        diffs.append(
            {
                "field": "route[" + code + "]",
                "label": _route_title(step, code),
                "kind": "route_added",
            }
        )
    return diffs


def compute_field_diffs(prev: Any, curr: Any, doc_type: str) -> list[dict]:
    """Список изменённых полей между prev и curr (только old != new)."""
    if not isinstance(prev, dict) or not isinstance(curr, dict):
        return []
    if doc_type == fp.STAGE_PASSPORT:
        return _passport_diffs(prev, curr)
    if doc_type == fp.STAGE_BLANK_ALLOWANCE:
        return _flat_diffs(prev, curr, fp.BLANK_ALLOWANCE_FIELDS)
    if doc_type == fp.STAGE_TECHNOLOGY:
        # Технология в истории хранится как {text, json}; берём json
        prev_json = prev.get("json") if "json" in prev else prev
        curr_json = curr.get("json") if "json" in curr else curr
        if not isinstance(prev_json, dict) or not isinstance(curr_json, dict):
            return []
        return _technology_diffs(prev_json, curr_json)
    return []


def stage_field_diffs(s: WorkSession, stage: str) -> list[dict]:
    """Diff текущего артефакта этапа против предыдущей версии (FR-002/FR-017)."""
    doc_type = fp.doc_type_for_stage(stage)
    if not doc_type:
        return []
    prev = previous_artifact(s, stage)
    if prev is None:
        return []
    if doc_type == fp.STAGE_PASSPORT:
        curr: Any = s.passport
    elif doc_type == fp.STAGE_BLANK_ALLOWANCE:
        curr = s.blank_allowance
    else:
        curr = {"text": s.technology_text, "json": s.technology_json}
    if not curr:
        return []
    return compute_field_diffs(prev, curr, doc_type)
