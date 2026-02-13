"""
Docling health service.

Tracks reachability of the external Docling service with TTL-based caching.
No background threads — rechecks happen lazily when the TTL expires.
"""

import logging
import time
from typing import Optional

import httpx

from ..config import settings

logger = logging.getLogger("document_service.docling_health")

# Default TTL for health check cache (seconds)
_DEFAULT_TTL = 60


class DoclingHealthService:
    """Singleton that tracks Docling service reachability."""

    def __init__(self, ttl: int = _DEFAULT_TTL):
        self._ttl = ttl
        self._is_reachable: Optional[bool] = None
        self._last_check_time: Optional[float] = None  # monotonic
        self._last_error: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        return bool(settings.DOCLING_SERVICE_URL)

    @property
    def is_reachable(self) -> Optional[bool]:
        return self._is_reachable

    @property
    def docling_enabled(self) -> bool:
        """True only if configured AND (reachable OR never-checked).

        The never-checked case is optimistic so requests arriving before
        the startup probe completes can still attempt Docling.
        """
        if not self.is_configured:
            return False
        if self._is_reachable is None:
            return True  # optimistic before first check
        return self._is_reachable

    def needs_recheck(self) -> bool:
        if not self.is_configured:
            return False
        if self._last_check_time is None:
            return True
        return (time.monotonic() - self._last_check_time) >= self._ttl

    def invalidate(self) -> None:
        """Reset the TTL timer to force a recheck on next call."""
        self._last_check_time = None

    async def check_health(self, force: bool = False) -> bool:
        """Ping Docling and cache the result.

        Args:
            force: If True, ignore TTL and always ping.

        Returns:
            True if Docling responded successfully.
        """
        if not self.is_configured:
            self._is_reachable = False
            self._last_error = "DOCLING_SERVICE_URL not configured"
            self._last_check_time = time.monotonic()
            return False

        if not force and not self.needs_recheck():
            return self._is_reachable or False

        service_url = settings.DOCLING_SERVICE_URL.rstrip("/")

        try:
            async with httpx.AsyncClient(
                timeout=5.0,
                verify=settings.DOCLING_VERIFY_SSL,
            ) as client:
                # Try /health first, fall back to /openapi.json
                for path in ["/health", "/openapi.json"]:
                    try:
                        resp = await client.get(f"{service_url}{path}")
                        if resp.status_code < 500:
                            self._is_reachable = True
                            self._last_error = None
                            self._last_check_time = time.monotonic()
                            logger.info(
                                "Docling health check OK via %s (status %d)",
                                path,
                                resp.status_code,
                            )
                            return True
                    except (httpx.ConnectError, httpx.ConnectTimeout):
                        raise  # connection-level errors → don't retry other paths
                    except httpx.HTTPError:
                        continue

                # Both paths failed with non-exception status
                self._is_reachable = False
                self._last_error = "All health endpoints returned 5xx"
                self._last_check_time = time.monotonic()
                return False

        except httpx.ConnectError as e:
            self._is_reachable = False
            self._last_error = f"Connection refused: {e}"
            self._last_check_time = time.monotonic()
            logger.warning("Docling unreachable: %s", self._last_error)
            return False
        except Exception as e:
            self._is_reachable = False
            self._last_error = str(e)
            self._last_check_time = time.monotonic()
            logger.warning("Docling health check failed: %s", self._last_error)
            return False

    def get_status(self) -> dict:
        """Return status dict for API responses."""
        result = {
            "configured": self.is_configured,
            "reachable": self._is_reachable,
            "last_error": self._last_error,
            "last_check_age_seconds": None,
            "service_url": settings.DOCLING_SERVICE_URL or None,
        }
        if self._last_check_time is not None:
            result["last_check_age_seconds"] = int(
                time.monotonic() - self._last_check_time
            )
        return result


# Module-level singleton
docling_health_service = DoclingHealthService()
