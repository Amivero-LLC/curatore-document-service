# Document Service API Reference

Base URL: `http://localhost:8010/api/v1`

## Authentication

Set `SERVICE_API_KEY` env var to enable auth. When set, all requests (except health) require:

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
    "upload_path": "/tmp/document_uploads/document.pdf",
    "request_id": "abc-123",
    "elapsed_ms": 150,
    "file_info": { "filename": "document.pdf", "extension": ".pdf", "size_bytes": 50000 },
    "content_info": { "character_count": 1234, "word_count": 200 },
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

**Response 401**: Missing/invalid API key

**Response 422**: Unsupported format or no content extracted

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

**Response 200**: Raw PDF bytes (`Content-Type: application/pdf`)

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

**Response 200**: Raw DOCX bytes (`Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`)

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

**Response 200**: Raw CSV bytes (`Content-Type: text/csv`)

**Response 422**: Empty data with no columns

---

## System (no auth required)

### GET /api/v1/system/health

```json
{"status": "ok", "service": "document-service"}
```

### GET /api/v1/system/supported-formats

```json
{"extensions": [".csv", ".doc", ".docx", ".eml", ...]}
```

### GET /api/v1/system/capabilities

```json
{
  "extraction_formats": [".csv", ".doc", ".docx", ...],
  "generation_formats": ["pdf", "docx", "csv"],
  "triage_available": true,
  "docling_available": false
}
```
