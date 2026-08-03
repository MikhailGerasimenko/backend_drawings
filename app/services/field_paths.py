"""Карта стабильных идентификаторов полей по типам документов.

Единый источник правды для diff (document_diff), идентификации замечаний к полям
(FR-015) и сборки текста для LLM. Идентификаторы совпадают с тем, что рендерит
фронтенд (PASSPORT_KEYS_V2, renderTechnologyV2, renderBlankAllowance).

specs/006-field-remarks-diff/research.md (R-04).
"""
from __future__ import annotations

import re

STAGE_PASSPORT = "passport"
STAGE_BLANK_ALLOWANCE = "blank_allowance"
STAGE_TECHNOLOGY = "technology"

# Тип документа совпадает с этапом согласования
_STAGE_TO_DOC = {
    "passport_review": STAGE_PASSPORT,
    "blank_allowance_review": STAGE_BLANK_ALLOWANCE,
    "technology_review": STAGE_TECHNOLOGY,
}

# Поля с фиксированными id → человекочитаемые label (RU)
PASSPORT_FIELDS: dict[str, str] = {
    "part_type": "Тип детали",
    "designation": "Обозначение",
    "overall_dimensions": "Габариты (макс)",
    "material_hardness": "Материал / твердость",
    "outer_geometry": "Наружный контур",
    "inner_geometry": "Внутренняя система",
    "special_elements": "Спец. элементы",
    "gdt": "ГДТ",
    "notes": "Примечания",
}

BLANK_ALLOWANCE_FIELDS: dict[str, str] = {
    "blank.source_stock": "Исходная заготовка (ленточно-отрезная)",
    "blank.pre_heat_treatment": "Черновая под термоулучшение",
    "blank.pre_finish_machining": "Предварительная токарная / под закалку",
    "allowances.summary": "Сводка припусков",
    "confirmation_required": "Требуется подтверждение",
}

# Скалярные (нетабличные) поля технологии v2
TECHNOLOGY_FIELDS: dict[str, str] = {
    "header.part_designation": "Обозначение",
    "header.part_name": "Тип детали",
    "header.material": "Материал",
    "header.features": "Особенности",
    "key_dimensions": "Ключевые размеры",
    "blank.type": "Тип заготовки",
    "blank.dimensions": "Размеры заготовки",
    "blank.allowances": "Припуски",
    "heat_treatment": "Термообработка",
    "finish_after_heat_treatment": "Чистовая после ТО",
    "confirmation_required": "Требуется подтверждение",
    "dimensions_control": "Контроль размеров",
}

# Атрибуты строки маршрута технологии (route[OPxx].<attr>)
TECHNOLOGY_ROUTE_ATTRS: dict[str, str] = {
    "equipment": "Оборудование",
    "transitions": "Переходы",
    "final_sizes": "Итоговые размеры",
}

# route[OP01].equipment / route[OP01].transitions / route[OP01].final_sizes
_ROUTE_FIELD_RE = re.compile(r"^route\[(?P<code>[^\]]+)\]\.(?P<attr>[a-z_]+)$")


def doc_type_for_stage(stage_or_status: str) -> str | None:
    """Тип документа для review-статуса или уже нормализованного этапа."""
    if stage_or_status in (STAGE_PASSPORT, STAGE_BLANK_ALLOWANCE, STAGE_TECHNOLOGY):
        return stage_or_status
    return _STAGE_TO_DOC.get(stage_or_status)


def field_label(doc_type: str, field: str) -> str | None:
    """Человекочитаемое имя поля по id (для diff)."""
    if doc_type == STAGE_PASSPORT:
        return PASSPORT_FIELDS.get(field)
    if doc_type == STAGE_BLANK_ALLOWANCE:
        return BLANK_ALLOWANCE_FIELDS.get(field)
    if doc_type == STAGE_TECHNOLOGY:
        if field in TECHNOLOGY_FIELDS:
            return TECHNOLOGY_FIELDS[field]
        m = _ROUTE_FIELD_RE.match(field)
        if m and m.group("attr") in TECHNOLOGY_ROUTE_ATTRS:
            return f"{m.group('code')}: {TECHNOLOGY_ROUTE_ATTRS[m.group('attr')]}"
    return None


def is_valid_field(doc_type: str, field: str) -> bool:
    """Принадлежит ли id поля множеству допустимых для типа документа (FR-015)."""
    if doc_type == STAGE_PASSPORT:
        return field in PASSPORT_FIELDS
    if doc_type == STAGE_BLANK_ALLOWANCE:
        return field in BLANK_ALLOWANCE_FIELDS
    if doc_type == STAGE_TECHNOLOGY:
        if field in TECHNOLOGY_FIELDS:
            return True
        m = _ROUTE_FIELD_RE.match(field)
        return bool(m and m.group("attr") in TECHNOLOGY_ROUTE_ATTRS)
    return False


def route_field(code: str, attr: str) -> str:
    """Собрать id ячейки маршрута: route[OP01].equipment (FR-015a)."""
    return f"route[{code}].{attr}"


def parse_route_field(field: str) -> tuple[str, str] | None:
    """(code, attr) для route[...]. поля, иначе None."""
    m = _ROUTE_FIELD_RE.match(field)
    if not m:
        return None
    return m.group("code"), m.group("attr")
