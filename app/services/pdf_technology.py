"""PDF технологии изготовления."""
import base64
import io
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.services.pdf_fonts import FONT, FONT_BOLD, ensure_pdf_fonts


def build_technology_pdf(title: str, technology_text: str) -> str:
    ensure_pdf_fonts()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    h = A4[1]
    y = h - 25 * mm

    c.setFont(FONT_BOLD, 16)
    c.drawString(25 * mm, y, "Технология изготовления")
    y -= 8 * mm
    c.setFont(FONT, 10)
    c.setFillColor(colors.grey)
    c.drawString(25 * mm, y, title or "")
    c.setFillColor(colors.black)
    y -= 12 * mm

    for line in (technology_text or "Нет данных").split("\n"):
        if y < 30 * mm:
            c.showPage()
            y = h - 25 * mm
        header = re.match(r"^#+\s+(.+)", line.strip())
        if header:
            c.setFont(FONT_BOLD, 11)
            c.drawString(25 * mm, y, header.group(1)[:90])
            y -= 7 * mm
            continue
        num = re.match(r"^(\d+)\.\s+(.+)", line.strip())
        if num:
            c.setFont(FONT_BOLD, 10)
            c.drawString(25 * mm, y, f"{num.group(1)}. {num.group(2)[:80]}")
            y -= 6 * mm
            continue
        if line.strip():
            c.setFont(FONT, 9)
            c.drawString(28 * mm, y, line.strip()[:95])
            y -= 5 * mm

    c.save()
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:application/pdf;base64,{b64}"
