"""Нормализация паспорта v2."""
from app.services.passport_normalize import normalize_passport, passport_session_title


def test_normalize_v2_flat_strings():
    raw = {
        "schema_version": "2.0",
        "part_type": "Тело вращения",
        "designation": "АБВ.001.002",
        "overall_dimensions": "Ø100 × 60",
        "material_hardness": "40Х",
        "outer_geometry": "Ø100 h11",
        "inner_geometry": "Ø30 H8",
        "special_elements": "4×Ø6",
        "gdt": "⊥ 0.02 A",
        "notes": "Таблица L=85",
    }
    p = normalize_passport(raw)
    assert p["schema_version"] == "2.0"
    assert p["designation"]["value"] == "АБВ.001.002"
    assert "Ø100" in p["outer_geometry"]["value"]


def test_upgrade_v1():
    raw = {
        "schema_version": "1.0",
        "designation": {"value": "X-1", "missing_on_drawing": False},
        "name": {"value": "Вал", "missing_on_drawing": False},
        "material": {"value": "Сталь 20", "missing_on_drawing": False},
        "dimensions": {"value": "100 мм", "missing_on_drawing": False},
        "mass": {"value": "1 кг", "missing_on_drawing": False},
        "tolerances": {"value": "IT7", "missing_on_drawing": False},
        "roughness": {"value": "Ra 1.6", "missing_on_drawing": False},
        "heat_treatment": {"value": None, "missing_on_drawing": True},
    }
    p = normalize_passport(raw)
    assert p["schema_version"] == "2.0"
    assert p["designation"]["value"] == "X-1"
    assert p["part_type"]["value"] == "Вал"
    assert p["material_hardness"]["value"] == "Сталь 20"
    assert passport_session_title(p) == "X-1 - Вал"
