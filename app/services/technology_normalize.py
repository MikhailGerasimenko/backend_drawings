"""Нормализация ответа LLM к технологической карте v2.0."""
import re
from datetime import date

from app.schemas.technology import (
    ManufacturingTechnology,
    TechnologyBlank,
    TechnologyCardV2,
    TechnologyHeader,
    TechnologyMetadata,
    TechnologyOperation,
    TechnologyRouteStep,
)
from app.services.passport_normalize import passport_field_text


def _s(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _route_from_v1_operations(ops: list) -> list[TechnologyRouteStep]:
    steps: list[TechnologyRouteStep] = []
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            continue
        num = int(op.get("number") or i + 1)
        code = _s(op.get("code")) or f"OP{num:02d}"
        steps.append(
            TechnologyRouteStep(
                code=code,
                number=num,
                name=_s(op.get("name")) or f"Операция {num}",
                equipment=op.get("equipment") or None,
                transitions=_s(op.get("transitions") or op.get("description")),
                final_sizes=_s(op.get("final_sizes")),
            )
        )
    return steps


def _upgrade_v1_to_v2(raw: dict) -> dict:
    ops = raw.get("operations") or []
    route = _route_from_v1_operations(ops)
    if not route:
        route = [
            TechnologyRouteStep(
                code="OP01",
                number=1,
                name="Технология",
                transitions=_s(raw.get("summary")),
            )
        ]
    card = TechnologyCardV2(
        header=TechnologyHeader(
            part_designation=_s(raw.get("part_designation")),
            part_name=_s(raw.get("part_name")),
            material=_s(raw.get("material")),
        ),
        key_dimensions=_s(raw.get("summary")),
        route=route,
    )
    return card.to_store()


def _fill_header_from_passport(header: TechnologyHeader, passport: dict | None) -> None:
    if not passport:
        return
    if not header.part_designation:
        header.part_designation = passport_field_text(passport, "designation") or "—"
    if not header.part_name:
        header.part_name = passport_field_text(passport, "part_type")
    if not header.material:
        header.material = passport_field_text(passport, "material_hardness")


def _parse_route_raw(raw: dict) -> list[TechnologyRouteStep]:
    """route | operations | маршрут."""
    route_raw = raw.get("route") or raw.get("operations") or raw.get("маршрут")
    if not isinstance(route_raw, list):
        return []
    return _route_from_v1_operations(route_raw)


def _parse_blank(raw: dict) -> TechnologyBlank:
    b = raw.get("blank") or raw.get("заготовка") or {}
    if isinstance(b, str):
        return TechnologyBlank(type=b)
    if not isinstance(b, dict):
        return TechnologyBlank()
    return TechnologyBlank(
        type=_s(b.get("type") or b.get("тип")),
        dimensions=_s(b.get("dimensions") or b.get("размеры")),
        allowances=_s(b.get("allowances") or b.get("припуски")),
    )


def _parse_header(raw: dict, passport: dict | None) -> TechnologyHeader:
    h = raw.get("header") or raw.get("заголовок") or {}
    if not isinstance(h, dict):
        h = {}
    header = TechnologyHeader(
        part_designation=_s(h.get("part_designation") or h.get("обозначение") or raw.get("part_designation")),
        part_name=_s(h.get("part_name") or h.get("наименование") or raw.get("part_name")),
        material=_s(h.get("material") or h.get("материал") or raw.get("material")),
        features=_s(h.get("features") or h.get("особенности")),
    )
    _fill_header_from_passport(header, passport)
    return header


def _parse_metadata(raw: dict) -> TechnologyMetadata:
    m = raw.get("metadata") or raw.get("метаданные") or {}
    if not isinstance(m, dict):
        m = {}
    files = m.get("files_used") or m.get("файлы") or []
    if isinstance(files, str):
        files = [files]
    if not isinstance(files, list):
        files = []
    return TechnologyMetadata(
        card_version=_s(m.get("card_version") or m.get("версия")) or "draft v1.0",
        author=_s(m.get("author") or m.get("автор")) or "ИИ-ассистент",
        date=_s(m.get("date") or m.get("дата")) or date.today().isoformat(),
        files_used=[_s(x) for x in files if _s(x)],
        allowance_rule_version=_s(m.get("allowance_rule_version")) or "v1.1",
    )


def technology_to_markdown(tj: dict) -> str:
    """Текст для PDF из карты v2.0 (или v1)."""
    if str(tj.get("schema_version")) != "2.0":
        return _markdown_v1(tj)

    lines: list[str] = []
    h = tj.get("header") or {}
    lines.append("1. ЗАГОЛОВОК")
    if h.get("part_designation"):
        lines.append(f"Обозначение: {h['part_designation']}")
    if h.get("part_name"):
        lines.append(f"Деталь: {h['part_name']}")
    if h.get("material"):
        lines.append(f"Материал: {h['material']}")
    if h.get("features"):
        lines.append(f"Особенности: {h['features']}")
    lines.append("")

    if tj.get("key_dimensions"):
        lines.append("2. КЛЮЧЕВЫЕ РАЗМЕРЫ")
        lines.append(str(tj["key_dimensions"]))
        lines.append("")

    blank = tj.get("blank") or {}
    if any(blank.get(k) for k in ("type", "dimensions", "allowances")):
        lines.append("3. ЗАГОТОВКА")
        if blank.get("type"):
            lines.append(f"Тип: {blank['type']}")
        if blank.get("dimensions"):
            lines.append(f"Размеры: {blank['dimensions']}")
        if blank.get("allowances"):
            lines.append(f"Припуски: {blank['allowances']}")
        lines.append("")

    lines.append("4. МАРШРУТ")
    for step in tj.get("route") or []:
        code = step.get("code") or ""
        name = step.get("name") or ""
        lines.append(f"{code}: {name}".strip(": "))
        if step.get("equipment"):
            lines.append(f"  Оборудование: {step['equipment']}")
        if step.get("transitions"):
            lines.append(f"  Переходы: {step['transitions']}")
        if step.get("final_sizes"):
            lines.append(f"  Итог: {step['final_sizes']}")
        lines.append("")

    for key, title in (
        ("heat_treatment", "5. ТЕРМООБРАБОТКА"),
        ("finish_after_heat_treatment", "6. ЧИСТОВАЯ ПОСЛЕ ТО"),
        ("confirmation_required", "7. ТРЕБУЕТСЯ ПОДТВЕРЖДЕНИЕ"),
        ("dimensions_control", "8. КОНТРОЛЬ РАЗМЕРОВ"),
        ("fields_needing_clarification", "Поля, требующие уточнения"),
        ("conflicts", "Конфликты"),
    ):
        if tj.get(key):
            lines.append(title)
            lines.append(str(tj[key]))
            lines.append("")

    meta = tj.get("metadata") or {}
    if meta:
        lines.append("МЕТАДАННЫЕ")
        lines.append(f"Версия: {meta.get('card_version', '')}")
        lines.append(f"author: {meta.get('author', '')}, date: {meta.get('date', '')}")
    return "\n".join(lines).strip() or "Технология изготовления"


def _markdown_v1(tj: dict) -> str:
    lines: list[str] = []
    if tj.get("summary"):
        lines.append(str(tj["summary"]))
    des = tj.get("part_designation") or ""
    pname = tj.get("part_name") or ""
    if des or pname:
        lines.append(f"Деталь: {des} {pname}".strip())
    if tj.get("material"):
        lines.append(f"Материал: {tj['material']}")
    lines.append("")
    for op in tj.get("operations") or []:
        lines.append(f"{op.get('number', '')}. {op.get('name', '')}")
        if op.get("description"):
            lines.append(str(op["description"]))
        lines.append("")
    return "\n".join(lines).strip() or "Технология изготовления"


def _unwrap_llm_card(raw: dict) -> dict:
    """Ответ LLM иногда повторяет формат артефакта истории: {json, text}."""
    inner = raw.get("json")
    if isinstance(inner, dict) and (
        inner.get("route") or str(inner.get("schema_version") or "") == "2.0"
    ):
        return inner
    return raw


def normalize_technology(raw: dict | None, passport: dict | None) -> tuple[str, dict]:
    """Приводит ответ LLM к technology v2.0."""
    if not raw:
        return mock_technology(passport)

    raw = _unwrap_llm_card(raw)

    ver = str(raw.get("schema_version") or "")
    if ver == "1.0" or (raw.get("operations") and not raw.get("route")):
        raw = _upgrade_v1_to_v2(raw)

    route = _parse_route_raw(raw)
    if not route:
        # Текст в одном поле body / markdown — попытка разобрать OP из текста
        blob = _s(raw.get("body") or raw.get("markdown") or raw.get("text"))
        if blob:
            route = _route_from_text_blob(blob)
    if not route:
        raise ValueError("В ответе нет операций маршрута (route)")

    card = TechnologyCardV2(
        header=_parse_header(raw, passport),
        key_dimensions=_s(
            raw.get("key_dimensions") or raw.get("ключевые_размеры") or raw.get("summary")
        ),
        blank=_parse_blank(raw),
        route=route,
        heat_treatment=_s(raw.get("heat_treatment") or raw.get("термообработка")),
        finish_after_heat_treatment=_s(
            raw.get("finish_after_heat_treatment")
            or raw.get("чистовая_после_то")
        ),
        confirmation_required=_s(
            raw.get("confirmation_required") or raw.get("требуется_подтверждение")
        ),
        metadata=_parse_metadata(raw),
        dimensions_control=_s(
            raw.get("dimensions_control") or raw.get("контроль_размеров")
        ),
        fields_needing_clarification=_s(
            raw.get("fields_needing_clarification") or raw.get("уточнения")
        ),
        conflicts=_s(raw.get("conflicts") or raw.get("конфликты")),
    )
    tj = card.to_store()
    md = technology_to_markdown(tj)
    return md, tj


def _route_from_text_blob(text: str) -> list[TechnologyRouteStep]:
    pat = re.compile(r"(?:^|\n)\s*(?:\*\*)?(OP\d{2,})[:\s\*—\-]*", re.I | re.M)
    matches = list(pat.finditer(text))
    if len(matches) < 1:
        return []
    steps: list[TechnologyRouteStep] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        code = m.group(1).upper()
        num = int(re.sub(r"\D", "", code) or i + 1)
        lines = chunk.split("\n", 1)
        name = lines[0].strip().strip("*")[:200] or code
        rest = lines[1].strip() if len(lines) > 1 else ""
        steps.append(
            TechnologyRouteStep(
                code=code,
                number=num,
                name=name,
                transitions=rest[:4000],
            )
        )
    return steps


def _mock_route_from_selected(selected: list[dict]) -> list[TechnologyRouteStep]:
    """Маршрут демо только из выбранных пользователем операций."""
    steps: list[TechnologyRouteStep] = []
    for i, item in enumerate(selected):
        num = (i + 1) * 10
        steps.append(
            TechnologyRouteStep(
                code=f"OP{num:02d}",
                number=num,
                name=_s(item.get("operation")) or f"Операция {num}",
                equipment=_s(item.get("equipment")) or "—",
                transitions="По чертежу (демо)",
                final_sizes="—",
            )
        )
    return steps


def mock_technology(
    passport: dict | None,
    selected_operations: list[dict] | None = None,
) -> tuple[str, dict]:
    des = passport_field_text(passport, "designation") or "Деталь-001"
    name = passport_field_text(passport, "part_type") or "Корпус"
    material = passport_field_text(passport, "material_hardness") or "Сталь 45"
    selected = selected_operations or []
    if selected:
        route = _mock_route_from_selected(selected)
    else:
        route = [
            TechnologyRouteStep(
                code="OP01",
                number=1,
                name="Ленточно-отрезная",
                equipment="ARG330",
                transitions="Отрезать заготовку",
                final_sizes="Заготовка Ø125 × 90",
            ),
            TechnologyRouteStep(
                code="OP10",
                number=10,
                name="Токарная черновая",
                equipment="16К20",
                transitions="Точение Ø120 h11",
                final_sizes="Ø120 h11 × 85",
            ),
            TechnologyRouteStep(
                code="OP70",
                number=70,
                name="Контроль размеров",
                equipment="вручную",
                transitions="Измерение размеров",
                final_sizes="По чертежу",
            ),
        ]
    card = TechnologyCardV2(
        header=TechnologyHeader(
            part_designation=des,
            part_name=name,
            material=material,
            features="Демо без API-ключа",
        ),
        key_dimensions="Ø120 × 85 мм, Ra 1.6",
        blank=TechnologyBlank(
            type="Пруток круглый",
            dimensions="Ø125 × 90 мм",
            allowances="5 мм на диаметр и длину",
        ),
        route=route,
        heat_treatment="Закалка CHO (демо)",
        finish_after_heat_treatment="Круглошлифовальная 3М151 или токарная ЧПУ",
        confirmation_required="—",
        metadata=TechnologyMetadata(
            card_version="draft v1.0",
            date=date.today().isoformat(),
        ),
        dimensions_control="Size_start → Size_final (демо)",
    )
    tj = card.to_store()
    return technology_to_markdown(tj), tj


def validate_technology_store(tj: dict) -> None:
    """Проверка перед сохранением / согласованием."""
    ver = str(tj.get("schema_version") or "")
    if ver == "2.0":
        TechnologyCardV2.model_validate(tj)
    else:
        ManufacturingTechnology.model_validate(tj)
