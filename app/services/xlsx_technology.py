"""Выгрузка технологии изготовления в Excel (маршрутная + технологическая карта).

Шаблон — производственная форма (как в образце 07-54-319.xlsx): листы МК и ТК
в альбомной ориентации A4, с шапкой, маршрутом операций и переходами.
"""
from __future__ import annotations

import base64
import io
import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.worksheet.worksheet import Worksheet

from app.services.passport_normalize import passport_field_text
from app.services.technology_normalize import normalize_technology

TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "assets"
    / "templates"
    / "technology_card.xlsx"
)

# Слоты операций на маршрутной карте (№ в колонке B, имя в D).
_MK1_SLOTS = (17, 21, 24, 27, 30, 33, 36, 39)  # лист 001, по 3 строки
_MK2_SLOTS = (8, 11, 14, 17, 20, 23, 26, 29, 32)  # лист 002 до блока «Мастер»

_HRC_RE = re.compile(
    r"(HRC\s*[\d.,]+(?:\s*(?:\.\.\.|…|-|–|—)\s*[\d.,]+)?)",
    re.IGNORECASE,
)
_NBSP = "\xa0"


def _s(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _norm_diameter(text: str) -> str:
    """Привести обозначения диаметра к виду шаблона (‡)."""
    if not text:
        return text
    for ch in ("Ø", "⌀", "ø", "φ", "Ф"):
        text = text.replace(ch, "‡")
    return text


def _material_without_hrc(material: str) -> str:
    """В шапке МК материал без блока HRC (твёрдость в отдельной ячейке)."""
    if not material:
        return ""
    cleaned = _HRC_RE.sub("", material)
    cleaned = re.sub(r"[,;]\s*$", "", cleaned.strip())
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;")
    return cleaned


def _extract_hardness(*parts: str) -> str:
    for part in parts:
        if not part:
            continue
        m = _HRC_RE.search(part)
        if m:
            h = m.group(1).upper().replace("…", "...").replace("–", "...")
            h = h.replace("—", "...").replace("-", "...")
            h = re.sub(r"\s+", " ", h)
            # HRC 48...52
            h = re.sub(r"HRC\s*", "HRC ", h, flags=re.IGNORECASE)
            return h
    return ""


def _split_name(name: str, max_first: int = 22) -> tuple[str, str]:
    """Разбить длинное имя операции на 1–2 строки как в образце."""
    name = _s(name)
    if not name:
        return "", ""
    if len(name) <= max_first:
        return name, ""
    # Предпочитаем разрыв по пробелу/дефису
    cut = name.rfind(" ", 0, max_first + 1)
    if cut < 8:
        cut = name.rfind("-", 0, max_first + 1)
    if cut < 8:
        cut = max_first
    return name[:cut].rstrip("- "), name[cut:].lstrip("- ")


def _wrap_line(text: str, width: int = 95) -> list[str]:
    text = _s(text)
    if not text:
        return []
    out: list[str] = []
    for para in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        para = para.strip()
        if not para:
            continue
        while len(para) > width:
            cut = para.rfind(" ", 0, width + 1)
            if cut < width // 3:
                cut = width
            out.append(para[:cut].rstrip())
            para = para[cut:].lstrip()
        if para:
            out.append(para)
    return out


def _set(ws: Worksheet, row: int, col: int, value: Any) -> None:
    cell = ws.cell(row, col)
    # openpyxl: писать можно только в верхний левый угол merge
    if isinstance(cell, MergedCell):
        for merged in ws.merged_cells.ranges:
            if cell.coordinate in merged:
                cell = ws.cell(merged.min_row, merged.min_col)
                break
    cell.value = value if value not in ("", None) else None

def _clear_mk_slots(ws: Worksheet, slots: tuple[int, ...], span: int = 3) -> None:
    for start in slots:
        for r in range(start, start + span):
            for col in (2, 4, 11, 15):
                _set(ws, r, col, None)


def _clear_tk_body(ws: Worksheet, start_row: int, end_row: int) -> None:
    for r in range(start_row, end_row + 1):
        for col in (2, 3, 5, 14):  # B, C, E, N
            _set(ws, r, col, None)

def _route_steps(tj: dict) -> list[dict]:
    route = tj.get("route") or []
    steps: list[dict] = []
    for i, step in enumerate(route):
        if not isinstance(step, dict):
            continue
        num = step.get("number")
        try:
            num_i = int(num) if num is not None else i + 1
        except (TypeError, ValueError):
            num_i = i + 1
        name = _s(step.get("name")) or f"Операция {num_i}"
        steps.append(
            {
                "number": num_i,
                "name": name,
                "equipment": _s(step.get("equipment")),
                "transitions": _s(step.get("transitions")),
                "final_sizes": _s(step.get("final_sizes")),
            }
        )
    return steps


def _fill_mk_header(
    ws: Worksheet,
    *,
    designation: str,
    part_name: str,
    material: str,
    blank_dims: str,
    blank_weight: str,
    finish_weight: str,
    hardness: str,
) -> None:
    _set(ws, 6, 4, part_name or None)  # D6 Деталь
    _set(ws, 9, 6, _norm_diameter(blank_dims) or None)  # F9 размер заготовки
    _set(ws, 9, 10, blank_weight or None)  # J9 вес заготовки
    _set(ws, 9, 12, finish_weight or None)  # L9 чистовой вес
    _set(ws, 9, 15, hardness or None)  # O9 твердость
    _set(ws, 10, 2, designation or None)  # B10 № чертежа
    _set(ws, 10, 4, material or None)  # D10 материал


def _fill_mk_ops(
    ws: Worksheet, slots: tuple[int, ...], steps: list[dict], nh_col: int
) -> None:
    for start, step in zip(slots, steps):
        _set(ws, start, 2, step["number"])
        line1, line2 = _split_name(step["name"])
        _set(ws, start, 4, line1)
        if line2:
            _set(ws, start + 1, 4, line2)
        _set(ws, start, nh_col, _NBSP)


def _fill_tk_header(
    ws: Worksheet,
    *,
    designation: str,
    part_name: str,
    blank_type: str,
    material: str,
    blank_dims: str,
    qty: str,
    blank_weight: str,
    piece_weight: str,
    sheet_no: int,
    sheets_total: int,
) -> None:
    _set(ws, 2, 9, designation or None)  # I2
    _set(ws, 3, 9, part_name or None)  # I3
    _set(ws, 4, 15, sheet_no)  # O4 Лист
    _set(ws, 5, 15, sheets_total)  # O5 Листов
    _set(ws, 6, 2, blank_type or None)
    _set(ws, 6, 5, material or None)
    _set(ws, 6, 6, _norm_diameter(blank_dims) or None)
    _set(ws, 6, 11, qty or None)
    _set(ws, 6, 12, blank_weight or None)
    _set(ws, 6, 13, piece_weight or None)


def _fill_tk_cont_header(
    ws: Worksheet,
    *,
    designation: str,
    part_name: str,
    sheet_no: int,
    sheets_total: int,
) -> None:
    _set(ws, 2, 4, designation or None)  # D2
    _set(ws, 2, 6, sheet_no)  # F2 Лист
    _set(ws, 3, 4, part_name or None)  # D3
    _set(ws, 3, 6, sheets_total)  # F3 Листов


def _tk_lines_for_steps(steps: list[dict]) -> list[tuple[str | None, str, str | None]]:
    """Строки ТК: (номер|None, текст, оборудование|None)."""
    lines: list[tuple[str | None, str, str | None]] = []
    for step in steps:
        lines.append((str(step["number"]), step["name"], step["equipment"] or None))
        body_parts: list[str] = []
        if step["transitions"]:
            body_parts.extend(_wrap_line(step["transitions"], 100))
        if step["final_sizes"]:
            body_parts.extend(
                _wrap_line(f"Итоговые размеры: {step['final_sizes']}", 100)
            )
        for t in body_parts:
            lines.append((None, _norm_diameter(t), None))
    return lines


def _write_tk_page(
    ws: Worksheet,
    lines: list[tuple[str | None, str, str | None]],
    *,
    start_row: int,
    end_row: int,
    num_col: int,
    text_col: int,
    eq_col: int,
) -> list[tuple[str | None, str, str | None]]:
    """Записать строки в диапазон; вернуть остаток."""
    row = start_row
    idx = 0
    while idx < len(lines) and row <= end_row:
        num, text, eq = lines[idx]
        if num is not None:
            _set(ws, row, num_col, num)
        _set(ws, row, text_col, text)
        if eq:
            _set(ws, row, eq_col, eq)
        idx += 1
        row += 1
    return lines[idx:]


def _clone_sheet_style(src: Worksheet, dst: Worksheet) -> None:
    """Копировать ширины колонок и высоты строк."""
    for letter, dim in src.column_dimensions.items():
        dst.column_dimensions[letter].width = dim.width
    for idx, dim in src.row_dimensions.items():
        if dim.height is not None:
            dst.row_dimensions[idx].height = dim.height
    dst.page_setup.orientation = src.page_setup.orientation
    dst.page_setup.paperSize = src.page_setup.paperSize
    dst.page_margins.left = src.page_margins.left
    dst.page_margins.right = src.page_margins.right
    dst.page_margins.top = src.page_margins.top
    dst.page_margins.bottom = src.page_margins.bottom
    dst.sheet_format.defaultRowHeight = src.sheet_format.defaultRowHeight


def _append_tk_overflow_sheet(
    wb,
    template_ws: Worksheet,
    *,
    designation: str,
    part_name: str,
    sheet_no: int,
    sheets_total: int,
    lines: list[tuple[str | None, str, str | None]],
) -> list[tuple[str | None, str, str | None]]:
    """Создать дополнительный лист продолжения ТК по образцу листа 004.

    sheet_no — номер «Лист N» в шапке (3, 4, …);
    имя листа книги — 005, 006, … (001–004 заняты шаблоном).
    """
    wb_name = f"{sheet_no + 2:03d}"
    while wb_name in wb.sheetnames:
        # защита от коллизий имён
        n = int(wb_name) + 1
        wb_name = f"{n:03d}"
    ws = wb.copy_worksheet(template_ws)
    ws.title = wb_name
    _clone_sheet_style(template_ws, ws)
    _fill_tk_cont_header(
        ws,
        designation=designation,
        part_name=part_name,
        sheet_no=sheet_no,
        sheets_total=sheets_total,
    )
    _clear_tk_body(ws, 5, 36)
    return _write_tk_page(
        ws,
        lines,
        start_row=5,
        end_row=36,
        num_col=2,
        text_col=3,
        eq_col=5,
    )
def build_technology_xlsx(
    title: str,
    technology_json: dict | None,
    passport: dict | None = None,
    technology_text: str | None = None,
) -> str:
    """Собрать .xlsx и вернуть data:application/...;base64,..."""
    if technology_json:
        _, tj = normalize_technology(technology_json, passport)
    else:
        # fallback: одна операция из текста
        tj = {
            "schema_version": "2.0",
            "header": {
                "part_designation": title or "",
                "part_name": "",
                "material": "",
            },
            "blank": {},
            "route": [
                {
                    "number": 1,
                    "name": "Технология",
                    "transitions": technology_text or "Нет данных",
                    "equipment": "",
                    "final_sizes": "",
                }
            ],
            "metadata": {},
            "heat_treatment": "",
            "key_dimensions": "",
        }

    header = tj.get("header") or {}
    blank = tj.get("blank") or {}
    meta = tj.get("metadata") or {}
    steps = _route_steps(tj)
    if not steps:
        steps = [
            {
                "number": 1,
                "name": "Технология",
                "equipment": "",
                "transitions": technology_text or "Нет данных",
                "final_sizes": "",
            }
        ]

    designation = _s(header.get("part_designation")) or _s(title)
    part_name = _s(header.get("part_name"))
    material = _s(header.get("material"))
    material_mk = _material_without_hrc(material) or material
    blank_type = _s(blank.get("type"))
    blank_dims = _s(blank.get("dimensions"))
    if blank.get("allowances") and blank_dims:
        # в образце размер и кол-во в одной ячейке: ‡80х36/1шт
        pass
    hardness = _extract_hardness(
        material,
        _s(tj.get("heat_treatment")),
        _s(tj.get("key_dimensions")),
        passport_field_text(passport, "material_hardness"),
    )
    finish_weight = passport_field_text(passport, "mass")
    blank_weight = ""
    piece_weight = finish_weight
    qty = "1"
    if blank_dims and "/" not in blank_dims:
        blank_dims_mk = f"{blank_dims}/1шт" if blank_dims else ""
    else:
        blank_dims_mk = blank_dims

    author = _s(meta.get("author")) or "ИИ-ассистент"
    tech_date = _s(meta.get("date"))

    if not TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f"Шаблон не найден: {TEMPLATE_PATH}")

    wb = load_workbook(TEMPLATE_PATH)
    ws_mk1 = wb["001"]
    ws_mk2 = wb["002"]
    ws_tk1 = wb["003"]
    ws_tk2 = wb["004"]

    # --- Маршрутная карта ---
    _clear_mk_slots(ws_mk1, _MK1_SLOTS, span=3)
    # на листе 002 слоты по 3 строки; очищаем B/D/K
    for start in _MK2_SLOTS:
        for r in range(start, start + 3):
            for col in (2, 4, 11):
                _set(ws_mk2, r, col, None)
    _fill_mk_header(
        ws_mk1,
        designation=designation,
        part_name=part_name,
        material=material_mk,
        blank_dims=blank_dims_mk,
        blank_weight=blank_weight,
        finish_weight=finish_weight,
        hardness=hardness,
    )

    mk1_count = len(_MK1_SLOTS)
    _fill_mk_ops(ws_mk1, _MK1_SLOTS, steps[:mk1_count], nh_col=15)
    rest_mk = steps[mk1_count:]
    _fill_mk_ops(ws_mk2, _MK2_SLOTS, rest_mk[: len(_MK2_SLOTS)], nh_col=11)
    overflow_mk = rest_mk[len(_MK2_SLOTS) :]
    if overflow_mk:
        # Добавляем операции сверх ёмкости в конец листа 002 текстом
        note_row = 35
        names = "; ".join(
            f"{s['number']}. {s['name']}" for s in overflow_mk
        )
        _set(ws_mk2, note_row, 4, f"Также: {names}"[:200])

    # --- Технологическая карта: сначала считаем листы ---
    extra_notes: list[str] = []
    for label, key in (
        ("Термообработка", "heat_treatment"),
        ("Чистовая после ТО", "finish_after_heat_treatment"),
        ("Контроль размеров", "dimensions_control"),
        ("Требуется подтверждение", "confirmation_required"),
        ("Конфликты", "conflicts"),
    ):
        val = _s(tj.get(key))
        if val:
            extra_notes.append(f"{label}: {val}")

    tk_lines = _tk_lines_for_steps(steps)
    for note in extra_notes:
        for wrapped in _wrap_line(note, 100):
            tk_lines.append((None, _norm_diameter(wrapped), None))

    # ёмкость: 003 rows 9-34 (26) + 004 rows 5-36 (32) + доп. листы по 32
    cap1, cap2 = 26, 32
    remaining_after_two = max(0, len(tk_lines) - cap1 - cap2)
    extra_sheets = (
        (remaining_after_two + cap2 - 1) // cap2 if remaining_after_two else 0
    )
    sheets_total = 2 + extra_sheets

    _fill_tk_header(
        ws_tk1,
        designation=designation,
        part_name=part_name,
        blank_type=blank_type,
        material=material_mk,
        blank_dims=blank_dims,
        qty=qty,
        blank_weight=blank_weight or piece_weight,
        piece_weight=piece_weight,
        sheet_no=1,
        sheets_total=sheets_total,
    )
    _clear_tk_body(ws_tk1, 9, 34)
    rest = _write_tk_page(
        ws_tk1,
        tk_lines,
        start_row=9,
        end_row=34,
        num_col=2,
        text_col=3,
        eq_col=14,
    )

    # подпись технолога
    _set(ws_tk1, 35, 4, author)
    if tech_date:
        _set(ws_tk1, 35, 10, tech_date)

    _fill_tk_cont_header(
        ws_tk2,
        designation=designation,
        part_name=part_name,
        sheet_no=2,
        sheets_total=sheets_total,
    )
    _clear_tk_body(ws_tk2, 5, 36)
    rest = _write_tk_page(
        ws_tk2,
        rest,
        start_row=5,
        end_row=36,
        num_col=2,
        text_col=3,
        eq_col=5,
    )

    sheet_no = 3
    while rest:
        rest = _append_tk_overflow_sheet(
            wb,
            ws_tk2,
            designation=designation,
            part_name=part_name,
            sheet_no=sheet_no,
            sheets_total=sheets_total,
            lines=rest,
        )
        sheet_no += 1

    buf = io.BytesIO()
    wb.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return (
        "data:application/vnd.openxmlformats-officedocument"
        ".spreadsheetml.sheet;base64," + b64
    )
