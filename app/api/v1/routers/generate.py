"""
Document generation API router.

Generates PDF, DOCX, and CSV files from content/data.
Returns raw bytes with appropriate Content-Type headers.
"""

import logging
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ....models import GenerateCsvRequest, GenerateDocxRequest, GeneratePdfRequest
from ....services.generation_service import document_generation_service

router = APIRouter(prefix="/generate", tags=["generation"])
logger = logging.getLogger("document_service.api.generate")


def _sanitize_filename(name: str, default: str, ext: str) -> str:
    """Sanitize a filename for use in Content-Disposition headers."""
    safe = re.sub(r'[^\w\s\-.]', '', name or default)
    safe = safe.strip() or default
    if not safe.endswith(ext):
        safe += ext
    return safe


@router.post("/pdf")
async def generate_pdf(request: GeneratePdfRequest):
    """
    Generate a PDF from markdown content.

    Returns raw PDF bytes with Content-Type: application/pdf.
    """
    try:
        pdf_bytes = await document_generation_service.generate_pdf(
            content=request.content,
            title=request.title,
            css=request.css,
            include_title_page=request.include_title_page,
        )
        filename = _sanitize_filename(request.title, "document", ".pdf")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except RuntimeError as e:
        logger.error("PDF generation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/docx")
async def generate_docx(request: GenerateDocxRequest):
    """
    Generate a DOCX from markdown content.

    Returns raw DOCX bytes with Content-Type for Word documents.
    """
    try:
        docx_bytes = await document_generation_service.generate_docx(
            content=request.content,
            title=request.title,
        )
        filename = _sanitize_filename(request.title, "document", ".docx")
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except RuntimeError as e:
        logger.error("DOCX generation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/csv")
async def generate_csv(request: GenerateCsvRequest):
    """
    Generate a CSV from structured data.

    Returns raw CSV bytes with Content-Type: text/csv.
    """
    try:
        csv_bytes = await document_generation_service.generate_csv(
            data=request.data,
            columns=request.columns,
            include_bom=request.include_bom,
        )
        filename = _sanitize_filename(None, "export", ".csv")
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except (RuntimeError, ValueError) as e:
        logger.error("CSV generation failed: %s", e)
        raise HTTPException(status_code=422, detail=str(e))
