"""Tests for triage routing logic."""

import importlib.util
import io
import tempfile
import xml.etree.ElementTree as ET
import zipfile
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


# ---------------------------------------------------------------------------
# Table detection tests (Step 1)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    importlib.util.find_spec("fitz") is None,
    reason="PyMuPDF not available",
)
@pytest.mark.asyncio
async def test_pdf_with_tables_routes_to_docling(triage, tmp_path):
    """PDF with table grid lines and cell text should route to docling."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()

    # Draw a 3x3 table grid (enough structure for find_tables to detect)
    x0, y0 = 72, 72
    col_w, row_h = 120, 30
    cols, rows = 4, 4

    # Horizontal lines
    for r in range(rows + 1):
        y = y0 + r * row_h
        page.draw_line((x0, y), (x0 + cols * col_w, y))
    # Vertical lines
    for c in range(cols + 1):
        x = x0 + c * col_w
        page.draw_line((x, y0), (x, y0 + rows * row_h))

    # Add text in cells
    for r in range(rows):
        for c in range(cols):
            page.insert_text(
                (x0 + c * col_w + 5, y0 + r * row_h + 20),
                f"Cell {r},{c}",
                fontsize=10,
            )

    # Add enough body text so the PDF doesn't appear to need OCR
    page.insert_text((72, y0 + (rows + 1) * row_h + 20), "Body text content. " * 10)

    p = tmp_path / "table.pdf"
    doc.save(str(p))
    doc.close()

    plan = await triage.triage(p, docling_enabled=True)
    assert plan["engine"] == "docling"
    assert "tables detected" in plan["reason"]


@pytest.mark.asyncio
async def test_xlsb_routes_through_office_triage(triage, tmp_path):
    """.xlsb files should route through office triage, not unknown fallback."""
    p = tmp_path / "workbook.xlsb"
    p.write_bytes(b"\x00" * 100)  # dummy content

    plan = await triage.triage(p, docling_enabled=False)
    # Should route to markitdown (office triage), not "unknown fallback"
    assert plan["engine"] == "markitdown"
    assert "unknown" not in plan["reason"].lower()


# ---------------------------------------------------------------------------
# Multi-column detection tests (Step 2)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    importlib.util.find_spec("fitz") is None,
    reason="PyMuPDF not available",
)
@pytest.mark.asyncio
async def test_multicolumn_pdf_routes_to_docling(triage, tmp_path):
    """PDF with left/right column text should route to docling."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # US Letter

    # Left column text blocks (x < 45% of page width ≈ 275)
    for i in range(3):
        page.insert_text((50, 100 + i * 80), "Left column paragraph text. " * 4, fontsize=10)

    # Right column text blocks (x > 50% of page width ≈ 306)
    for i in range(3):
        page.insert_text((320, 100 + i * 80), "Right column paragraph text. " * 4, fontsize=10)

    p = tmp_path / "twocol.pdf"
    doc.save(str(p))
    doc.close()

    plan = await triage.triage(p, docling_enabled=True)
    assert plan["engine"] == "docling"
    assert "multi-column" in plan["reason"]


@pytest.mark.skipif(
    importlib.util.find_spec("fitz") is None,
    reason="PyMuPDF not available",
)
@pytest.mark.asyncio
async def test_triage_plan_includes_docling_params(triage, tmp_path):
    """Triage plan for PDF should include docling_params dict."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Simple text content for a basic PDF document. " * 5)
    p = tmp_path / "params.pdf"
    doc.save(str(p))
    doc.close()

    plan = await triage.triage(p)
    assert "docling_params" in plan
    assert isinstance(plan["docling_params"], dict)
    assert "page_count" in plan
    assert plan["page_count"] >= 1
    assert "table_count" in plan
    assert plan["table_count"] == 0
    # Simple text PDF with no OCR needed should have do_ocr=False
    assert plan["docling_params"].get("do_ocr") is False
    assert plan["docling_params"].get("table_mode") == "fast"


# ---------------------------------------------------------------------------
# DOCX content analysis tests (Step 4)
# ---------------------------------------------------------------------------

def _build_docx_with_nested_table() -> bytes:
    """Build a minimal DOCX with a nested table (w:tbl inside w:tbl)."""
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    content_types = (
        b"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        b"<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
        b"<Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>"
        b"<Default Extension='xml' ContentType='application/xml'/>"
        b"<Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/>"
        b"</Types>"
    )
    rels = (
        b"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        b"<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
        b"<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='word/document.xml'/>"
        b"</Relationships>"
    )
    # Document with nested table: outer table cell contains an inner table
    doc_xml = f"""<?xml version='1.0' encoding='UTF-8' standalone='yes'?>
    <w:document xmlns:w="{ns}"
     xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <w:body>
        <w:p><w:r><w:t>Before table</w:t></w:r></w:p>
        <w:tbl>
          <w:tr>
            <w:tc>
              <w:p><w:r><w:t>Outer cell</w:t></w:r></w:p>
              <w:tbl>
                <w:tr>
                  <w:tc><w:p><w:r><w:t>Inner cell</w:t></w:r></w:p></w:tc>
                </w:tr>
              </w:tbl>
            </w:tc>
          </w:tr>
        </w:tbl>
        <w:sectPr/>
      </w:body>
    </w:document>""".encode("utf-8")

    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc_xml)
    return bio.getvalue()


@pytest.mark.asyncio
async def test_docx_with_nested_tables_routes_to_docling(triage, tmp_path):
    """DOCX with nested tables should route to docling."""
    p = tmp_path / "nested.docx"
    p.write_bytes(_build_docx_with_nested_table())

    plan = await triage.triage(p, docling_enabled=True)
    assert plan["engine"] == "docling"
    assert "complex tables" in plan["reason"]


@pytest.mark.asyncio
async def test_docx_simple_still_markitdown(triage, tmp_path):
    """Simple DOCX without complex content should still route to markitdown."""
    p = tmp_path / "simple.docx"
    p.write_bytes(build_docx_bytes("Just a simple paragraph."))

    plan = await triage.triage(p, docling_enabled=True)
    assert plan["engine"] == "markitdown"


@pytest.mark.asyncio
async def test_xlsx_still_size_based(triage, tmp_path):
    """Small XLSX should route to markitdown regardless of content."""
    from tests.fixtures_docs import build_xlsx_bytes

    p = tmp_path / "data.xlsx"
    p.write_bytes(build_xlsx_bytes("Some spreadsheet data"))

    plan = await triage.triage(p, docling_enabled=True)
    assert plan["engine"] == "markitdown"
    assert plan["complexity"] == "low"
