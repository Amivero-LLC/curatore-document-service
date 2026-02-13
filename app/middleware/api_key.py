"""
API key authentication middleware.

Bearer token auth. Skips health endpoints. Pass-through if no key configured (dev mode).
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..config import settings

logger = logging.getLogger("document_service.auth")

# Paths that never require authentication
SKIP_PATHS = {
    "/api/v1/system/health",
    "/health",
    "/api/v1/docs",
    "/api/v1/openapi.json",
    "/api/v1/redoc",
}


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Bearer token auth. Skip health endpoints. Pass-through if no key configured (dev mode)."""

    async def dispatch(self, request: Request, call_next):
        # Skip auth for excluded paths
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        # Dev mode: no key configured → pass all requests
        if not settings.SERVICE_API_KEY:
            return await call_next(request)

        # Validate Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header. Expected: Bearer <token>"},
            )

        token = auth_header[7:]  # Strip "Bearer " prefix
        if token != settings.SERVICE_API_KEY:
            logger.warning("Invalid API key from %s", request.client.host if request.client else "unknown")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid API key"},
            )

        return await call_next(request)
