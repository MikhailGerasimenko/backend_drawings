"""Тесты парсинга JSON из ответа LLM."""

import json
import re

import pytest

from app.core.exceptions import AppError
from app.services.ai import _parse_json_content


def test_greedy_regex_fails_on_trailing_brace():
    """Жадный regex ломает JSON при хвосте с '}'."""
    bad = '{"schema_version": "2.0", "route": []} note with }'
    m = re.search(r"\{[\s\S]*\}", bad.strip())
    with pytest.raises(json.JSONDecodeError):
        json.loads(m.group(0))


def test_parse_json_with_trailing_text():
    parsed = _parse_json_content('{"schema_version": "2.0", "route": []} note with }')
    assert parsed["schema_version"] == "2.0"


def test_parse_json_with_brace_inside_string():
    raw = '{"route": [{"transitions": "size } test"}]}'
    parsed = _parse_json_content(raw)
    assert parsed["route"][0]["transitions"] == "size } test"


def test_parse_json_markdown_fence():
    raw = '```json\n{"schema_version": "2.0", "route": []}\n```'
    parsed = _parse_json_content(raw)
    assert parsed["schema_version"] == "2.0"


def test_parse_json_invalid_raises():
    with pytest.raises(AppError) as exc:
        _parse_json_content("not json at all")
    assert exc.value.message == "Ответ AI не является корректным JSON"


def test_normalize_wrapped_json_card():
    from app.services.technology_normalize import normalize_technology

    inner = {
        "schema_version": "2.0",
        "route": [
            {
                "code": "OP01",
                "number": 1,
                "name": "Отрезная",
                "transitions": "Отрезать",
            }
        ],
    }
    _, tj = normalize_technology({"json": inner, "text": "markdown"}, None)
    assert tj["route"][0]["code"] == "OP01"
