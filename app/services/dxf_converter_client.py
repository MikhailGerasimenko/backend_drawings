"""HTTP-клиент DXF Converter с retry (3×, экспоненциальные задержки 0.5/1/2 с)."""
import asyncio
import logging

import httpx

from app.core.config import settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

_RETRY_DELAYS = (0.5, 1.0, 2.0)


def _unwrap_convert_payload(body: dict) -> dict:
    """Corp BaseResponse: поля convert лежат в body['data']; старый flat-ответ тоже ок."""
    if not isinstance(body, dict):
        return {}
    data = body.get("data")
    if isinstance(data, dict) and (
        "job_id" in data or "files" in data or "llm_context" in data
    ):
        return data
    return body


def _error_message(resp: httpx.Response) -> str:
    ct = resp.headers.get("content-type", "")
    if "json" not in ct:
        return resp.text[:200] or f"HTTP {resp.status_code}"
    try:
        body = resp.json()
    except Exception:
        return resp.text[:200] or f"HTTP {resp.status_code}"
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if body.get("detail") is not None:
            return str(body["detail"])
    return f"HTTP {resp.status_code}"


async def _post_convert(dxf_bytes: bytes, *, render_png: bool) -> dict:
    """POST /api/v1/convert → ConvertData (unwrap BaseResponse.data)."""
    last_exc: Exception | None = None
    for attempt, delay in enumerate(_RETRY_DELAYS, 1):
        try:
            async with httpx.AsyncClient(
                base_url=settings.dxf_converter_url,
                timeout=settings.dxf_converter_timeout,
            ) as client:
                resp = await client.post(
                    "/api/v1/convert",
                    files={"file": ("drawing.dxf", dxf_bytes, "application/octet-stream")},
                    data={"render_png": "true" if render_png else "false"},
                )
            if resp.status_code == 422:
                raise AppError("DXF_CONVERSION_FAILED", _error_message(resp), 422)
            if resp.status_code >= 400:
                raise AppError(
                    "DXF_CONVERSION_FAILED",
                    f"DXF Converter вернул HTTP {resp.status_code}: {_error_message(resp)}",
                    422,
                )
            return _unwrap_convert_payload(resp.json())
        except AppError:
            raise
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exc = exc
            logger.warning(
                "DXF Converter недоступен (попытка %s/%s): %s",
                attempt,
                len(_RETRY_DELAYS),
                exc,
            )
            if attempt < len(_RETRY_DELAYS):
                await asyncio.sleep(delay)
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "DXF Converter ошибка (попытка %s/%s): %s",
                attempt,
                len(_RETRY_DELAYS),
                exc,
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
    1. POST /api/v1/convert с render_png=true → job_id и имя PNG в data.*
    2. GET /api/v1/artifacts/{job_id}/{filename} → скачиваем PNG bytes
    """
    data = await _post_convert(dxf_bytes, render_png=True)

    png_filename = (data.get("files") or {}).get("png")
    job_id = data.get("job_id")
    if not png_filename or not job_id:
        raise AppError("DXF_CONVERSION_FAILED", "Конвертер не вернул PNG артефакт", 422)

    artifact_url = (
        f"{settings.dxf_converter_url.rstrip('/')}/api/v1/artifacts/{job_id}/{png_filename}"
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

    POST /api/v1/convert с render_png=false → data.llm_context.
    """
    data = await _post_convert(dxf_bytes, render_png=False)
    return data.get("llm_context") or ""
