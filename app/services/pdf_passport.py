"""PDF паспорта детали (reportlab + шрифт с кириллицей)."""
import base64
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.schema_modules.passport import PASSPORT_FIELD_LABELS, PASSPORT_V2_FIELDS
from app.services.pdf_fonts import FONT, FONT_BOLD, ensure_pdf_fonts
from app.services.passport_normalize import normalize_passport

PASSPORT_LABELS_V1 = [
    ("designation", "Обозначение"),
    ("name", "Наименование"),
    ("material", "Материал"),
    ("dimensions", "Габариты"),
    ("mass", "Масса"),
    ("tolerances", "Допуски"),
    ("roughness", "Шероховатость"),
    ("heat_treatment", "ТО / термообработка"),
]


def _field_text(f: dict) -> str:
    if not f:
        return "—"
    if f.get("missing_on_drawing"):
        return "не указано на чертеже"
    return str(f.get("value") or "—")


def _draw_multiline(c, x: float, y: float, text: str, line_h: float = 5 * mm) -> float:
    for line in str(text).split("\n"):
        c.drawString(x, y, line[:95])
        y -= line_h
        if y < 30 * mm:
            c.showPage()
            y = A4[1] - 25 * mm
    return y


def build_passport_pdf(title: str, passport: dict) -> str:
    """Возвращает data:application/pdf;base64,..."""
    p = normalize_passport(passport)
    ensure_pdf_fonts()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    h = A4[1]
    y = h - 25 * mm

    c.setFont(FONT_BOLD, 16)
    c.drawString(25 * mm, y, "Паспорт детали")
    y -= 8 * mm
    c.setFont(FONT, 10)
    c.setFillColor(colors.grey)
    c.drawString(25 * mm, y, title or "")
    c.setFillColor(colors.black)
    y -= 12 * mm

    if p.get("schema_version") == "2.0" or p.get("part_type"):
        for key in PASSPORT_V2_FIELDS:
            label = PASSPORT_FIELD_LABELS[key]
            f = p.get(key) or {}
            c.setFont(FONT_BOLD, 9)
            c.drawString(25 * mm, y, label + ":")
            y -= 6 * mm
            c.setFont(FONT, 9)
            y = _draw_multiline(c, 28 * mm, y, _field_text(f))
            y -= 3 * mm
    else:
        for key, label in PASSPORT_LABELS_V1:
            f = p.get(key) or {}
            c.setFont(FONT_BOLD, 9)
            c.drawString(25 * mm, y, label + ":")
            c.setFont(FONT, 9)
            c.drawString(70 * mm, y, _field_text(f)[:80])
            y -= 7 * mm
            if y < 30 * mm:
                c.showPage()
                y = h - 25 * mm

    notes = p.get("notes")
    if notes:
        y -= 4 * mm
        c.setFont(FONT_BOLD, 9)
        c.drawString(25 * mm, y, "Примечания:")
        y -= 6 * mm
        c.setFont(FONT, 9)
        y = _draw_multiline(c, 28 * mm, y, str(notes))

    c.save()
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:application/pdf;base64,{b64}"
