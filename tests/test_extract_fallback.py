"""Tests for extraction fallback when Docling fails."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def get_client():
    from app.main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_health_service():
    """Reset the module-level health service between tests."""
    from app.services.docling_health_service import docling_health_service
    docling_health_service._is_reachable = None
    docling_health_service._last_check_time = None
    docling_health_service._last_error = None
    yield
    docling_health_service._is_reachable = None
    docling_health_service._last_check_time = None
    docling_health_service._last_error = None


@pytest.fixture(autouse=True)
def reset_detected_endpoint():
    """Reset cached endpoint between tests."""
    from app.services import docling_proxy_service
    docling_proxy_service._detected_endpoint = None
    yield
    docling_proxy_service._detected_endpoint = None


def test_docling_fails_falls_back_to_fast_pdf(monkeypatch):
    """PDF upload: Docling fails -> falls back to fast_pdf, metadata has fallback_from."""
    import importlib.util
    if importlib.util.find_spec("fitz") is None:
        pytest.skip("PyMuPDF not available")

    from app import config
    from app.services.docling_health_service import docling_health_service

    # Configure Docling as enabled and reachable (so triage routes to docling)
    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "http://docling:8080")
    monkeypatch.setattr(config.settings, "DOCLING_TIMEOUT", 5)

    # Mark as reachable so triage sees docling_enabled=True
    import time
    docling_health_service._is_reachable = True
    docling_health_service._last_check_time = time.monotonic()

    # Mock check_health to be a no-op (skip real HTTP)
    monkeypatch.setattr(docling_health_service, "check_health", AsyncMock(return_value=True))

    # Mock extract_via_docling to simulate failure (empty content)
    async def mock_docling_fail(*args, **kwargs):
        return ("", "error", False, None)

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(config.settings, "UPLOAD_DIR", tmpdir)

        # Create a minimal real PDF for fast_pdf to extract from
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello fallback world")
        pdf_path = Path(tmpdir) / "test.pdf"
        doc.save(str(pdf_path))
        doc.close()

        with patch(
            "app.services.docling_proxy_service.extract_via_docling",
            new=mock_docling_fail,
        ):
            client = get_client()
            with pdf_path.open("rb") as f:
                resp = client.post(
                    "/api/v1/extract",
                    files={"file": ("test.pdf", f, "application/pdf")},
                )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["method"] == "fast_pdf"
    assert body["metadata"].get("fallback_from") == "docling"
    assert body["metadata"].get("fallback_to") == "fast_pdf"


def test_docling_fails_falls_back_to_markitdown(monkeypatch):
    """DOCX upload forced to docling, mock docling error -> falls back to markitdown."""
    import importlib.util
    if importlib.util.find_spec("markitdown") is None:
        pytest.skip("markitdown not available")

    from app import config
    from app.services.docling_health_service import docling_health_service

    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "http://docling:8080")
    monkeypatch.setattr(config.settings, "DOCLING_TIMEOUT", 5)

    import time
    docling_health_service._is_reachable = True
    docling_health_service._last_check_time = time.monotonic()
    monkeypatch.setattr(docling_health_service, "check_health", AsyncMock(return_value=True))

    async def mock_docling_fail(*args, **kwargs):
        return ("", "error", False, None)

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(config.settings, "UPLOAD_DIR", tmpdir)

        # Use engine=docling override to force docling routing for a .docx
        from tests.fixtures_docs import create_all_docs
        doc_dir = Path(tmpdir) / "docs"
        doc_dir.mkdir()
        create_all_docs(doc_dir)
        docx_path = doc_dir / "sample.docx"
        if not docx_path.exists():
            pytest.skip("sample.docx not created by fixtures")

        with patch(
            "app.services.docling_proxy_service.extract_via_docling",
            new=mock_docling_fail,
        ):
            client = get_client()
            with docx_path.open("rb") as f:
                resp = client.post(
                    "/api/v1/extract",
                    files={"file": ("sample.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                    params={"engine": "docling"},
                )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["metadata"].get("fallback_from") == "docling"
    assert body["metadata"].get("fallback_to") == body["method"]


def test_no_fallback_on_success(monkeypatch):
    """When docling succeeds, no fallback metadata should be present."""
    from app import config
    from app.services.docling_health_service import docling_health_service

    monkeypatch.setattr(config.settings, "DOCLING_SERVICE_URL", "http://docling:8080")
    monkeypatch.setattr(config.settings, "DOCLING_TIMEOUT", 5)

    import time
    docling_health_service._is_reachable = True
    docling_health_service._last_check_time = time.monotonic()
    monkeypatch.setattr(docling_health_service, "check_health", AsyncMock(return_value=True))

    async def mock_docling_success(*args, **kwargs):
        return ("# Extracted Content\n\nSome text here.", "docling", True, 3)

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(config.settings, "UPLOAD_DIR", tmpdir)

        pdf_path = Path(tmpdir) / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake content")

        with patch(
            "app.services.docling_proxy_service.extract_via_docling",
            new=mock_docling_success,
        ):
            client = get_client()
            with pdf_path.open("rb") as f:
                resp = client.post(
                    "/api/v1/extract",
                    files={"file": ("test.pdf", f, "application/pdf")},
                )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["method"] == "docling"
    assert "fallback_from" not in body["metadata"]
    assert "fallback_to" not in body["metadata"]
