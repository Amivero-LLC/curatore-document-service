"""
Configuration for the Document Service.

Handles all document format conversion:
- Extraction: file -> markdown (Office, PDF, text, email, with triage + Docling proxy)
- Generation: markdown/data -> file (PDF, DOCX, CSV)
"""

import os
from typing import List

from pydantic import BaseModel, Field


class Settings(BaseModel):
    # API
    API_TITLE: str = Field(default="Curatore Document Service")
    API_VERSION: str = Field(default="1.0.0")
    DEBUG: bool = Field(default=os.getenv("DEBUG", "false").lower() == "true")

    # Auth
    SERVICE_API_KEY: str = Field(default=os.getenv("SERVICE_API_KEY", ""))

    # CORS
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    CORS_CREDENTIALS: bool = True
    CORS_METHODS: List[str] = Field(default_factory=lambda: ["*"])
    CORS_HEADERS: List[str] = Field(default_factory=lambda: ["*"])

    # File Upload Limits
    MAX_FILE_SIZE: int = Field(default=int(os.getenv("MAX_FILE_SIZE", "52428800")))  # 50MB

    # Upload Directory
    UPLOAD_DIR: str = Field(default=os.getenv("UPLOAD_DIR", "/tmp/document_uploads"))

    # Docling Service
    DOCLING_SERVICE_URL: str = Field(default=os.getenv("DOCLING_SERVICE_URL", ""))
    DOCLING_TIMEOUT: int = Field(default=int(os.getenv("DOCLING_TIMEOUT", "300")))
    DOCLING_VERIFY_SSL: bool = Field(
        default=os.getenv("DOCLING_VERIFY_SSL", "true").lower() == "true"
    )

    # PDF triage thresholds
    PDF_BLOCK_THRESHOLD: int = Field(
        default=int(os.getenv("PDF_BLOCK_THRESHOLD", "50"))
    )
    PDF_IMAGE_THRESHOLD: int = Field(
        default=int(os.getenv("PDF_IMAGE_THRESHOLD", "3"))
    )
    PDF_PAGES_TO_ANALYZE: int = Field(
        default=int(os.getenv("PDF_PAGES_TO_ANALYZE", "3"))
    )

    # Office size threshold for Docling routing (bytes)
    OFFICE_SIZE_THRESHOLD: int = Field(
        default=int(os.getenv("OFFICE_SIZE_THRESHOLD", str(5 * 1024 * 1024)))  # 5MB
    )


settings = Settings()
