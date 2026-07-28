"""Доля полей, принятых без замечаний (FR-018/FR-019).

Сравнивает ПЕРВУЮ сгенерированную версию документа этапа с согласованной
(текущей) и считает долю неизменных полей. Источник версий — память
переписки sessions.llm_history (фича 002), как и в document_diff.

Если истории нет (этап согласован без единого замечания), первой версией
считается сам согласованный документ → доля принятия 100%.
"""
from __future__ import annotations

from typing import Any

from app.models import WorkSession
from app.services import field_paths as fp
from app.services.document_diff import KIND_ARTIFACT, compute_field_diffs


def first_artifact(s: WorkSession, stage: str) -> Any | None:
    """Первая artifact-версия этапа из llm_history; None если версий нет."""
    history = s.llm_history or {}
    turns = [t for t in (history.get(stage) or []) if t.get("kind") == KIND_ARTIFACT]
    return turns[0].get("content") if turns else None


def _route_codes(doc: Any) -> set[str]:
    codes: set[str] = set()
    if isinstance(doc, dict):
        for idx, step in enumerate(doc.get("route") or []):
            if isinstance(step, dict):
                code = step.get("code") or "OP" + str(step.get("number") or idx + 1).zfill(2)
                codes.add(code)
    return codes


def _total_fields(doc_type: str, first: Any, approved: Any) -> int:
    """Общее число сравниваемых полей документа (знаменатель доли)."""
    if doc_type == fp.STAGE_PASSPORT:
        return len(fp.PASSPORT_FIELDS)
    if doc_type == fp.STAGE_BLANK_ALLOWANCE:
        return len(fp.BLANK_ALLOWANCE_FIELDS)
    # Технология: скалярные поля + ячейки маршрута по объединению операций версий
    fj = first.get("json") if isinstance(first, dict) and "json" in first else first
    aj = approved.get("json") if isinstance(approved, dict) and "json" in approved else approved
    codes = _route_codes(fj) | _route_codes(aj)
    return len(fp.TECHNOLOGY_FIELDS) + len(codes) * len(fp.TECHNOLOGY_ROUTE_ATTRS)


def _approved_doc(s: WorkSession, doc_type: str) -> Any:
    if doc_type == fp.STAGE_PASSPORT:
        return s.passport
    if doc_type == fp.STAGE_BLANK_ALLOWANCE:
        return s.blank_allowance
    return {"text": s.technology_text, "json": s.technology_json}


def compute_stage_acceptance(s: WorkSession, stage: str) -> dict | None:
    """{'total','unchanged','share_pct'} для этапа или None, если документа нет."""
    doc_type = fp.doc_type_for_stage(stage)
    if not doc_type:
        return None
    approved = _approved_doc(s, doc_type)
    if not approved:
        return None
    # Нет истории правок → первая версия совпадает с согласованной (100% принятия)
    first = first_artifact(s, stage)
    if first is None:
        first = approved
    total = _total_fields(doc_type, first, approved)
    if total <= 0:
        return None
    changed = min(len(compute_field_diffs(first, approved, doc_type)), total)
    unchanged = total - changed
    return {
        "total": total,
        "unchanged": unchanged,
        "share_pct": round(unchanged / total * 100, 2),
    }


def snapshot_stage_acceptance(s: WorkSession, stage: str) -> None:
    """Сохранить снимок доли принятия этапа в sessions.field_acceptance."""
    res = compute_stage_acceptance(s, stage)
    if res is None:
        return
    acc = dict(s.field_acceptance or {})
    acc[stage] = res
    s.field_acceptance = acc  # переприсваивание для отслеживания изменения JSONB
