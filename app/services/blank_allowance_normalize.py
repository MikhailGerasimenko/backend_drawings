"""Нормализация и mock ответа расчёта припусков."""
import ast
import json

from app.services.passport_normalize import passport_field_text


def _format_selected_operations(selected: list[dict]) -> str:
    lines = []
    for i, item in enumerate(selected, 1):
        op = item.get("operation") or ""
        eq = item.get("equipment") or ""
        lines.append(f"{i}. {op} ({eq})")
    return "\n".join(lines)


def _s(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


# Подписи типовых полей, если LLM вернул объект вместо строки
_BLANK_DIM_LABELS = {
    "external_diameter": "Нар. Ø",
    "overall_length": "Длина",
    "hole_depth": "Глубина отверстия",
    "hole_diameter": "Ø отверстия",
    "diameter": "Ø",
    "length": "Длина",
}


def _blank_field_text(val) -> str:
    """Текст для UI: строка как есть; dict/list — читаемый формат, не repr()."""
    if val is None:
        return ""
    if isinstance(val, str):
        s = val.strip()
        # Уже сохранённый repr от старой нормализации — попытаться разобрать
        if s.startswith("{") and s.endswith("}"):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, dict):
                    return _blank_field_text(parsed)
            except (SyntaxError, ValueError):
                pass
        return s
    if isinstance(val, list):
        lines = [_blank_field_text(x) for x in val]
        return "\n".join(line for line in lines if line)
    if isinstance(val, dict):
        parts: list[str] = []
        for key in ("description", "text", "summary", "notes", "value"):
            t = val.get(key)
            if isinstance(t, str) and t.strip():
                parts.append(t.strip())
                break
            if t is not None and not isinstance(t, str):
                sub = _blank_field_text(t)
                if sub:
                    parts.append(sub)
                    break
        dim_bits: list[str] = []
        for k, v in val.items():
            if k in ("description", "text", "summary", "notes", "value"):
                continue
            if v is None or v == "":
                continue
            if isinstance(v, (dict, list)):
                sub = _blank_field_text(v)
                if sub:
                    dim_bits.append(sub)
            else:
                dim_bits.append(f"{_BLANK_DIM_LABELS.get(k, k)}: {v}")
        if dim_bits:
            parts.append("; ".join(dim_bits))
        return "\n".join(parts)
    return str(val).strip()


def normalize_blank_allowance(raw: dict | None) -> dict:
    """Привести ответ LLM к структуре Appendix B."""
    if not isinstance(raw, dict):
        raw = {}
    blank_in = raw.get("blank") if isinstance(raw.get("blank"), dict) else {}
    allowances_in = raw.get("allowances") if isinstance(raw.get("allowances"), dict) else {}
    return {
        "schema_version": "1.0",
        "confirmation_required": _s(raw.get("confirmation_required")),
        "blank": {
            "source_stock": _blank_field_text(blank_in.get("source_stock")),
            "pre_heat_treatment": _blank_field_text(blank_in.get("pre_heat_treatment")),
            "pre_finish_machining": _blank_field_text(blank_in.get("pre_finish_machining")),
        },
        "allowances": {
            "summary": _blank_field_text(allowances_in.get("summary")),
        },
    }


def mock_blank_allowance(passport: dict | None, selected_operations: list[dict]) -> dict:
    """Mock без API-ключа (осевые детали, базовые припуски)."""
    dims = passport_field_text(passport or {}, "overall_dimensions") or "L×Ø по паспорту"
    mat = passport_field_text(passport or {}, "material_hardness") or "сталь"
    ops = _format_selected_operations(selected_operations or [])
    return normalize_blank_allowance(
        {
            "confirmation_required": "",
            "blank": {
                "source_stock": (
                    f"Заготовка прокат (mock): габариты {dims}; +5 мм на Ø и L "
                    f"(ленточно-отрезная)"
                ),
                "pre_heat_treatment": "",
                "pre_finish_machining": (
                    f"Чистовые припуски (mock) под маршрут:\n{ops or '—'}"
                ),
            },
            "allowances": {
                "summary": f"Mock-расчёт для материала {mat}; проверьте в production с LLM.",
            },
        }
    )


def blank_allowance_for_technology_context(blank: dict | None) -> str:
    if not blank:
        return ""
    return json.dumps(blank, ensure_ascii=False, indent=2)


def validate_blank_allowance_store(data: dict | None) -> dict:
    """Проверка структуры перед сохранением в сессию."""
    norm = normalize_blank_allowance(data)
    for section in ("source_stock", "pre_heat_treatment", "pre_finish_machining"):
        if section not in norm.get("blank", {}):
            raise ValueError(f"blank.{section} обязателен")
    if "summary" not in norm.get("allowances", {}):
        raise ValueError("allowances.summary обязателен")
    return norm
