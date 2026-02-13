from fastapi import APIRouter

from ....config import settings
from ....models import CapabilitiesResponse, DoclingStatus, SupportedFormats
from ....services.docling_health_service import docling_health_service
from ....services.extraction_service import SUPPORTED_EXTS

router = APIRouter(prefix="/system", tags=["system"])

# All formats handled by this service (including PDF via fast_pdf/docling)
ALL_EXTRACTION_EXTS = sorted(list(SUPPORTED_EXTS | {".pdf"}))


@router.get("/health")
async def health():
    if docling_health_service.is_configured and docling_health_service.needs_recheck():
        await docling_health_service.check_health()

    result = {"status": "ok", "service": "document-service"}

    status = docling_health_service.get_status()
    result["docling"] = status

    return result


@router.get("/supported-formats", response_model=SupportedFormats)
def supported_formats():
    return SupportedFormats(extensions=ALL_EXTRACTION_EXTS)


@router.get("/capabilities", response_model=None)
async def capabilities():
    if docling_health_service.is_configured and docling_health_service.needs_recheck():
        await docling_health_service.check_health()

    status = docling_health_service.get_status()

    return {
        "extraction_formats": ALL_EXTRACTION_EXTS,
        "generation_formats": ["pdf", "docx", "csv"],
        "triage_available": True,
        "docling_available": docling_health_service.docling_enabled,
        "docling": status,
    }
