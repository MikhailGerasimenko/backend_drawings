"""Нормализация ответа LLM для расчёта припусков."""
from app.services.blank_allowance_normalize import normalize_blank_allowance


def test_dict_pre_heat_treatment_becomes_readable_text():
    raw = {
        "confirmation_required": "",
        "blank": {
            "source_stock": "Ø21 × 105",
            "pre_heat_treatment": {
                "external_diameter": 21,
                "overall_length": 105,
                "hole_depth": 31,
                "hole_diameter": 6.8,
                "description": (
                    "Черновая токарная перед термоулучшением. Припуск +5 мм на наружный диаметр."
                ),
            },
            "pre_finish_machining": "",
        },
        "allowances": {"summary": "Итого"},
    }
    out = normalize_blank_allowance(raw)
    text = out["blank"]["pre_heat_treatment"]
    assert "Черновая токарная перед термоулучшением" in text
    assert "external_diameter" not in text
    assert "{" not in text
