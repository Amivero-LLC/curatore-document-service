"""Tests for DoclingHealthService."""

import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest


def _make_service(ttl=60):
    """Create a fresh DoclingHealthService instance."""
    from app.services.docling_health_service import DoclingHealthService
    return DoclingHealthService(ttl=ttl)


def test_not_configured(monkeypatch):
    """When DOCLING_SERVICE_URL is empty, is_configured=False and docling_enabled=False."""
    from app import config
    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "")

    svc = _make_service()
    assert svc.is_configured is False
    assert svc.docling_enabled is False
    assert svc.needs_recheck() is False


@pytest.mark.asyncio
async def test_check_reachable(monkeypatch):
    """Mock httpx 200 -> is_reachable=True, docling_enabled=True."""
    from app import config
    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "http://docling:8080")

    svc = _make_service()

    mock_response = AsyncMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.services.docling_health_service.httpx.AsyncClient", return_value=mock_client):
        result = await svc.check_health(force=True)

    assert result is True
    assert svc.is_reachable is True
    assert svc.docling_enabled is True


@pytest.mark.asyncio
async def test_check_unreachable(monkeypatch):
    """Mock httpx ConnectError -> is_reachable=False, docling_enabled=False."""
    from app import config
    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "http://docling:8080")

    svc = _make_service()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    with patch("app.services.docling_health_service.httpx.AsyncClient", return_value=mock_client):
        result = await svc.check_health(force=True)

    assert result is False
    assert svc.is_reachable is False
    assert svc.docling_enabled is False
    assert "Connection refused" in (svc.get_status()["last_error"] or "")


@pytest.mark.asyncio
async def test_ttl_caching(monkeypatch):
    """After a check, needs_recheck()=False. After TTL expires, needs_recheck()=True."""
    from app import config
    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "http://docling:8080")

    svc = _make_service(ttl=60)

    mock_response = AsyncMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.services.docling_health_service.httpx.AsyncClient", return_value=mock_client):
        await svc.check_health(force=True)

    assert svc.needs_recheck() is False

    # Simulate TTL expiry by backdating the last check time
    svc._last_check_time = time.monotonic() - 120
    assert svc.needs_recheck() is True


def test_invalidate(monkeypatch):
    """After invalidate(), needs_recheck() returns True."""
    from app import config
    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "http://docling:8080")

    svc = _make_service()
    # Simulate a previous check
    svc._last_check_time = time.monotonic()
    svc._is_reachable = True

    assert svc.needs_recheck() is False
    svc.invalidate()
    assert svc.needs_recheck() is True


def test_get_status_dict(monkeypatch):
    """get_status() returns dict with all expected keys."""
    from app import config
    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "http://docling:8080")

    svc = _make_service()
    status = svc.get_status()

    assert "configured" in status
    assert "reachable" in status
    assert "last_error" in status
    assert "last_check_age_seconds" in status
    assert "service_url" in status
    assert status["configured"] is True
    assert status["reachable"] is None  # never checked
    assert status["service_url"] == "http://docling:8080"


def test_optimistic_before_first_check(monkeypatch):
    """Configured + never checked -> docling_enabled=True (optimistic)."""
    from app import config
    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "http://docling:8080")

    svc = _make_service()
    assert svc.is_configured is True
    assert svc.is_reachable is None
    assert svc.docling_enabled is True
