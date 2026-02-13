from fastapi import APIRouter

from ....config import settings
from ....models import CapabilitiesResponse, SupportedFormats
from ....services.extraction_service import SUPPORTED_EXTS

router = APIRouter(prefix="/system", tags=["system"])

# All formats handled by this service (including PDF via fast_pdf/docling)
ALL_EXTRACTION_EXTS = sorted(list(SUPPORTED_EXTS | {".pdf"}))


@router.get("/health")
def health():
    return {"status": "ok", "service": "document-service"}


@router.get("/supported-formats", response_model=SupportedFormats)
def supported_formats():
    return SupportedFormats(extensions=ALL_EXTRACTION_EXTS)


@router.get("/capabilities", response_model=CapabilitiesResponse)
def capabilities():
    return CapabilitiesResponse(
        extraction_formats=ALL_EXTRACTION_EXTS,
        generation_formats=["pdf", "docx", "csv"],
        triage_available=True,
        docling_available=bool(settings.DOCLING_SERVICE_URL),
    )
