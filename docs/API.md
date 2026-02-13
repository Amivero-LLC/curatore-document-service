# Document Service API Reference

Base URL: `http://localhost:8010/api/v1`

## Authentication

Set `SERVICE_API_KEY` env var to enable auth. When set, all requests (except health/system) require:

```
Authorization: Bearer <SERVICE_API_KEY>
```

When unset, all requests pass (dev mode).

---

## Extraction

### POST /api/v1/extract

Extract text content from a document file.

**Auth**: Required (when key configured)

**Content-Type**: `multipart/form-data`

**Parameters**:
| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `file` | file | body | Document file to extract |
| `engine` | string | query | Engine override: `auto`, `fast_pdf`, `markitdown`, `docling`. Default: `auto` |
| `X-Request-ID` | string | header | Optional correlation ID |

**Response 200**:
```json
{
  "filename": "document.pdf",
  "content_markdown": "# Title\n\nExtracted content...",
  "content_chars": 1234,
  "method": "fast_pdf",
  "ocr_used": false,
  "page_count": 5,
  "media_type": "application/pdf",
  "metadata": {
    "request_id": "abc-123",
    "elapsed_ms": 150,
    "file_info": { "filename": "document.pdf", "extension": ".pdf", "size_bytes": 50000 },
    "content_info": { "character_count": 1234, "word_count": 200, "line_count": 50 },
    "extraction_info": { "method": "fast_pdf", "timestamp": "2024-01-01T00:00:00Z" }
  },
  "triage": {
    "file_type": ".pdf",
    "engine": "fast_pdf",
    "needs_ocr": false,
    "needs_layout": false,
    "complexity": "low",
    "triage_duration_ms": 5,
    "reason": "Simple text-based PDF (500 chars/page, 10 blocks/page)"
  }
}
```

**Error Responses**:

| Status | Meaning | When |
|--------|---------|------|
| 401 | Unauthorized | Missing or invalid `Authorization: Bearer` token |
| 422 | Unprocessable Entity | Unsupported file format, or no text could be extracted |
| 500 | Internal Server Error | Unexpected extraction failure |

**Response 401**:
```json
{"detail": "Missing Authorization header"}
```

**Response 422**:
```json
{"detail": "No text could be extracted from this file. Request ID: abc-123"}
```

**Response 500**:
```json
{"detail": "Extraction failed: <error message>. Request ID: abc-123"}
```

---

## Generation

### POST /api/v1/generate/pdf

Generate a PDF from markdown content.

**Auth**: Required

**Content-Type**: `application/json`

**Request body**:
```json
{
  "content": "# Hello\n\nWorld",
  "title": "My Document",
  "css": null,
  "include_title_page": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | yes | Markdown content to convert |
| `title` | string | no | Document title |
| `css` | string | no | Custom CSS (uses default styling if omitted) |
| `include_title_page` | bool | no | Add a title page at the beginning (default: false) |

**Response 200**: Raw PDF bytes (`Content-Type: application/pdf`)

**Response 500**:
```json
{"detail": "WeasyPrint is not installed"}
```

---

### POST /api/v1/generate/docx

Generate a DOCX from markdown content.

**Auth**: Required

**Content-Type**: `application/json`

**Request body**:
```json
{
  "content": "# Report\n\n- Item 1\n- Item 2",
  "title": "Report"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | yes | Markdown content to convert |
| `title` | string | no | Document title |

**Response 200**: Raw DOCX bytes (`Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`)

**Response 500**:
```json
{"detail": "python-docx is not installed"}
```

---

### POST /api/v1/generate/csv

Generate a CSV from structured data.

**Auth**: Required

**Content-Type**: `application/json`

**Request body**:
```json
{
  "data": [
    {"name": "Alice", "age": 30},
    {"name": "Bob", "age": 25}
  ],
  "columns": ["name", "age"],
  "include_bom": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `data` | array | yes | List of row dictionaries |
| `columns` | array | no | Column names and order (auto-detected from data keys if omitted) |
| `include_bom` | bool | no | Include UTF-8 BOM for Excel compatibility (default: true) |

**Response 200**: Raw CSV bytes (`Content-Type: text/csv`)

**Response 422**:
```json
{"detail": "No data and no columns provided; cannot generate CSV."}
```

---

## System (no auth required)

### GET /api/v1/system/health

Returns service health status, including Docling reachability when configured.

**Response 200**:
```json
{
  "status": "ok",
  "service": "document-service",
  "docling": {
    "configured": true,
    "reachable": true,
    "last_error": null,
    "last_check_age_seconds": 30,
    "service_url": "http://docling:8080"
  }
}
```

### GET /api/v1/system/supported-formats

Returns all file extensions supported for extraction.

**Response 200**:
```json
{"extensions": [".csv", ".doc", ".docx", ".eml", ".htm", ".html", ".json", ".md", ".msg", ".pdf", ".ppt", ".pptx", ".txt", ".xls", ".xlsb", ".xlsx", ".xml"]}
```

### GET /api/v1/system/capabilities

Returns full service capabilities including extraction formats, generation formats, and Docling status.

**Response 200**:
```json
{
  "extraction_formats": [".csv", ".doc", ".docx", ".eml", ...],
  "generation_formats": ["pdf", "docx", "csv"],
  "triage_available": true,
  "docling_available": false,
  "docling": {
    "configured": false,
    "reachable": null,
    "last_error": null,
    "last_check_age_seconds": null,
    "service_url": null
  }
}
```
