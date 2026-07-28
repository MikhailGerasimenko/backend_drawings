"""Нормализация ответа VLM к паспорту v2.0."""
from app.schemas.base import PartPassport, PassportField


def _as_field(raw_val) -> PassportField:
    if raw_val is None:
        return PassportField(value=None, missing_on_drawing=True)
    if isinstance(raw_val, str):
        text = raw_val.strip()
        if not text:
            return PassportField(value=None, missing_on_drawing=True)
        return PassportField(value=text, missing_on_drawing=False)
    if isinstance(raw_val, (int, float)):
        return PassportField(value=str(raw_val), missing_on_drawing=False)
    if isinstance(raw_val, dict):
        val = raw_val.get("value")
        if val is not None and not isinstance(val, str):
            val = str(val)
        if val is not None:
            val = str(val).strip() or None
        missing = bool(raw_val.get("missing_on_drawing"))
        if val is None and not missing:
            missing = True
        return PassportField(value=val, missing_on_drawing=missing, unit=raw_val.get("unit"))
    if isinstance(raw_val, list):
        lines = [str(x).strip() for x in raw_val if str(x).strip()]
        if lines:
            return PassportField(value="\n".join(lines), missing_on_drawing=False)
    return PassportField(value=None, missing_on_drawing=True)


def _pick(raw: dict, *keys: str) -> PassportField:
    for key in keys:
        if key in raw and raw[key] is not None:
            return _as_field(raw[key])
    return PassportField(value=None, missing_on_drawing=True)


def _section(raw: dict, *section_keys: str) -> dict:
    for sk in section_keys:
        block = raw.get(sk)
        if isinstance(block, dict):
            return block
    return {}


def _notes_text(raw: dict) -> str:
    n = raw.get("notes") or raw.get("примечания")
    if n is None:
        return ""
    if isinstance(n, str):
        return n.strip()
    if isinstance(n, dict):
        return str(n.get("value") or n.get("text") or "").strip()
    if isinstance(n, list):
        return "\n".join(str(x) for x in n).strip()
    return str(n).strip()


def _upgrade_v1_raw(raw: dict) -> dict:
    def v1(key: str) -> str | None:
        f = raw.get(key) or {}
        if isinstance(f, dict) and f.get("value"):
            return str(f["value"]).strip()
        return None

    extras: list[str] = []
    for key, label in (
        ("name", "Наименование"),
        ("mass", "Масса"),
        ("tolerances", "Допуски"),
        ("roughness", "Шероховатость"),
        ("heat_treatment", "ТО"),
    ):
        val = v1(key)
        if val:
            extras.append(f"{label}: {val}")

    notes = _notes_text(raw)
    if extras:
        notes = (notes + "\n\n" + "\n".join(extras)).strip()

    def f1(key: str) -> dict:
        val = v1(key)
        return {"value": val, "missing_on_drawing": not bool(val)}

    return {
        "schema_version": "2.0",
        "part_type": f1("name"),
        "designation": raw.get("designation") or {"value": None, "missing_on_drawing": True},
        "overall_dimensions": raw.get("dimensions") or {"value": None, "missing_on_drawing": True},
        "material_hardness": raw.get("material") or {"value": None, "missing_on_drawing": True},
        "outer_geometry": {"value": None, "missing_on_drawing": True},
        "inner_geometry": {"value": None, "missing_on_drawing": True},
        "special_elements": {"value": None, "missing_on_drawing": True},
        "gdt": raw.get("tolerances") or {"value": None, "missing_on_drawing": True},
        "notes": notes,
    }


def normalize_passport(raw: dict | None) -> dict:
    if not raw:
        return mock_passport()

    data = dict(raw)
    ver = str(data.get("schema_version") or "")
    if ver == "1.0" or (
        "material" in data and "material_hardness" not in data and "part_type" not in data
    ):
        data = _upgrade_v1_raw(data)

    general = _section(data, "general", "общие_данные", "общие")
    geometry = _section(data, "geometry", "геометрия")
    gdt_block = _section(data, "gdt_section", "гдт")

    p = PartPassport(
        part_type=_pick(data, "part_type")
        or _pick(general, "part_type", "type", "тип", "тип_детали"),
        designation=_pick(data, "designation", "обозначение")
        or _pick(general, "designation", "обозначение"),
        overall_dimensions=_pick(
            data, "overall_dimensions", "dimensions", "габариты", "overall_size"
        )
        or _pick(general, "overall_dimensions", "габариты", "габариты_макс"),
        material_hardness=_pick(
            data, "material_hardness", "material", "материал"
        )
        or _pick(general, "material_hardness", "material", "материал"),
        outer_geometry=_pick(data, "outer_geometry", "outer", "наружный_контур")
        or _pick(geometry, "outer_geometry", "outer", "наружный", "наружный_контур"),
        inner_geometry=_pick(data, "inner_geometry", "inner", "внутренняя")
        or _pick(geometry, "inner_geometry", "inner", "внутренняя_система", "внутренняя"),
        special_elements=_pick(data, "special_elements", "special", "спец_элементы")
        or _pick(geometry, "special_elements", "special", "спецэлементы"),
        gdt=_pick(data, "gdt", "gd_t")
        or _pick(gdt_block, "gdt", "text", "value")
        or _pick(data, "tolerances"),
        notes=_notes_text(data),
    )
    return p.to_store()


def mock_passport() -> dict:
    def field(value, missing=False):
        return PassportField(value=value, missing_on_drawing=missing).model_dump()

    return PartPassport(
        part_type=field("Тело вращения (втулка)"),
        designation=field("Деталь-001"),
        overall_dimensions=field("Ø120 × 85 мм"),
        material_hardness=field("Сталь 45, HRC 28–32"),
        outer_geometry=field(
            "Ø120 h11 — корпус\nØ95 f8 — посадочный пояс\nФаска 2×45° по торцу"
        ),
        inner_geometry=field(
            "Ступенчатое отверстие:\nØ40 H8, глубина 30 от торца\nØ25 сквозное"
        ),
        special_elements=field("6 отв. Ø8.5, PCD Ø80"),
        gdt=field("⊥ 0.05 относительно базы A"),
        notes="Демо-паспорт без API-ключа",
    ).to_store()


def passport_session_title(passport: dict | None) -> str | None:
    """Название сессии после согласования паспорта: «Обозначение - Тип детали»."""
    if not passport:
        return None
    des = passport_field_text(passport, "designation")
    part = passport_field_text(passport, "part_type")
    if not des or not part:
        return None
    return f"{des} - {part}"


def passport_field_text(passport: dict | None, key: str) -> str:
    if not passport:
        return ""
    f = passport.get(key) or {}
    if isinstance(f, dict) and f.get("value"):
        return str(f["value"]).strip()
    if key == "material":
        return passport_field_text(passport, "material_hardness")
    if key == "name":
        return passport_field_text(passport, "part_type")
    if key == "dimensions":
        return passport_field_text(passport, "overall_dimensions")
    return ""
