"""Unit-тесты для dxf_converter_client — mock httpx, retry, error codes."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.exceptions import AppError


SAMPLE_DXF = b"AutoCAD DXF fake content for tests"
SAMPLE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # minimal fake PNG


def _mock_response(status_code: int = 200, json_data: dict | None = None, content: bytes = b"") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.headers = MagicMock()
    resp.headers.get = MagicMock(return_value="application/json")
    if json_data is not None:
        resp.json = MagicMock(return_value=json_data)
    else:
        resp.json = MagicMock(side_effect=ValueError("no json"))
    return resp


@pytest.mark.asyncio
async def test_get_preview_png_success():
    """get_preview_png: успешная конвертация возвращает PNG bytes."""
    convert_resp = _mock_response(
        json_data={
            "job_id": "abc123",
            "files": {"png": "drawing.png"},
            "llm_context": "",
            "validation_gate": {"status": "pass"},
        }
    )
    png_resp = _mock_response(content=SAMPLE_PNG)

    with patch("app.services.dxf_converter_client.settings") as mock_settings:
        mock_settings.dxf_converter_url = "http://dxf-converter:8001"
        mock_settings.dxf_converter_timeout = 8.0

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=convert_resp)
        mock_client.get = AsyncMock(return_value=png_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            from app.services import dxf_converter_client
            result = await dxf_converter_client.get_preview_png(SAMPLE_DXF)

    assert result == SAMPLE_PNG


@pytest.mark.asyncio
async def test_get_llm_markdown_success():
    """get_llm_markdown: успешный вызов возвращает строку llm_context."""
    md_text = "# LLM Engineering Context\n\nProduct Identity: ..."
    convert_resp = _mock_response(
        json_data={
            "job_id": "abc123",
            "files": {},
            "llm_context": md_text,
            "validation_gate": {"status": "pass"},
        }
    )

    with patch("app.services.dxf_converter_client.settings") as mock_settings:
        mock_settings.dxf_converter_url = "http://dxf-converter:8001"
        mock_settings.dxf_converter_timeout = 8.0

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=convert_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            from app.services import dxf_converter_client
            result = await dxf_converter_client.get_llm_markdown(SAMPLE_DXF)

    assert result == md_text


@pytest.mark.asyncio
async def test_retry_3x_on_connect_error_then_unavailable():
    """Retry 3× при ConnectError → AppError DXF_CONVERTER_UNAVAILABLE."""
    import httpx as _httpx

    with patch("app.services.dxf_converter_client.settings") as mock_settings:
        mock_settings.dxf_converter_url = "http://dxf-converter:8001"
        mock_settings.dxf_converter_timeout = 8.0

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=_httpx.ConnectError("connection refused")
        )

        call_count = 0

        async def counting_sleep(delay):
            nonlocal call_count
            call_count += 1

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("asyncio.sleep", side_effect=counting_sleep):
                from app.services import dxf_converter_client
                with pytest.raises(AppError) as exc_info:
                    await dxf_converter_client.get_llm_markdown(SAMPLE_DXF)

    assert exc_info.value.code == "DXF_CONVERTER_UNAVAILABLE"
    assert exc_info.value.status == 502
    assert mock_client.post.call_count == 3
    assert call_count == 2  # sleep вызывается 2 раза (между 1-2 и 2-3 попытками)


@pytest.mark.asyncio
async def test_conversion_failed_on_422():
    """HTTP 422 от конвертера → AppError DXF_CONVERSION_FAILED (не retry)."""
    err_resp = _mock_response(
        status_code=422,
        json_data={"detail": "Invalid DXF structure"},
    )

    with patch("app.services.dxf_converter_client.settings") as mock_settings:
        mock_settings.dxf_converter_url = "http://dxf-converter:8001"
        mock_settings.dxf_converter_timeout = 8.0

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=err_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            from app.services import dxf_converter_client
            with pytest.raises(AppError) as exc_info:
                await dxf_converter_client.get_llm_markdown(SAMPLE_DXF)

    assert exc_info.value.code == "DXF_CONVERSION_FAILED"
    assert exc_info.value.status == 422
    assert mock_client.post.call_count == 1  # нет retry на 422


@pytest.mark.asyncio
async def test_get_preview_png_missing_png_artifact():
    """Конвертер не вернул files.png → AppError DXF_CONVERSION_FAILED."""
    convert_resp = _mock_response(
        json_data={
            "job_id": "abc123",
            "files": {},  # нет png
            "llm_context": "",
        }
    )

    with patch("app.services.dxf_converter_client.settings") as mock_settings:
        mock_settings.dxf_converter_url = "http://dxf-converter:8001"
        mock_settings.dxf_converter_timeout = 8.0

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=convert_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            from app.services import dxf_converter_client
            with pytest.raises(AppError) as exc_info:
                await dxf_converter_client.get_preview_png(SAMPLE_DXF)

    assert exc_info.value.code == "DXF_CONVERSION_FAILED"
