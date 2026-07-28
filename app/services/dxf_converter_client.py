"""HTTP-клиент DXF Converter с retry (3×, экспоненциальные задержки 0.5/1/2 с)."""
import asyncio
import logging

import httpx

from app.core.config import settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

_RETRY_DELAYS = (0.5, 1.0, 2.0)


async def _post_convert(dxf_bytes: bytes, *, render_png: bool) -> dict:
    """POST /v1/convert → parsed JSON. Retry on network errors; raise AppError on HTTP 4xx."""
    last_exc: Exception | None = None
    for attempt, delay in enumerate(_RETRY_DELAYS, 1):
        try:
            async with httpx.AsyncClient(
                base_url=settings.dxf_converter_url,
                timeout=settings.dxf_converter_timeout,
            ) as client:
                resp = await client.post(
                    "/v1/convert",
                    files={"file": ("drawing.dxf", dxf_bytes, "application/octet-stream")},
                    data={"render_png": "true" if render_png else "false"},
                )
            ct = resp.headers.get("content-type", "")
            if resp.status_code == 422:
                detail = resp.json().get("detail", "Ошибка конвертации DXF") if "json" in ct else resp.text[:200]
                raise AppError("DXF_CONVERSION_FAILED", str(detail), 422)
            if resp.status_code >= 400:
                raise AppError(
                    "DXF_CONVERSION_FAILED",
                    f"DXF Converter вернул HTTP {resp.status_code}",
                    422,
                )
            return resp.json()
        except AppError:
            raise
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exc = exc
            logger.warning(
                "DXF Converter недоступен (попытка %s/%s): %s", attempt, len(_RETRY_DELAYS), exc
            )
            if attempt < len(_RETRY_DELAYS):
                await asyncio.sleep(delay)
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "DXF Converter ошибка (попытка %s/%s): %s", attempt, len(_RETRY_DELAYS), exc
            )
            if attempt < len(_RETRY_DELAYS):
                await asyncio.sleep(delay)

    raise AppError(
        "DXF_CONVERTER_UNAVAILABLE",
        "Сервис конвертации DXF недоступен, повторите позже",
        502,
    ) from last_exc


async def get_preview_png(dxf_bytes: bytes) -> bytes:
    """Конвертировать DXF → PNG-превью (bytes).

    Шаги:
    1. POST /v1/convert с render_png=true → получаем job_id и имя PNG-файла
    2. GET /v1/artifacts/{job_id}/{filename} → скачиваем PNG bytes
    """
    data = await _post_convert(dxf_bytes, render_png=True)

    png_filename = (data.get("files") or {}).get("png")
    job_id = data.get("job_id")
    if not png_filename or not job_id:
        raise AppError("DXF_CONVERSION_FAILED", "Конвертер не вернул PNG артефакт", 422)

    artifact_url = (
        f"{settings.dxf_converter_url.rstrip('/')}/v1/artifacts/{job_id}/{png_filename}"
    )
    last_exc: Exception | None = None
    for attempt, delay in enumerate(_RETRY_DELAYS, 1):
        try:
            async with httpx.AsyncClient(timeout=settings.dxf_converter_timeout) as client:
                resp = await client.get(artifact_url)
            if resp.status_code >= 400:
                raise AppError(
                    "DXF_CONVERSION_FAILED",
                    f"Не удалось скачать PNG превью: HTTP {resp.status_code}",
                    422,
                )
            return resp.content
        except AppError:
            raise
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exc = exc
            if attempt < len(_RETRY_DELAYS):
                await asyncio.sleep(delay)
        except Exception as exc:
            last_exc = exc
            if attempt < len(_RETRY_DELAYS):
                await asyncio.sleep(delay)

    raise AppError(
        "DXF_CONVERTER_UNAVAILABLE",
        "Сервис конвертации DXF недоступен при скачивании PNG",
        502,
    ) from last_exc


async def get_llm_markdown(dxf_bytes: bytes) -> str:
    """Конвертировать DXF → LLM Markdown контекст (строка).

    POST /v1/convert с render_png=false → поле llm_context в ответе.
    """
    data = await _post_convert(dxf_bytes, render_png=False)
    return data.get("llm_context") or ""
