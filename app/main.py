import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1.routers import extract as extract_router
from .api.v1.routers import generate as generate_router
from .api.v1.routers import system as system_router
from .config import settings
from .middleware.api_key import ApiKeyMiddleware
from .services.docling_health_service import docling_health_service

logger = logging.getLogger("document_service.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: probe Docling reachability
    if docling_health_service.is_configured:
        reachable = await docling_health_service.check_health(force=True)
        if reachable:
            logger.info("Docling service is reachable at %s", settings.DOCLING_SERVICE_URL)
        else:
            status = docling_health_service.get_status()
            logger.warning(
                "Docling service is UNREACHABLE at %s: %s",
                settings.DOCLING_SERVICE_URL,
                status.get("last_error", "unknown"),
            )
    else:
        logger.info("Docling service not configured (DOCLING_SERVICE_URL is empty)")
    yield


app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    debug=settings.DEBUG,
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    lifespan=lifespan,
)

# Middleware (order matters: first added = outermost)
app.add_middleware(ApiKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_CREDENTIALS,
    allow_methods=settings.CORS_METHODS,
    allow_headers=settings.CORS_HEADERS,
)

# Versioned API routers
app.include_router(system_router.router, prefix="/api/v1")
app.include_router(extract_router.router, prefix="/api/v1")
app.include_router(generate_router.router, prefix="/api/v1")
