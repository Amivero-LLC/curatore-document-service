"""
Unified extraction API router.

Handles document extraction for all formats:
- Office files (DOCX, PPTX, XLSX, DOC, PPT, XLS) via MarkItDown
- Text files (TXT, MD, CSV) via direct read
- Email files (MSG, EML) via extract-msg / Python email
- PDFs via PyMuPDF (fast_pdf) or Docling proxy
- Triage routing to select optimal engine automatically
"""

import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile

from ....config import settings
from ....models import ExtractionOptions, ExtractionResult, TriageInfo
from ....services.extraction_service import extract_markdown, save_upload_to_disk
from ....services.metadata_extractor import extract_document_metadata
from ....services.pdf_extraction_service import extract_pdf
from ....services.triage_service import triage_service

router = APIRouter(prefix="/extract", tags=["extraction"])
logger = logging.getLogger("document_service.api.extract")


@router.post("", response_model=ExtractionResult)
async def extract(
    file: UploadFile = File(...),
    options: ExtractionOptions = Depends(),
    engine: Optional[str] = Query(
        None,
        description="Engine override: auto, fast_pdf, markitdown, docling. Default: auto (triage decides).",
    ),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
):
    """
    Extract text content from a document.

    Supported formats:
    - Office: DOCX, PPTX, XLSX, DOC, PPT, XLS, XLSB
    - Text: TXT, MD, CSV, HTML, XML, JSON
    - Email: MSG, EML
    - PDF: routed via triage to fast_pdf or docling

    Query params:
    - engine: Override engine selection (auto|fast_pdf|markitdown|docling)

    Headers:
    - X-Request-ID: Optional correlation ID for request tracing
    """
    start_time = time.time()
    request_id = x_request_id or "no-id"

    logger.info(
        "[%s] EXTRACT_START: filename=%s, content_type=%s, engine=%s",
        request_id,
        file.filename,
        file.content_type,
        engine or "auto",
    )

    try:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        path = save_upload_to_disk(file, settings.UPLOAD_DIR)

        logger.info(
            "[%s] EXTRACT_PROCESSING: saved to %s",
            request_id,
            path,
        )

        # Run triage to determine engine
        from pathlib import Path as PPath
        triage_plan = await triage_service.triage(
            file_path=PPath(path),
            mime_type=file.content_type,
        )

        # Allow caller to override engine
        selected_engine = engine if engine and engine != "auto" else triage_plan["engine"]

        # Route to appropriate extraction engine
        content_md = ""
        method = "error"
        ocr_used = False
        page_count = None

        if selected_engine == "unsupported":
            elapsed_ms = int((time.time() - start_time) * 1000)
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported file format: {triage_plan['file_type']}. Request ID: {request_id}",
            )

        elif selected_engine == "fast_pdf":
            content_md, method, ocr_used, page_count = extract_pdf(
                path=path,
                filename=file.filename,
            )

        elif selected_engine == "docling":
            from ....services.docling_proxy_service import extract_via_docling
            content_md, method, ocr_used, page_count = await extract_via_docling(
                file_path=path,
                filename=file.filename,
                docling_params=triage_plan.get("docling_params"),
            )

        else:
            # markitdown (default for office/text/email)
            content_md, method, ocr_used, page_count = extract_markdown(
                path=path,
                filename=file.filename,
                media_type=file.content_type or "",
            )

        elapsed_ms = int((time.time() - start_time) * 1000)

        if not content_md:
            logger.warning(
                "[%s] EXTRACT_EMPTY: No content from %s via %s after %dms",
                request_id,
                file.filename,
                selected_engine,
                elapsed_ms,
            )
            raise HTTPException(
                status_code=422,
                detail=f"No text could be extracted from this file. Request ID: {request_id}",
            )

        # Extract document metadata
        doc_metadata = extract_document_metadata(
            path=path,
            filename=file.filename,
            content=content_md,
            extraction_method=method,
        )

        logger.info(
            "[%s] EXTRACT_SUCCESS: filename=%s, chars=%d, method=%s, engine=%s, elapsed=%dms",
            request_id,
            file.filename,
            len(content_md),
            method,
            selected_engine,
            elapsed_ms,
        )

        triage_info = TriageInfo(
            file_type=triage_plan["file_type"],
            engine=triage_plan["engine"],
            needs_ocr=triage_plan["needs_ocr"],
            needs_layout=triage_plan["needs_layout"],
            complexity=triage_plan["complexity"],
            triage_duration_ms=triage_plan.get("triage_duration_ms", 0),
            reason=triage_plan.get("reason", ""),
            page_count=triage_plan.get("page_count"),
            table_count=triage_plan.get("table_count"),
        )

        return ExtractionResult(
            filename=file.filename,
            content_markdown=content_md,
            content_chars=len(content_md),
            method=method,
            ocr_used=ocr_used,
            page_count=page_count,
            media_type=file.content_type,
            metadata={
                "upload_path": path,
                "request_id": request_id,
                "elapsed_ms": elapsed_ms,
                **doc_metadata,
            },
            triage=triage_info,
        )

    except HTTPException:
        raise
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "[%s] EXTRACT_ERROR: filename=%s, error=%s, elapsed=%dms",
            request_id,
            file.filename,
            str(e),
            elapsed_ms,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed: {str(e)}. Request ID: {request_id}",
        )
