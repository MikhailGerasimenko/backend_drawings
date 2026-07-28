"""Память переписки LLM по этапам сессии.

specs/002-llm-conversation-memory: contracts/README.md, data-model.md.
История хранится в sessions.llm_history (JSONB) как
{stage: [turn, ...]}, turn = {role, kind, ts, content}.
"""
from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.models import WorkSession, utcnow

STAGE_PASSPORT = "passport"
STAGE_BLANK_ALLOWANCE = "blank_allowance"
STAGE_TECHNOLOGY = "technology"

KIND_ARTIFACT = "artifact"
KIND_REMARK = "remark"


def _stage_turns(s: WorkSession, stage: str) -> list[dict]:
    history = s.llm_history or {}
    return list(history.get(stage) or [])


def _set_stage_turns(s: WorkSession, stage: str, turns: list[dict]) -> None:
    # JSONB не отслеживает мутации in-place — переприсваиваем новый dict
    history = dict(s.llm_history or {})
    history[stage] = turns
    s.llm_history = history


def append_turn(
    s: WorkSession,
    stage: str,
    role: str,
    kind: str,
    content: Any,
) -> None:
    """Добавляет turn в конец истории этапа (FR-003; без 50-cap)."""
    turns = _stage_turns(s, stage)
    turns.append(
        {
            "role": role,
            "kind": kind,
            "ts": utcnow().isoformat(),
            "content": content,
        }
    )
    _set_stage_turns(s, stage, turns)


def reset_stage(s: WorkSession, stage: str) -> None:
    """Сброс истории этапа при смене входного контекста (edge case spec 002)."""
    if (s.llm_history or {}).get(stage):
        _set_stage_turns(s, stage, [])


def seed_if_empty(s: WorkSession, stage: str, artifact: Any) -> None:
    """R-07: in-flight сессия без истории — текущий артефакт как первая версия."""
    if artifact and not _stage_turns(s, stage):
        append_turn(s, stage, "assistant", KIND_ARTIFACT, artifact)


def _serialize_artifact(content: Any) -> str:
    """Версия артефакта как assistant-сообщение (T005)."""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(content)


def _turn_to_message(turn: dict) -> dict:
    role = turn.get("role") or ("assistant" if turn.get("kind") == KIND_ARTIFACT else "user")
    content = turn.get("content")
    if turn.get("kind") == KIND_ARTIFACT:
        return {"role": role, "content": _serialize_artifact(content)}
    return {"role": role, "content": f"Замечания инженера (исправь с учётом):\n{content}"}


def _estimate_chars(turns: list[dict]) -> int:
    total = 0
    for t in turns:
        try:
            total += len(json.dumps(t.get("content"), ensure_ascii=False))
        except (TypeError, ValueError):
            total += len(str(t.get("content")))
    return total


def truncate_history(turns: list[dict], budget: int) -> list[dict]:
    """FR-010: при превышении бюджета удаляются самые старые artifact-turn'ы.

    Сохраняются: все remark-turn'ы и последняя artifact-версия.
    system и initial-вход в turns не входят (собираются отдельно) и не усекаются.
    """
    if budget <= 0 or _estimate_chars(turns) <= budget:
        return list(turns)

    artifact_idx = [i for i, t in enumerate(turns) if t.get("kind") == KIND_ARTIFACT]
    if len(artifact_idx) <= 1:
        return list(turns)

    result = list(turns)
    # Самые старые версии — кандидаты на удаление; последняя версия неприкосновенна
    removable = artifact_idx[:-1]
    for idx in removable:
        if _estimate_chars(result) <= budget:
            break
        result = [t for t in result if t is not turns[idx]]
    return result


def _stage_session_artifact(s: WorkSession, stage: str) -> Any:
    if stage == STAGE_PASSPORT:
        return s.passport
    if stage == STAGE_BLANK_ALLOWANCE:
        return s.blank_allowance
    if stage == STAGE_TECHNOLOGY:
        if s.technology_text or s.technology_json:
            return {"text": s.technology_text, "json": s.technology_json}
    return None


def build_messages(
    stage: str,
    s: WorkSession,
    *,
    system_prompt: str,
    initial_user_content: Any,
    budget: int | None = None,
) -> list[dict]:
    """Собирает messages: system → initial → история (assistant/user)* (FR-001/002/006).

    История извлекается из s.llm_history[stage]; при пустой истории и наличии
    артефакта в сессии — сидирование R-07. Первая генерация (FR-004) даёт
    [system, user] без блока истории.
    """
    turns = _stage_turns(s, stage)
    if not turns:
        artifact = _stage_session_artifact(s, stage)
        if artifact:
            turns = [
                {
                    "role": "assistant",
                    "kind": KIND_ARTIFACT,
                    "ts": utcnow().isoformat(),
                    "content": artifact,
                }
            ]

    max_chars = settings.llm_history_max_chars if budget is None else budget
    turns = truncate_history(turns, max_chars)

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_user_content},
    ]
    messages.extend(_turn_to_message(t) for t in turns)
    return messages
