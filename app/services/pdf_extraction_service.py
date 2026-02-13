"""
PDF extraction service using PyMuPDF.

Provides fast text extraction from simple PDFs that have an embedded text layer.
For complex PDFs (scanned, complex layouts, tables), use the Docling proxy instead.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("document_service.pdf_extraction")


def extract_pdf(path: str, filename: str) -> Tuple[str, str, bool, Optional[int]]:
    """
    Extract text from PDF using PyMuPDF.

    Args:
        path: Absolute path to the PDF file
        filename: Original filename

    Returns:
        (markdown, method, ocr_used, page_count)
    """
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF (fitz) is not installed. Install with: pip install PyMuPDF")
        return ("", "error", False, None)

    try:
        logger.info("Extracting PDF with PyMuPDF: %s", filename)

        doc = fitz.open(path)
        markdown_parts = []

        # Extract document metadata
        metadata = doc.metadata
        if metadata:
            title = metadata.get("title", "")
            author = metadata.get("author", "")

            if title:
                markdown_parts.append(f"# {title}\n")
            if author:
                markdown_parts.append(f"*Author: {author}*\n")
            if title or author:
                markdown_parts.append("")  # Blank line after metadata

        # Extract text from each page
        total_pages = len(doc)
        for page_num in range(total_pages):
            page = doc[page_num]

            # Get text with layout preservation
            text = page.get_text("text")

            if text.strip():
                # Add page separator for multi-page docs
                if total_pages > 1 and page_num > 0:
                    markdown_parts.append(f"\n---\n\n*Page {page_num + 1}*\n")

                markdown_parts.append(text.strip())

        doc.close()

        # Combine all parts
        markdown_content = "\n\n".join(markdown_parts)

        if not markdown_content.strip():
            logger.warning(
                "PDF contains no extractable text: %s (%d pages)",
                filename, total_pages
            )
            return ("", "error", False, total_pages)

        logger.info(
            "PDF extraction complete: %s - %d pages, %d characters",
            filename, total_pages, len(markdown_content)
        )

        return (markdown_content, "fast_pdf", False, total_pages)

    except Exception as e:
        logger.error("PDF extraction failed for %s: %s", filename, str(e))
        return ("", "error", False, None)
