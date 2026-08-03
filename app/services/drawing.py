"""Загрузка чертежа: MIME, размер, preview data URL."""
import base64

import fitz
from fastapi import UploadFile

from app.core.exceptions import AppError

# Макс. сторона растра превью (первая страница PDF → PNG, как у загруженных PNG/JPEG)
PREVIEW_MAX_PX = 1600

# FR: PNG/JPEG/PDF/DXF, до 20 МБ
ALLOWED_MIME = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "application/pdf",
        "application/dxf",
    }
)
MAX_BYTES = 20 * 1024 * 1024


def can_replace_drawing(status: str, drawing_sent_at) -> bool:
    """FR-025/026: замена только до первой отправки на анализ."""
    return drawing_sent_at is None and status in ("draft_upload", "ready_to_send")


async def read_and_validate_upload(file: UploadFile) -> tuple[bytes, str]:
    if not file or not file.filename:
        raise AppError("VALIDATION_ERROR", "Файл не передан", 400)

    raw = await file.read()
    if not raw:
        raise AppError("VALIDATION_ERROR", "Файл пустой", 400)
    if len(raw) > MAX_BYTES:
        raise AppError("FILE_TOO_LARGE", "Файл больше 20 МБ", 413)

    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in ALLOWED_MIME:
        # по расширению, если браузер не прислал MIME
        name = file.filename.lower()
        if name.endswith(".pdf"):
            mime = "application/pdf"
        elif name.endswith(".png"):
            mime = "image/png"
        elif name.endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        elif name.endswith(".dxf"):
            mime = "application/dxf"
        else:
            raise AppError("UNSUPPORTED_MEDIA", "Допустимы PNG, JPEG, PDF, DXF", 415)

    return raw, mime


def _pdf_first_page_png(raw: bytes) -> bytes:
    """Первая страница PDF в PNG для превью в UI и image_url VLM."""
    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception as exc:
        raise AppError("VALIDATION_ERROR", "Некорректный PDF", 400) from exc
    try:
        if doc.page_count < 1:
            raise AppError("VALIDATION_ERROR", "PDF без страниц", 400)
        page = doc[0]
        w, h = page.rect.width, page.rect.height
        scale = min(1.0, PREVIEW_MAX_PX / max(w, h, 1.0))
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


async def dxf_to_preview_url(dxf_bytes: bytes) -> tuple[str, str]:
    """DXF → (data:image/png;base64,…, llm_context) через DXF Converter."""
    from app.services import dxf_converter_client

    png_bytes, llm_context = await dxf_converter_client.convert_with_preview(dxf_bytes)
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}", llm_context


def to_preview_url(raw: bytes, mime: str) -> str:
    """Синхронный путь для PNG/JPEG/PDF. DXF требует async — используй dxf_to_preview_url."""
    if mime == "application/pdf":
        png = _pdf_first_page_png(raw)
        b64 = base64.b64encode(png).decode("ascii")
        return f"data:image/png;base64,{b64}"
    if mime == "application/dxf":
        raise AppError(
            "INTERNAL_ERROR",
            "DXF preview требует async вызова dxf_to_preview_url()",
            500,
        )
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def resolve_preview_url(
    preview_url: str | None,
    drawing_b64: str | None,
    drawing_mime: str | None,
) -> str | None:
    """Старые сессии: в БД мог остаться data:application/pdf — отдаём PNG на лету."""
    if not preview_url:
        return None
    if not preview_url.startswith("data:application/pdf"):
        return preview_url
    if drawing_mime != "application/pdf" or not drawing_b64:
        return preview_url
    try:
        raw = base64.b64decode(drawing_b64)
        return to_preview_url(raw, "application/pdf")
    except AppError:
        return preview_url
