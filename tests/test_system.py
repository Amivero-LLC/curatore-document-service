import time
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def get_client():
    from app.main import app
    return TestClient(app)


def test_health_ok():
    client = get_client()
    r = client.get("/api/v1/system/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    assert body.get("service") == "document-service"
    # Docling status should always be present
    assert "docling" in body
    docling = body["docling"]
    assert "configured" in docling
    assert "reachable" in docling


def test_health_with_docling_configured(monkeypatch):
    """When DOCLING_SERVICE_URL is set, health should report configured=True."""
    from app import config
    from app.services.docling_health_service import docling_health_service

    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "http://docling:8080")

    # Simulate a recent health check so it doesn't try to hit real network
    docling_health_service._is_reachable = True
    docling_health_service._last_check_time = time.monotonic()
    docling_health_service._last_error = None

    try:
        client = get_client()
        r = client.get("/api/v1/system/health")
        assert r.status_code == 200
        body = r.json()
        assert body["docling"]["configured"] is True
        assert body["docling"]["reachable"] is True
    finally:
        # Clean up
        docling_health_service._is_reachable = None
        docling_health_service._last_check_time = None


def test_supported_formats_nonempty():
    client = get_client()
    r = client.get("/api/v1/system/supported-formats")
    assert r.status_code == 200
    body = r.json()
    exts = body.get("extensions") or []
    assert isinstance(exts, list)
    assert len(exts) > 0
    assert ".docx" in exts
    assert ".pdf" in exts  # New: PDFs are now handled by this service


def test_capabilities():
    client = get_client()
    r = client.get("/api/v1/system/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert "extraction_formats" in body
    assert "generation_formats" in body
    assert ".pdf" in body["extraction_formats"]
    assert "pdf" in body["generation_formats"]
    assert "docx" in body["generation_formats"]
    assert "csv" in body["generation_formats"]
    assert body["triage_available"] is True
    # Docling status should be present
    assert "docling" in body
    assert "configured" in body["docling"]
