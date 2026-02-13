"""Tests for triage routing logic."""

import importlib.util
import tempfile
from pathlib import Path

import pytest

from tests.fixtures_docs import build_docx_bytes, build_pdf_bytes


@pytest.fixture
def triage():
    from app.services.triage_service import TriageService
    return TriageService()


@pytest.mark.asyncio
async def test_text_file_routes_to_markitdown(triage, tmp_path):
    """Text files should always route to markitdown."""
    p = tmp_path / "readme.txt"
    p.write_text("Hello world")

    plan = await triage.triage(p)
    assert plan["engine"] == "markitdown"
    assert plan["complexity"] == "low"


@pytest.mark.asyncio
async def test_csv_routes_to_markitdown(triage, tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("a,b\n1,2")

    plan = await triage.triage(p)
    assert plan["engine"] == "markitdown"


@pytest.mark.asyncio
async def test_small_office_routes_to_markitdown(triage, tmp_path):
    """Small Office files should route to markitdown."""
    p = tmp_path / "small.docx"
    p.write_bytes(build_docx_bytes("Small document"))

    plan = await triage.triage(p)
    assert plan["engine"] == "markitdown"
    assert plan["complexity"] == "low"


@pytest.mark.asyncio
async def test_large_office_routes_to_docling_when_enabled(triage, tmp_path, monkeypatch):
    """Large Office files should route to docling when available."""
    from app import config
    monkeypatch.setattr(config.settings, "OFFICE_SIZE_THRESHOLD", 100)  # 100 bytes

    p = tmp_path / "large.docx"
    p.write_bytes(build_docx_bytes("X" * 200))  # larger than 100 bytes

    plan = await triage.triage(p, docling_enabled=True)
    assert plan["engine"] == "docling"


@pytest.mark.asyncio
async def test_large_office_falls_back_when_docling_disabled(triage, tmp_path, monkeypatch):
    """Large Office files fall back to markitdown when docling is disabled."""
    from app import config
    monkeypatch.setattr(config.settings, "OFFICE_SIZE_THRESHOLD", 100)

    p = tmp_path / "large.docx"
    p.write_bytes(build_docx_bytes("X" * 200))

    plan = await triage.triage(p, docling_enabled=False)
    assert plan["engine"] == "markitdown"


@pytest.mark.skipif(
    importlib.util.find_spec("fitz") is None,
    reason="PyMuPDF not available",
)
@pytest.mark.asyncio
async def test_simple_pdf_routes_to_fast_pdf(triage, tmp_path):
    """Simple text-based PDF should route to fast_pdf."""
    import fitz
    # Create a PDF with enough text to pass the OCR threshold (>100 chars/page)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "This is a simple text-based PDF with enough content. " * 5)
    p = tmp_path / "simple.pdf"
    doc.save(str(p))
    doc.close()

    plan = await triage.triage(p)
    assert plan["engine"] == "fast_pdf"
    assert plan["complexity"] == "low"
    assert plan["needs_ocr"] is False


@pytest.mark.asyncio
async def test_image_file_unsupported(triage, tmp_path):
    """Standalone images should be unsupported."""
    p = tmp_path / "photo.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")

    plan = await triage.triage(p)
    assert plan["engine"] == "unsupported"


@pytest.mark.asyncio
async def test_unknown_extension_fallback(triage, tmp_path):
    """Unknown file types should fall back to markitdown."""
    p = tmp_path / "mystery.xyz"
    p.write_bytes(b"some data")

    plan = await triage.triage(p)
    assert plan["engine"] == "markitdown"


@pytest.mark.asyncio
async def test_triage_duration_is_set(triage, tmp_path):
    """Triage should report duration in milliseconds."""
    p = tmp_path / "quick.txt"
    p.write_text("fast")

    plan = await triage.triage(p)
    assert "triage_duration_ms" in plan
    assert isinstance(plan["triage_duration_ms"], int)
