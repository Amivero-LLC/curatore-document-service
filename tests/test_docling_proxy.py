"""Tests for Docling proxy service (mocked httpx)."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_detected_endpoint():
    """Reset cached endpoint between tests."""
    from app.services import docling_proxy_service
    docling_proxy_service._detected_endpoint = None
    yield
    docling_proxy_service._detected_endpoint = None


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a tiny test file."""
    p = tmp_path / "test.pdf"
    p.write_bytes(b"%PDF-1.4 fake content")
    return str(p)


@pytest.mark.asyncio
async def test_docling_not_configured(sample_pdf, monkeypatch):
    """Should return error if DOCLING_SERVICE_URL is not set."""
    from app import config
    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "")

    from app.services.docling_proxy_service import extract_via_docling
    content, method, ocr, pages = await extract_via_docling(sample_pdf, "test.pdf")
    assert method == "error"
    assert content == ""


@pytest.mark.asyncio
async def test_docling_success(sample_pdf, monkeypatch):
    """Successful Docling extraction should return content."""
    from app import config
    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "http://docling:8080")
    monkeypatch.setattr(config.settings, "DOCLING_TIMEOUT", 10)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {
        "document": {"md_content": "# Extracted\n\nSome content here."}
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.get = AsyncMock(side_effect=Exception("skip openapi"))
    mock_client.options = AsyncMock(return_value=MagicMock(status_code=200))

    with patch("app.services.docling_proxy_service.httpx.AsyncClient", return_value=mock_client):
        from app.services.docling_proxy_service import extract_via_docling
        content, method, ocr, pages = await extract_via_docling(sample_pdf, "test.pdf")

    assert method == "docling"
    assert "Extracted" in content
    assert ocr is True


@pytest.mark.asyncio
async def test_docling_timeout(sample_pdf, monkeypatch):
    """Timeout should be handled gracefully."""
    import httpx
    from app import config
    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "http://docling:8080")
    monkeypatch.setattr(config.settings, "DOCLING_TIMEOUT", 1)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    mock_client.get = AsyncMock(side_effect=Exception("skip"))
    mock_client.options = AsyncMock(side_effect=Exception("skip"))

    with patch("app.services.docling_proxy_service.httpx.AsyncClient", return_value=mock_client):
        from app.services.docling_proxy_service import extract_via_docling
        content, method, ocr, pages = await extract_via_docling(
            sample_pdf, "test.pdf", max_retries=0,
        )

    assert method == "error"
    assert content == ""


@pytest.mark.asyncio
async def test_docling_empty_response(sample_pdf, monkeypatch):
    """Empty content from Docling should not crash."""
    from app import config
    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "http://docling:8080")
    monkeypatch.setattr(config.settings, "DOCLING_TIMEOUT", 10)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {"document": {"md_content": ""}}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.get = AsyncMock(side_effect=Exception("skip"))
    mock_client.options = AsyncMock(return_value=MagicMock(status_code=200))

    with patch("app.services.docling_proxy_service.httpx.AsyncClient", return_value=mock_client):
        from app.services.docling_proxy_service import extract_via_docling
        content, method, ocr, pages = await extract_via_docling(
            sample_pdf, "test.pdf", max_retries=0,
        )

    # Empty content → falls through all retries → error
    assert content == ""
    assert method == "error"


@pytest.mark.asyncio
async def test_docling_params_override(sample_pdf, monkeypatch):
    """Triage-driven overrides should be applied to Docling form data."""
    from app import config
    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "http://docling:8080")
    monkeypatch.setattr(config.settings, "DOCLING_TIMEOUT", 10)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {
        "document": {"md_content": "# Overridden\n\nContent."}
    }
    mock_response.raise_for_status = MagicMock()

    captured_data = {}

    async def capture_post(url, headers=None, files=None, data=None):
        captured_data.update(data or {})
        return mock_response

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=capture_post)
    mock_client.get = AsyncMock(side_effect=Exception("skip openapi"))
    mock_client.options = AsyncMock(return_value=MagicMock(status_code=200))

    overrides = {"do_ocr": False, "table_mode": "fast"}

    with patch("app.services.docling_proxy_service.httpx.AsyncClient", return_value=mock_client):
        from app.services.docling_proxy_service import extract_via_docling
        content, method, ocr, pages = await extract_via_docling(
            sample_pdf, "test.pdf", docling_params=overrides,
        )

    assert method == "docling"
    assert ocr is False  # OCR was overridden to False
    # Verify the form data captured the overrides
    assert captured_data.get("do_ocr") == "false"
    assert captured_data.get("table_mode") == "fast"
