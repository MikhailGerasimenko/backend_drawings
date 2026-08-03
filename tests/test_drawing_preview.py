"""Превью чертежа: PDF растеризуется в PNG для UI и VLM."""
from io import BytesIO

from reportlab.pdfgen import canvas

from app.services.drawing import to_preview_url


def _tiny_pdf() -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(200, 200))
    c.drawString(50, 100, "test")
    c.save()
    return buf.getvalue()


def test_pdf_preview_is_png_data_url():
    url = to_preview_url(_tiny_pdf(), "application/pdf")
    assert url.startswith("data:image/png;base64,")


def test_image_preview_unchanged():
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    url = to_preview_url(png, "image/png")
    assert url.startswith("data:image/png;base64,")
