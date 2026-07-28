"""Регистрация TTF-шрифтов с кириллицей для reportlab."""
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT = "AppSans"
FONT_BOLD = "AppSans-Bold"
_registered = False


def _find_font_files() -> tuple[Path, Path] | None:
    pairs = [
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
        (
            Path(__file__).resolve().parents[1] / "assets" / "fonts" / "DejaVuSans.ttf",
            Path(__file__).resolve().parents[1] / "assets" / "fonts" / "DejaVuSans-Bold.ttf",
        ),
        (
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
        ),
    ]
    for reg, bold in pairs:
        if reg.is_file() and bold.is_file():
            return reg, bold
    return None


def ensure_pdf_fonts() -> None:
    global _registered
    if _registered:
        return
    found = _find_font_files()
    if not found:
        raise RuntimeError("Нет шрифта с кириллицей для PDF (DejaVu или Arial)")
    reg, bold = found
    pdfmetrics.registerFont(TTFont(FONT, str(reg)))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))
    _registered = True
