"""
Models for the Document Service API.

Covers extraction (file -> markdown), triage routing, and document generation.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

class ExtractionOptions(BaseModel):
    """Options for document extraction (kept for API compatibility)."""
    ocr_fallback: bool = Field(default=False, description="Deprecated: OCR handled by Docling")
    force_ocr: bool = Field(default=False, description="Deprecated: OCR handled by Docling")
    ocr_lang: Optional[str] = None
    ocr_psm: Optional[str] = None


class TriageInfo(BaseModel):
    """Triage analysis included in extraction responses."""
    file_type: str
    engine: str
    needs_ocr: bool
    needs_layout: bool
    complexity: str
    triage_duration_ms: int = 0
    reason: str = ""
    page_count: Optional[int] = None
    table_count: Optional[int] = None


class ExtractionResult(BaseModel):
    """Result of document extraction."""
    filename: str
    content_markdown: str
    content_chars: int
    method: str  # "markitdown", "libreoffice+markitdown", "text", "email", "fast_pdf", "docling", "error"
    ocr_used: bool
    page_count: Optional[int] = None
    media_type: Optional[str] = None
    metadata: Dict = Field(default_factory=dict)
    triage: Optional[TriageInfo] = None


class SupportedFormats(BaseModel):
    """List of supported file extensions."""
    extensions: List[str]


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

class GeneratePdfRequest(BaseModel):
    """Request body for PDF generation."""
    content: str = Field(..., description="Markdown content to convert to PDF")
    title: Optional[str] = Field(None, description="Document title")
    css: Optional[str] = Field(None, description="Custom CSS (uses default if not provided)")
    include_title_page: bool = Field(False, description="Add a title page at the beginning")


class GenerateDocxRequest(BaseModel):
    """Request body for DOCX generation."""
    content: str = Field(..., description="Markdown content to convert to DOCX")
    title: Optional[str] = Field(None, description="Document title")


class GenerateCsvRequest(BaseModel):
    """Request body for CSV generation."""
    data: List[Dict[str, Any]] = Field(..., description="List of row dictionaries")
    columns: Optional[List[str]] = Field(None, description="Column names (auto-detected if omitted)")
    include_bom: bool = Field(True, description="Include UTF-8 BOM for Excel compatibility")


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

class DoclingStatus(BaseModel):
    """Docling service reachability status."""
    configured: bool
    reachable: Optional[bool] = None
    last_error: Optional[str] = None
    last_check_age_seconds: Optional[int] = None
    service_url: Optional[str] = None


class CapabilitiesResponse(BaseModel):
    """Service capabilities."""
    extraction_formats: List[str]
    generation_formats: List[str]
    triage_available: bool
    docling_available: bool
    docling: Optional[DoclingStatus] = None
