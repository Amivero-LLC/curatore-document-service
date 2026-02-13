"""Tests for PDF extraction via PyMuPDF."""

import importlib.util
import io
import tempfile

import pytest
from fastapi.testclient import TestClient

from tests.fixtures_docs import MARKERS, build_pdf_bytes

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fitz") is None,
    reason="PyMuPDF not available",
)


def get_client():
    from app.main import app
    return TestClient(app)


def test_simple_pdf_extraction(monkeypatch):
    """Simple text-based PDF should extract via fast_pdf."""
    from app import config
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(config.settings, "UPLOAD_DIR", tmpdir, raising=True)

        client = get_client()
        pdf_bytes = build_pdf_bytes(MARKERS["pdf"])
        files = {"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")}

        r = client.post("/api/v1/extract", files=files)
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["method"] == "fast_pdf"
        assert body["content_chars"] > 0
        assert MARKERS["pdf"] in body["content_markdown"]
        assert body["page_count"] == 1


def test_pdf_extraction_with_engine_override(monkeypatch):
    """Caller can force fast_pdf engine."""
    from app import config
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(config.settings, "UPLOAD_DIR", tmpdir, raising=True)

        client = get_client()
        pdf_bytes = build_pdf_bytes("Engine override test")
        files = {"file": ("override.pdf", io.BytesIO(pdf_bytes), "application/pdf")}

        r = client.post("/api/v1/extract?engine=fast_pdf", files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["method"] == "fast_pdf"


def test_empty_pdf_returns_422(monkeypatch):
    """PDF with no extractable text should return 422."""
    from app import config
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(config.settings, "UPLOAD_DIR", tmpdir, raising=True)

        client = get_client()
        # Minimal valid PDF with no text stream
        import fitz
        doc = fitz.open()
        doc.new_page()  # blank page
        pdf_bytes = doc.tobytes()
        doc.close()

        files = {"file": ("empty.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        r = client.post("/api/v1/extract?engine=fast_pdf", files=files)
        assert r.status_code == 422


def test_multipage_pdf(monkeypatch):
    """Multi-page PDF extraction should report page count."""
    from app import config
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(config.settings, "UPLOAD_DIR", tmpdir, raising=True)

        client = get_client()
        import fitz
        doc = fitz.open()
        for i in range(3):
            page = doc.new_page()
            page.insert_text((72, 72), f"Page {i + 1} content")
        pdf_bytes = doc.tobytes()
        doc.close()

        files = {"file": ("multi.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        r = client.post("/api/v1/extract?engine=fast_pdf", files=files)
        assert r.status_code == 200
        body = r.json()
        assert body["page_count"] == 3
        assert "Page 1" in body["content_markdown"]
