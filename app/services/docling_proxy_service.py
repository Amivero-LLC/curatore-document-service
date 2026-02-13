"""
Docling proxy service.

Proxies extraction requests to an external IBM Docling Serve instance
for advanced document conversion with rich layout understanding.
"""

import logging
import mimetypes
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx

from ..config import settings

logger = logging.getLogger("document_service.docling_proxy")


# Cached detected endpoint
_detected_endpoint: Optional[str] = None


def _get_docling_params(
    endpoint: Optional[str] = None,
    triage_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Get Docling-specific conversion parameters.

    API Version Differences:
    - v1.9.0+: Uses /v1/convert/file with 'pipeline' parameter
    - v0.7.0 (alpha): Uses /v1alpha/convert/file, no 'pipeline' parameter

    Args:
        endpoint: The API endpoint path being used.
        triage_overrides: Optional overrides from triage analysis (e.g. do_ocr, table_mode).
    """
    endpoint_path = endpoint or "/v1/convert/file"
    is_alpha_api = "v1alpha" in endpoint_path

    params: Dict[str, Any] = {
        "to_formats": ["md"],
        "image_export_mode": "placeholder",
        "do_ocr": True,
        "ocr_engine": "easyocr",
        "table_mode": "accurate",
        "include_images": False,
    }

    if not is_alpha_api:
        params["pipeline"] = "standard"

    # Apply triage-driven overrides
    if triage_overrides:
        for key, value in triage_overrides.items():
            if key in params or key == "pdf_backend":
                params[key] = value

    return params


async def _detect_endpoint(client: httpx.AsyncClient) -> Optional[str]:
    """Detect Docling API endpoint using OpenAPI or probing."""
    global _detected_endpoint
    if _detected_endpoint:
        return _detected_endpoint

    service_url = settings.DOCLING_SERVICE_URL

    if "v1alpha" in service_url.lower():
        _detected_endpoint = "/v1alpha/convert/file"
        return _detected_endpoint

    # Try OpenAPI spec
    try:
        openapi_url = f"{service_url}/openapi.json"
        response = await client.get(openapi_url)
        if response.status_code == 200:
            payload = response.json()
            paths = payload.get("paths", {}) if isinstance(payload, dict) else {}
            if "/v1/convert/file" in paths:
                _detected_endpoint = "/v1/convert/file"
                return _detected_endpoint
            if "/v1alpha/convert/file" in paths:
                _detected_endpoint = "/v1alpha/convert/file"
                return _detected_endpoint
    except Exception:
        pass

    # Probe endpoints
    for endpoint in ["/v1/convert/file", "/v1alpha/convert/file"]:
        try:
            probe = await client.options(f"{service_url}{endpoint}")
            if probe.status_code != 404:
                _detected_endpoint = endpoint
                return _detected_endpoint
        except Exception:
            continue

    return None


def _build_endpoint_candidates(preferred: Optional[str]) -> list:
    """Return endpoint candidates ordered by preference."""
    candidates = ["/v1/convert/file", "/v1alpha/convert/file"]
    if preferred in candidates:
        return [preferred] + [c for c in candidates if c != preferred]
    return candidates


async def extract_via_docling(
    file_path: str,
    filename: str,
    max_retries: int = 2,
    docling_params: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, bool, Optional[int]]:
    """
    Proxy extraction to external Docling service.

    Args:
        file_path: Path to the document file
        filename: Original filename
        max_retries: Maximum number of retry attempts
        docling_params: Optional triage-driven parameter overrides (e.g. do_ocr, table_mode)

    Returns:
        (markdown_content, method, ocr_used, page_count)
    """
    service_url = settings.DOCLING_SERVICE_URL
    if not service_url:
        logger.error("DOCLING_SERVICE_URL not configured")
        return ("", "error", False, None)

    timeout_extension = 30.0
    path = Path(file_path)

    for attempt in range(max_retries + 1):
        current_timeout = settings.DOCLING_TIMEOUT + (attempt * timeout_extension)

        if attempt == 0:
            logger.info(
                "Using Docling: %s (timeout: %.0fs) for file: %s",
                service_url, current_timeout, filename
            )
        else:
            logger.info(
                "Retrying Docling (attempt %d/%d, timeout: %.0fs): %s",
                attempt + 1, max_retries + 1, current_timeout, filename
            )

        headers = {"Accept": "application/json"}

        try:
            async with httpx.AsyncClient(
                timeout=current_timeout,
                verify=settings.DOCLING_VERIFY_SSL,
            ) as client:
                mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

                async def _post_with(
                    endpoint_url: str,
                    params: Dict[str, Any],
                    field_name: str,
                ) -> httpx.Response:
                    """Helper to post file with specific field name."""
                    with path.open("rb") as f:
                        files = [(field_name, (path.name, f, mime))]
                        form_data = {}
                        for key, value in params.items():
                            if isinstance(value, list):
                                form_data[key] = value
                            elif isinstance(value, bool):
                                form_data[key] = str(value).lower()
                            else:
                                form_data[key] = str(value)
                        return await client.post(
                            endpoint_url,
                            headers=headers,
                            files=files,
                            data=form_data,
                        )

                detected = await _detect_endpoint(client)
                endpoints = _build_endpoint_candidates(detected)

                response = None
                used_url = service_url
                used_endpoint = endpoints[0]

                for endpoint in endpoints:
                    endpoint_url = f"{service_url}{endpoint}"
                    used_url = endpoint_url
                    used_endpoint = endpoint
                    params = _get_docling_params(endpoint=endpoint, triage_overrides=docling_params)

                    response = await _post_with(endpoint_url, params, "files")

                    if response.status_code == 404 and endpoint != endpoints[-1]:
                        logger.warning(
                            "Docling endpoint %s returned 404; trying next.",
                            endpoint,
                        )
                        continue

                    # Handle field name mismatches
                    if response.status_code == 422:
                        try:
                            body = response.json() or {}
                            needs_file = any(
                                any(str(x).lower() == "file" for x in (d.get("loc") or []))
                                for d in (body.get("detail") or [])
                            )
                            if needs_file:
                                logger.warning("Docling expects 'file' field. Retrying.")
                                response = await _post_with(endpoint_url, params, "file")
                        except Exception:
                            pass

                    break

                if response is None:
                    return ("", "error", False, None)

                response.raise_for_status()

                # Parse response
                content_type = response.headers.get("content-type", "").lower()
                markdown_content = None

                if "application/json" in content_type:
                    payload = response.json()
                    if isinstance(payload, dict):
                        doc = payload.get("document")
                        if isinstance(doc, dict):
                            md_val = doc.get("md_content")
                            if isinstance(md_val, str) and md_val.strip():
                                markdown_content = md_val
                            else:
                                txt_val = doc.get("text_content")
                                if isinstance(txt_val, str) and txt_val.strip():
                                    markdown_content = txt_val
                                    logger.info(
                                        "Using text_content (md_content not available) for %s",
                                        filename,
                                    )
                else:
                    markdown_content = response.text

                if markdown_content and markdown_content.strip():
                    ocr_was_used = params.get("do_ocr", True)
                    logger.info(
                        "Docling extraction successful: %d characters from %s (ocr=%s)",
                        len(markdown_content), filename, ocr_was_used,
                    )
                    return (markdown_content, "docling", ocr_was_used, None)
                else:
                    logger.warning("Docling returned empty content for %s", filename)

        except httpx.TimeoutException as e:
            logger.warning(
                "Docling timeout (attempt %d/%d) for %s: %s",
                attempt + 1, max_retries + 1, filename, str(e),
            )
            if attempt < max_retries:
                continue
            else:
                return ("", "error", False, None)

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            logger.error("Docling extraction failed for %s: %s", filename, error_msg)
            return ("", "error", False, None)

        except Exception as e:
            logger.error(
                "Docling error (attempt %d/%d) for %s: %s",
                attempt + 1, max_retries + 1, filename, str(e),
            )
            if attempt < max_retries:
                continue
            else:
                return ("", "error", False, None)

    return ("", "error", False, None)
