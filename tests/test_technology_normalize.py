"""Нормализация технологической карты v2."""
from app.services.technology_normalize import mock_technology, normalize_technology


def test_normalize_v2_structured():
    raw = {
        "schema_version": "2.0",
        "header": {
            "part_designation": "534",
            "part_name": "Толкатель",
            "material": "40Х",
            "features": "—",
        },
        "key_dimensions": "Ø50 h14",
        "blank": {"type": "Пруток", "dimensions": "Ø55", "allowances": "5 мм"},
        "route": [
            {
                "code": "OP01",
                "number": 1,
                "name": "Отрезная",
                "equipment": "ARG330",
                "transitions": "Отрезать",
                "final_sizes": "Ø55",
            },
            {
                "code": "OP10",
                "number": 10,
                "name": "Токарная",
                "transitions": "Точение",
                "final_sizes": "Ø50",
            },
        ],
        "heat_treatment": "Закалка",
        "dimensions_control": "Цепочка размеров",
    }
    md, tj = normalize_technology(raw, None)
    assert tj["schema_version"] == "2.0"
    assert tj["route"][0]["code"] == "OP01"
    assert tj["route"][0]["transitions"] == "Отрезать"
    assert "OP01" in md
    assert tj["header"]["part_designation"] == "534"


def test_upgrade_v1_operations_to_route():
    raw = {
        "schema_version": "1.0",
        "part_designation": "X-1",
        "part_name": "Вал",
        "material": "Сталь 45",
        "summary": "Ключевые размеры",
        "operations": [
            {
                "number": 1,
                "name": "Заготовка",
                "description": "Резка",
                "equipment": "ARG330",
            }
        ],
    }
    _, tj = normalize_technology(raw, None)
    assert tj["schema_version"] == "2.0"
    assert tj["route"][0]["transitions"] == "Резка"
    assert tj["route"][0]["equipment"] == "ARG330"


def test_mock_v2():
    _, tj = mock_technology(None)
    assert tj["schema_version"] == "2.0"
    assert len(tj["route"]) >= 2
