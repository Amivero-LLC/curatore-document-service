"""
Triage Service for Intelligent Document Extraction Routing.

Performs lightweight document analysis to select the optimal extraction engine:
- fast_pdf: PyMuPDF-based extraction for simple PDFs
- markitdown: MarkItDown for Office files and text
- docling: Advanced extraction for complex documents (OCR, layout analysis)

Note: Standalone image files are NOT supported. Image OCR is only performed
within documents (e.g., scanned PDFs) via the Docling engine.
"""

import logging
import mimetypes
import time
from pathlib import Path
from typing import Optional

from ..config import settings

logger = logging.getLogger("document_service.triage")


# File extension groups
PDF_EXTENSIONS = {".pdf"}
OFFICE_DOCUMENT_EXTENSIONS = {".docx", ".doc"}
OFFICE_PRESENTATION_EXTENSIONS = {".pptx", ".ppt"}
OFFICE_SPREADSHEET_EXTENSIONS = {".xlsx", ".xls"}
OFFICE_EXTENSIONS = OFFICE_DOCUMENT_EXTENSIONS | OFFICE_PRESENTATION_EXTENSIONS | OFFICE_SPREADSHEET_EXTENSIONS
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp"}
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".rst", ".csv", ".json", ".xml", ".html", ".htm"}


class TriageService:
    """
    Service for intelligent document triage and extraction routing.

    Performs lightweight analysis of documents to determine the optimal
    extraction engine. The triage process is designed to be fast (sub-second)
    while providing accurate routing decisions.
    """

    def __init__(self):
        """Initialize the triage service."""
        self._fitz_available = self._check_fitz_available()

    def _check_fitz_available(self) -> bool:
        """Check if PyMuPDF (fitz) is available for PDF analysis."""
        try:
            import fitz
            return True
        except ImportError:
            logger.warning(
                "PyMuPDF (fitz) not available. PDF triage will use fallback logic."
            )
            return False

    async def triage(
        self,
        file_path: Path,
        mime_type: Optional[str] = None,
        docling_enabled: Optional[bool] = None,
    ) -> dict:
        """
        Analyze a document and determine the optimal extraction engine.

        Args:
            file_path: Path to the document file
            mime_type: MIME type (optional, will be guessed from extension)
            docling_enabled: Whether Docling service is available.
                             If None, derived from settings.DOCLING_SERVICE_URL.

        Returns:
            Dict with triage plan: file_type, engine, needs_ocr, needs_layout,
            complexity, triage_duration_ms, reason
        """
        start_time = time.time()

        if docling_enabled is None:
            docling_enabled = bool(settings.DOCLING_SERVICE_URL)

        # Get file extension
        ext = file_path.suffix.lower()
        if not ext and mime_type:
            ext = mimetypes.guess_extension(mime_type) or ""

        # Determine file category and run appropriate analysis
        if ext in IMAGE_EXTENSIONS:
            plan = self._triage_image(ext)
        elif ext in PDF_EXTENSIONS:
            plan = await self._triage_pdf(file_path, ext, docling_enabled)
        elif ext in OFFICE_EXTENSIONS:
            plan = await self._triage_office(file_path, ext, docling_enabled)
        elif ext in TEXT_EXTENSIONS:
            plan = self._triage_text(ext)
        else:
            # Unknown file type - try markitdown as fallback
            plan = {
                "file_type": ext,
                "engine": "markitdown",
                "needs_ocr": False,
                "needs_layout": False,
                "complexity": "low",
                "reason": f"Unknown file type {ext}, using markitdown as fallback",
            }

        # If Docling is not enabled, fall back to fast engines
        if not docling_enabled and plan["engine"] == "docling":
            original_engine = plan["engine"]
            if ext in PDF_EXTENSIONS:
                plan = {
                    "file_type": ext,
                    "engine": "fast_pdf",
                    "needs_ocr": plan["needs_ocr"],
                    "needs_layout": plan["needs_layout"],
                    "complexity": plan["complexity"],
                    "reason": f"Docling disabled, falling back from {original_engine} to fast_pdf",
                }
            else:
                plan = {
                    "file_type": ext,
                    "engine": "markitdown",
                    "needs_ocr": plan["needs_ocr"],
                    "needs_layout": plan["needs_layout"],
                    "complexity": plan["complexity"],
                    "reason": f"Docling disabled, falling back from {original_engine} to markitdown",
                }

        # Calculate triage duration
        duration_ms = int((time.time() - start_time) * 1000)
        plan["triage_duration_ms"] = duration_ms

        logger.info(
            "Triage complete: file=%s, engine=%s, complexity=%s, duration=%dms, reason=%s",
            file_path.name, plan["engine"], plan["complexity"], duration_ms, plan["reason"]
        )

        return plan

    def _triage_image(self, ext: str) -> dict:
        """Triage image files - not supported as standalone files."""
        return {
            "file_type": ext,
            "engine": "unsupported",
            "needs_ocr": False,
            "needs_layout": False,
            "complexity": "low",
            "reason": "Standalone image files are not supported. Image OCR is only available within documents (e.g., scanned PDFs).",
        }

    async def _triage_pdf(
        self,
        file_path: Path,
        ext: str,
        docling_enabled: bool,
    ) -> dict:
        """
        Triage PDF files using PyMuPDF analysis.

        Checks:
        1. Whether PDF has extractable text (vs scanned/image-based)
        2. Layout complexity (number of blocks, images, tables)
        """
        if not self._fitz_available:
            return {
                "file_type": ext,
                "engine": "docling" if docling_enabled else "fast_pdf",
                "needs_ocr": False,
                "needs_layout": False,
                "complexity": "medium",
                "reason": "PyMuPDF not available, using fallback routing",
            }

        try:
            import fitz

            doc = fitz.open(str(file_path))
            total_pages = len(doc)

            pages_to_check = min(settings.PDF_PAGES_TO_ANALYZE, total_pages)
            total_text_length = 0
            total_blocks = 0
            total_images = 0
            has_tables = False

            for page_num in range(pages_to_check):
                page = doc[page_num]

                text = page.get_text()
                total_text_length += len(text)

                blocks = page.get_text("dict")["blocks"]
                total_blocks += len(blocks)

                image_list = page.get_images(full=True)
                total_images += len(image_list)

                drawings = page.get_drawings()
                line_count = sum(1 for d in drawings if d.get("items"))
                if line_count > 20:
                    has_tables = True

            doc.close()

            avg_text_per_page = total_text_length / pages_to_check if pages_to_check > 0 else 0
            avg_blocks_per_page = total_blocks / pages_to_check if pages_to_check > 0 else 0
            avg_images_per_page = total_images / pages_to_check if pages_to_check > 0 else 0

            needs_ocr = avg_text_per_page < 100
            is_complex_layout = (
                avg_blocks_per_page > settings.PDF_BLOCK_THRESHOLD or
                avg_images_per_page > settings.PDF_IMAGE_THRESHOLD or
                has_tables
            )

            if needs_ocr:
                complexity = "high"
            elif is_complex_layout:
                complexity = "medium"
            else:
                complexity = "low"

            if needs_ocr:
                engine = "docling"
                reason = f"PDF needs OCR (avg {avg_text_per_page:.0f} chars/page)"
            elif is_complex_layout:
                engine = "docling"
                reasons = []
                if avg_blocks_per_page > settings.PDF_BLOCK_THRESHOLD:
                    reasons.append(f"{avg_blocks_per_page:.0f} blocks/page")
                if avg_images_per_page > settings.PDF_IMAGE_THRESHOLD:
                    reasons.append(f"{avg_images_per_page:.0f} images/page")
                if has_tables:
                    reasons.append("tables detected")
                reason = f"Complex PDF layout: {', '.join(reasons)}"
            else:
                engine = "fast_pdf"
                reason = f"Simple text-based PDF ({avg_text_per_page:.0f} chars/page, {avg_blocks_per_page:.0f} blocks/page)"

            return {
                "file_type": ext,
                "engine": engine,
                "needs_ocr": needs_ocr,
                "needs_layout": is_complex_layout,
                "complexity": complexity,
                "reason": reason,
            }

        except Exception as e:
            logger.warning("PDF analysis failed for %s: %s", file_path.name, e)
            return {
                "file_type": ext,
                "engine": "docling" if docling_enabled else "fast_pdf",
                "needs_ocr": False,
                "needs_layout": True,
                "complexity": "medium",
                "reason": f"PDF analysis failed ({e}), using cautious routing",
            }

    async def _triage_office(
        self,
        file_path: Path,
        ext: str,
        docling_enabled: bool,
    ) -> dict:
        """
        Triage Office files (DOCX, PPTX, XLSX).

        Uses file size as a proxy for complexity.
        """
        try:
            file_size = file_path.stat().st_size
            file_size_mb = file_size / (1024 * 1024)
        except Exception:
            file_size_mb = 0

        is_complex = file_size >= settings.OFFICE_SIZE_THRESHOLD

        if is_complex and docling_enabled:
            return {
                "file_type": ext,
                "engine": "docling",
                "needs_ocr": False,
                "needs_layout": True,
                "complexity": "medium",
                "reason": f"Large Office file ({file_size_mb:.1f}MB), using Docling for better layout",
            }
        else:
            return {
                "file_type": ext,
                "engine": "markitdown",
                "needs_ocr": False,
                "needs_layout": False,
                "complexity": "low",
                "reason": f"Office file ({file_size_mb:.1f}MB), using MarkItDown",
            }

    def _triage_text(self, ext: str) -> dict:
        """Triage text files - always simple, use markitdown."""
        return {
            "file_type": ext,
            "engine": "markitdown",
            "needs_ocr": False,
            "needs_layout": False,
            "complexity": "low",
            "reason": "Text-based file, using MarkItDown",
        }


# Singleton instance
triage_service = TriageService()
