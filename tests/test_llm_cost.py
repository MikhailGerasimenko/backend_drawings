"""Стоимость LLM из ответа модели (FR-022) — без тарифных таблиц."""
from decimal import Decimal

from app.services.llm_telemetry import (
    compute_cost,
    cost_from_provider_usage,
    openrouter_cache_hit,
)


def test_cache_hit_zero_cost():
    cost, meta = compute_cost(
        {"usage": {"cost": 0.05}}, provider_response_cache_hit=True
    )
    assert cost == Decimal("0")
    assert not meta.get("cost_missing")


def test_cost_from_provider_response():
    cost, meta = compute_cost({"usage": {"cost": 0.0123456}})
    assert cost == Decimal("0.012346")
    assert meta.get("cost_source") == "provider"


def test_cost_missing_when_provider_omits():
    cost, meta = compute_cost({"usage": {"prompt_tokens": 100}})
    assert cost is None
    assert meta.get("cost_missing") is True


def test_cost_from_provider_usage_helper():
    cost = cost_from_provider_usage({"usage": {"cost": 0.0123456}})
    assert cost == Decimal("0.012346")
    assert cost_from_provider_usage({"usage": {}}) is None


def test_openrouter_cache_hit_header():
    class H:
        def get(self, k, default=None):
            return {"X-OpenRouter-Cache-Status": "HIT"}.get(k, default)

    assert openrouter_cache_hit(H()) is True
