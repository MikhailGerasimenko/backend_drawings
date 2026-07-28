"""Телеметрия LLM/VLM: usage, cost, llm_requests_log."""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.models import LlmRequestLog


@dataclass
class TelemetryCtx:
    db: Session
    session_id: UUID
    user_id: UUID
    stage: str  # passport | blank_allowance | technology
    extra_meta: dict = field(default_factory=dict)


def parse_usage(data: dict) -> tuple[int, int, int]:
    usage = data.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    cached = 0
    details = usage.get("prompt_tokens_details") or {}
    if isinstance(details, dict):
        cached = int(details.get("cached_tokens") or 0)
    return prompt, completion, cached


def openrouter_cache_hit(headers: httpx.Headers) -> bool:
    return (headers.get("X-OpenRouter-Cache-Status") or "").upper() == "HIT"


def cost_from_provider_usage(response_data: dict) -> Decimal | None:
    """Стоимость запроса из ответа модели (OpenRouter usage.cost)."""
    usage = response_data.get("usage") or {}
    raw = usage.get("cost")
    if raw is None:
        return None
    try:
        return Decimal(str(raw)).quantize(Decimal("0.000001"))
    except Exception:
        return None


def compute_cost(
    response_data: dict,
    *,
    provider_response_cache_hit: bool = False,
) -> tuple[Decimal | None, dict[str, Any]]:
    """Стоимость запроса берём напрямую из ответа модели (FR-022).

    Внутренних тарифных таблиц больше нет; при cache hit стоимость = 0,
    иначе usage.cost из ответа провайдера (или None, если провайдер не отдал).
    """
    meta: dict[str, Any] = {}
    if provider_response_cache_hit:
        return Decimal("0"), meta
    cost = cost_from_provider_usage(response_data)
    if cost is None:
        meta["cost_missing"] = True
    else:
        meta["cost_source"] = "provider"
    return cost, meta


# data-URL с base64 (чертёж) занимает весь лимит payload_prompt — заменяем заглушкой,
# чтобы в лог попадала вся текстовая часть запроса (история, замечания)
_BASE64_DATA_URL_RE = re.compile(r"data:[\w.+-]+/[\w.+-]+;base64,[A-Za-z0-9+/=]+")


def _messages_to_prompt_text(messages: list) -> str:
    try:
        text = json.dumps(messages, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(messages)
    text = _BASE64_DATA_URL_RE.sub("<BASE64_OMITTED>", text)
    return text[:50000]


def record_llm_call(
    ctx: TelemetryCtx,
    model_name: str,
    messages: list,
    response_data: dict,
    http_response: httpx.Response,
    latency_ms: int,
) -> None:
    prompt_t, completion_t, cached_t = parse_usage(response_data)
    cache_hit = openrouter_cache_hit(http_response.headers)
    cost, extra_meta = compute_cost(
        response_data,
        provider_response_cache_hit=cache_hit,
    )
    try:
        raw_response_text = json.dumps(response_data, ensure_ascii=False)
    except (TypeError, ValueError):
        raw_response_text = str(response_data)

    meta = {"stage": ctx.stage, "provider": "openrouter", **extra_meta, **(ctx.extra_meta or {})}
    ctx.db.add(
        LlmRequestLog(
            id=uuid.uuid4(),
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            model_name=model_name,
            prompt_tokens=prompt_t,
            completion_tokens=completion_t,
            cached_tokens=cached_t,
            provider_response_cache_hit=cache_hit,
            cost=cost,
            latency_ms=latency_ms,
            payload_prompt=_messages_to_prompt_text(messages),
            payload_response=raw_response_text[:50000] or None,
            meta=meta,
        )
    )


def record_llm_call_failed(
    ctx: TelemetryCtx,
    model_name: str,
    messages: list,
    *,
    latency_ms: int | None = None,
    error_code: str = "AI_UNAVAILABLE",
) -> None:
    ctx.db.add(
        LlmRequestLog(
            id=uuid.uuid4(),
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            model_name=model_name,
            prompt_tokens=0,
            completion_tokens=0,
            cached_tokens=0,
            provider_response_cache_hit=False,
            cost=None,
            latency_ms=latency_ms,
            payload_prompt=_messages_to_prompt_text(messages),
            payload_response=None,
            meta={"stage": ctx.stage, "error_code": error_code},
        )
    )
