# Curatore Document Service

Stateless document format conversion microservice for the [Curatore AI Data Platform](https://github.com/your-org/curatore-v2). Handles all document extraction (file → markdown) and generation (markdown/data → file) as a standalone service.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Tech Stack & Frameworks](#tech-stack--frameworks)
- [Dependencies](#dependencies)
- [Extraction Engines](#extraction-engines)
- [Triage Process](#triage-process)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Quick Start](#quick-start)
- [Docker Deployment](#docker-deployment)
- [Network Architecture](#network-architecture)
- [Testing](#testing)
- [Documentation](#documentation)

---

## Architecture Overview

The Document Service is a **stateless** FastAPI microservice that receives bytes and returns bytes. It has no database, no object storage, and no orchestration logic. The Curatore backend remains the sole owner of MinIO/S3, PostgreSQL, and job orchestration.

```
                         ┌─────────────────────────────────────────────┐
                         │        Curatore Document Service            │
                         │              (port 8010)                    │
                         │                                             │
  ┌─────────────┐        │  ┌──────────────┐    ┌──────────────────┐  │
  │   Curatore   │  HTTP  │  │  API Key     │    │   FastAPI App    │  │
  │   Backend    │───────▶│  │  Middleware   │───▶│   (main.py)     │  │
  │  (port 8000) │        │  └──────────────┘    └────────┬─────┬──┘  │
  └─────────────┘        │                           │         │      │
                         │              ┌────────────┘         │      │
                         │              ▼                      ▼      │
                         │  ┌──────────────────┐  ┌────────────────┐  │
                         │  │  Extract Router   │  │ Generate Router│  │
                         │  │  POST /extract    │  │ POST /generate │  │
                         │  └────────┬─────────┘  └───────┬────────┘  │
                         │           │                     │          │
                         │           ▼                     ▼          │
                         │  ┌──────────────────┐  ┌────────────────┐  │
                         │  │  Triage Service   │  │  Generation    │  │
                         │  │  (engine select)  │  │  Service       │  │
                         │  └────────┬─────────┘  │  - WeasyPrint  │  │
                         │           │            │  - python-docx  │  │
                         │     ┌─────┼─────┐      │  - csv module  │  │
                         │     ▼     ▼     ▼      └────────────────┘  │
                         │  ┌─────┐┌────┐┌─────┐                      │
                         │  │fast ││Mark││Docl-│                      │
                         │  │_pdf ││It  ││ing  │──── HTTP ──▶ Docling │
                         │  │     ││Down││Proxy│          (external)  │
                         │  └─────┘└────┘└─────┘                      │
                         └─────────────────────────────────────────────┘
```

### Design Principles

1. **Stateless** — No database, no object storage, no file persistence. Temp files are cleaned up after each request.
2. **Single Responsibility** — Only handles format conversion. Orchestration, storage, and search remain in the backend.
3. **Engine Abstraction** — The triage layer selects the best engine automatically; callers can also override.
4. **Graceful Degradation** — If Docling is unavailable, triage falls back to fast_pdf or MarkItDown.
5. **Dev-Friendly Auth** — API key middleware passes all requests through when no key is configured.

### Request Flow

**Extraction** (`POST /api/v1/extract`):
1. File uploaded via multipart/form-data
2. Saved to temp disk (`UPLOAD_DIR`)
3. Triage service analyzes document (sub-second)
4. Routes to selected engine (fast_pdf, markitdown, or docling proxy)
5. Engine extracts text → markdown
6. Metadata extracted from document
7. JSON response with markdown, metadata, and triage info

**Generation** (`POST /api/v1/generate/{format}`):
1. JSON body with markdown content or structured data
2. Generation service converts to requested format
3. Raw bytes returned with appropriate Content-Type header

---

## Tech Stack & Frameworks

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Web Framework** | [FastAPI](https://fastapi.tiangolo.com/) 0.115.x | Async REST API with automatic OpenAPI docs |
| **ASGI Server** | [Uvicorn](https://www.uvicorn.org/) 0.27+ | High-performance async server with hot-reload |
| **Data Validation** | [Pydantic](https://docs.pydantic.dev/) 2.6+ | Request/response models with JSON Schema |
| **PDF Extraction** | [PyMuPDF (fitz)](https://pymupdf.readthedocs.io/) 1.24+ | Fast text extraction from PDFs, page analysis for triage |
| **Office Extraction** | [MarkItDown](https://github.com/microsoft/markitdown) 0.0.1+ | Microsoft's library for Office → Markdown (DOCX, PPTX, XLSX) |
| **Email Parsing** | [extract-msg](https://github.com/TeamMsgExtractor/msg-extractor) 0.48+ | Outlook .msg file parsing |
| **PDF Generation** | [WeasyPrint](https://weasyprint.org/) 60+ | HTML/CSS → PDF rendering engine |
| **DOCX Generation** | [python-docx](https://python-docx.readthedocs.io/) 1.1+ | Word document creation from structured content |
| **Markdown Rendering** | [markdown](https://python-markdown.github.io/) 3.5+ | Markdown → HTML for PDF generation pipeline |
| **HTTP Client** | [httpx](https://www.python-httpx.org/) 0.27+ | Async HTTP for Docling proxy calls |
| **File Detection** | [filetype](https://github.com/h2non/filetype.py) 1.2+ | Magic-byte file type identification |
| **Image Handling** | [Pillow](https://pillow.readthedocs.io/) 10+ | Image support for MarkItDown |
| **Spreadsheets** | [openpyxl](https://openpyxl.readthedocs.io/) 3.1+ | XLSX merged-cell preprocessing |
| **Runtime** | Python 3.12+ | Language runtime |
| **Container** | Docker (Debian slim) | Deployment with LibreOffice for legacy Office formats |

---

## Dependencies

### Production (`requirements.txt`)

```
# Web framework
fastapi>=0.115,<0.116          # REST API framework
uvicorn[standard]>=0.27,<0.31  # ASGI server (includes uvloop, httptools)
python-multipart>=0.0.9        # Multipart file upload parsing
pydantic>=2.6,<3               # Data validation

# Document extraction
markitdown[all]>=0.0.1         # Office files → Markdown
openpyxl>=3.1.0                # XLSX preprocessing
Pillow>=10.0.0                 # Image handling
extract-msg>=0.48.0            # Outlook .msg parsing
filetype>=1.2.0                # File type detection
pymupdf>=1.24.0                # PDF text extraction (PyMuPDF/fitz)

# Document generation
weasyprint>=60.0               # Markdown → PDF (via HTML/CSS)
python-docx>=1.1.0             # Markdown → DOCX
markdown>=3.5.0                # Markdown → HTML rendering

# Docling proxy
httpx>=0.27.0                  # Async HTTP client
```

### Development (`requirements-dev.txt`)

```
pytest>=8.0
httpx>=0.27.0                  # TestClient transport
```

### System Dependencies (Dockerfile)

```
libpango-1.0-0                 # WeasyPrint text layout
libpangocairo-1.0-0            # WeasyPrint Cairo integration
libgdk-pixbuf-2.0-0            # WeasyPrint image rendering
libffi-dev                     # Foreign function interface (cffi)
libcairo2                      # 2D graphics library
libreoffice-writer-nogui       # Legacy Office format conversion (.doc, .ppt, .xls)
fonts-dejavu-core              # Default fonts for PDF generation
curl                           # Container health checks
```

---

## Extraction Engines

| Engine | Library | Best For | Speed |
|--------|---------|----------|-------|
| **fast_pdf** | PyMuPDF (fitz) | Simple text-based PDFs | Fast (< 1s) |
| **markitdown** | MarkItDown + LibreOffice | Office files, text, email | Fast (< 2s) |
| **docling** | IBM Docling (external) | Scanned PDFs, OCR, complex layouts, large Office files | Slow (5-60s) |

### Engine Selection

The extract router (`POST /api/v1/extract`) accepts an optional `?engine=` query parameter:

| Value | Behavior |
|-------|----------|
| `auto` (default) | Triage service analyzes document and selects optimal engine |
| `fast_pdf` | Force PyMuPDF extraction (PDFs only) |
| `markitdown` | Force MarkItDown extraction |
| `docling` | Force Docling proxy (requires `DOCLING_SERVICE_URL` configured) |

---

## Triage Process

The triage service (`app/services/triage_service.py`) performs lightweight document analysis to route each file to the optimal extraction engine. The entire process runs in **sub-second time** (typically < 10ms) and does not extract content — it only inspects file metadata and structure.

### Triage Decision Flow

```
                            ┌──────────────┐
                            │  File Upload  │
                            └──────┬───────┘
                                   │
                                   ▼
                         ┌──────────────────┐
                         │  Get Extension   │
                         │  (.pdf, .docx,   │
                         │   .txt, .png...) │
                         └────────┬─────────┘
                                  │
              ┌───────────────────┼───────────────────┐──────────────┐
              ▼                   ▼                   ▼              ▼
       ┌─────────────┐   ┌──────────────┐   ┌──────────────┐ ┌───────────┐
       │  Image?      │   │  PDF?        │   │  Office?     │ │  Text?    │
       │ .png/.jpg/.. │   │  .pdf        │   │ .docx/.xlsx/ │ │ .txt/.md/ │
       └──────┬──────┘   └──────┬───────┘   │ .pptx/...    │ │ .csv/...  │
              │                  │           └──────┬───────┘ └─────┬─────┘
              ▼                  ▼                  ▼               ▼
       ┌─────────────┐   ┌──────────────┐   ┌──────────────┐ ┌───────────┐
       │ UNSUPPORTED │   │  PDF Triage  │   │ Office Triage│ │ markitdown│
       │ (422 error) │   │  (PyMuPDF    │   │ (file size)  │ │ (direct)  │
       └─────────────┘   │  analysis)   │   └──────┬───────┘ └───────────┘
                         └──────┬───────┘          │
                                │                  │
              ┌─────────────────┤           ┌──────┴──────┐
              │                 │           │             │
              ▼                 ▼           ▼             ▼
     ┌────────────────┐ ┌────────────┐ ┌────────┐ ┌──────────┐
     │ Needs OCR?     │ │ Complex    │ │ < 5MB  │ │ >= 5MB   │
     │ (<100 chars/pg)│ │ layout?    │ │        │ │          │
     │                │ │ (blocks,   │ │        │ │          │
     │ ──▶ docling    │ │  images,   │ │──▶     │ │──▶       │
     │    (high)      │ │  tables)   │ │ markit-│ │ docling  │
     └────────────────┘ │            │ │ down   │ │ (medium) │
                        │ ──▶ docling│ │ (low)  │ └──────────┘
                        │   (medium) │ └────────┘
                        │            │
                        │  else ──▶  │
                        │  fast_pdf  │
                        │  (low)     │
                        └────────────┘

         ┌──────────────────────────────────────────────────┐
         │  DOCLING FALLBACK: If Docling is not available   │
         │  (DOCLING_SERVICE_URL not set), all "docling"    │
         │  decisions fall back to:                          │
         │    - PDFs ──▶ fast_pdf                           │
         │    - Office ──▶ markitdown                       │
         └──────────────────────────────────────────────────┘
```

### PDF Triage (detailed)

When a PDF is uploaded, the triage service opens it with PyMuPDF and analyzes the **first N pages** (default: 3, configured via `PDF_PAGES_TO_ANALYZE`):

| Metric | How Measured | Threshold |
|--------|-------------|-----------|
| **Text density** | Average characters per page | < 100 chars/page → needs OCR |
| **Block count** | Text/image blocks per page | > 50 blocks/page → complex layout |
| **Image count** | Embedded images per page | > 3 images/page → complex layout |
| **Table detection** | Drawing line count per page | > 20 drawing items → tables detected |

**Decision matrix:**

| Condition | Engine | Complexity |
|-----------|--------|------------|
| < 100 chars/page (needs OCR) | `docling` | high |
| > 50 blocks OR > 3 images OR tables | `docling` | medium |
| Otherwise | `fast_pdf` | low |

### Office Triage (detailed)

Office files are triaged by file size as a proxy for complexity:

| Condition | Engine | Complexity |
|-----------|--------|------------|
| File size >= 5MB (`OFFICE_SIZE_THRESHOLD`) | `docling` | medium |
| File size < 5MB | `markitdown` | low |

### Triage Response

Every extraction response includes a `triage` object:

```json
{
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

---

## API Reference

See [docs/API.md](docs/API.md) for the full API reference. Summary:

### Extraction
```
POST /api/v1/extract
  Auth: Authorization: Bearer <SERVICE_API_KEY>
  Body: multipart/form-data (file field)
  Query: ?engine=auto|fast_pdf|markitdown|docling
  Header: X-Request-ID (optional)
  Response 200: { filename, content_markdown, content_chars, method,
                  ocr_used, page_count, media_type, metadata, triage }
  Response 401: Missing/invalid API key
  Response 422: Unsupported format or no content extracted
```

### Generation
```
POST /api/v1/generate/pdf   → application/pdf
POST /api/v1/generate/docx  → application/vnd.openxmlformats-...wordprocessingml.document
POST /api/v1/generate/csv   → text/csv
  Auth: Bearer token
  Body: JSON (content, title, options vary by format)
```

### System (no auth required)
```
GET /api/v1/system/health            → { status, service }
GET /api/v1/system/supported-formats → { extensions }
GET /api/v1/system/capabilities      → { extraction_formats, generation_formats,
                                         triage_available, docling_available }
```

---

## Configuration

All configuration is via environment variables. See [.env.example](.env.example) for defaults.

| Variable | Default | Purpose |
|----------|---------|---------|
| `SERVICE_API_KEY` | _(none)_ | Bearer token for auth. Unset = dev mode (no auth) |
| `DEBUG` | `false` | Enable debug logging |
| `MAX_FILE_SIZE` | `52428800` | Max upload size in bytes (50MB) |
| `UPLOAD_DIR` | `/tmp/document_uploads` | Temp file directory |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | CORS allowed origins |
| `DOCLING_SERVICE_URL` | _(none)_ | External Docling URL. Unset = Docling disabled |
| `DOCLING_TIMEOUT` | `300` | Docling request timeout (seconds) |
| `DOCLING_VERIFY_SSL` | `true` | Verify SSL for Docling calls |
| `PDF_BLOCK_THRESHOLD` | `50` | Blocks/page threshold for complex PDF triage |
| `PDF_IMAGE_THRESHOLD` | `3` | Images/page threshold for complex PDF triage |
| `PDF_PAGES_TO_ANALYZE` | `3` | Number of pages to analyze during PDF triage |
| `OFFICE_SIZE_THRESHOLD` | `5242880` | File size (bytes) threshold for Office → Docling routing |

---

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run the service
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload

# Run tests
pytest tests/ -v
```

### Smoke Tests

```bash
# Health check
curl http://localhost:8010/api/v1/system/health

# Extract a PDF
curl -X POST http://localhost:8010/api/v1/extract -F "file=@document.pdf"

# Generate a PDF from markdown
curl -X POST http://localhost:8010/api/v1/generate/pdf \
  -H "Content-Type: application/json" \
  -d '{"content": "# Hello\n\nWorld"}' -o output.pdf
```

---

## Docker Deployment

### Standalone

```bash
docker build -t document-service .
docker run -p 8010:8010 --env-file .env document-service
```

### With Curatore (Docker Compose)

The document service runs as a **separate Docker Compose project** that connects to the Curatore stack via an external Docker network.

```bash
# 1. Create the shared network (one-time setup)
docker network create curatore-network

# 2. Start the document service
cd curatore-document-service
docker compose up -d

# 3. Start curatore-v2 (in a separate terminal)
cd curatore-v2
docker compose up -d
```

Both projects declare `curatore-network` as an `external: true` network, allowing containers to communicate by service name (e.g., `http://document-service:8010`).

---

## Network Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     curatore-network (external)                   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  curatore-v2 (docker-compose)                                │ │
│  │                                                               │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │ │
│  │  │ backend  │ │ worker   │ │ beat     │ │ frontend │       │ │
│  │  │ :8000    │ │          │ │          │ │ :3000    │       │ │
│  │  └────┬─────┘ └────┬─────┘ └──────────┘ └──────────┘       │ │
│  │       │             │                                        │ │
│  │  ┌────┴─────┐ ┌────┴─────┐ ┌──────────┐ ┌──────────┐       │ │
│  │  │ redis    │ │ minio    │ │ postgres │ │playwright│       │ │
│  │  │ :6379    │ │ :9000    │ │ :5432    │ │ :8011    │       │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  curatore-document-service (docker-compose)                  │ │
│  │                                                               │ │
│  │  ┌──────────────────┐                                        │ │
│  │  │ document-service  │  DNS: document-service                │ │
│  │  │ :8010             │  Container: curatore-document-service  │ │
│  │  └──────────────────┘                                        │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘

Communication:
  backend/worker → http://document-service:8010  (extraction + generation)
  backend/worker → Authorization: Bearer <EXTRACTION_SERVICE_API_KEY>
```

---

## Project Structure

```
curatore-document-service/
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI app + middleware registration
│   ├── config.py                        # Settings (env vars → Pydantic model)
│   ├── models.py                        # All request/response Pydantic models
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── api_key.py                   # Bearer token auth middleware
│   ├── api/v1/
│   │   ├── __init__.py
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── extract.py               # POST /api/v1/extract
│   │       ├── generate.py              # POST /api/v1/generate/{pdf,docx,csv}
│   │       └── system.py                # Health, supported-formats, capabilities
│   └── services/
│       ├── __init__.py
│       ├── extraction_service.py        # Office/text/email → Markdown (MarkItDown)
│       ├── metadata_extractor.py        # Office metadata from ZIP/XML headers
│       ├── pdf_extraction_service.py    # PDF → Markdown (PyMuPDF/fitz)
│       ├── triage_service.py            # Document analysis + engine routing
│       ├── docling_proxy_service.py     # Proxy to external Docling service (httpx)
│       └── generation_service.py        # Markdown/data → PDF/DOCX/CSV
├── tests/
│   ├── conftest.py                      # Fixtures, test client
│   ├── fixtures_docs.py                 # Test document builders
│   ├── test_extraction.py               # Manifest-based extraction tests
│   ├── test_extract_text.py             # Plain text extraction
│   ├── test_pdf_extraction.py           # PyMuPDF PDF extraction
│   ├── test_triage.py                   # Triage routing logic
│   ├── test_generation.py               # PDF/DOCX/CSV generation
│   ├── test_api_key_middleware.py        # API key auth tests
│   ├── test_docling_proxy.py            # Docling proxy (mocked)
│   ├── test_system.py                   # Health/capabilities
│   └── README.md                        # Test documentation
├── docs/
│   └── API.md                           # Detailed API reference
├── Dockerfile                           # Python 3.12 + LibreOffice + WeasyPrint deps
├── docker-compose.yml                   # Docker Compose with curatore-network
├── requirements.txt                     # Production dependencies
├── requirements-dev.txt                 # Test dependencies
├── pytest.ini                           # Pytest configuration
├── .env                                 # Local environment (not committed)
├── .env.example                         # Environment variable reference
├── .gitignore                           # Python + Docker ignores
├── CLAUDE.md                            # Development guidance for Claude Code
└── README.md                            # This file
```

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test files
pytest tests/test_triage.py -v
pytest tests/test_generation.py -v
pytest tests/test_extraction.py -v
```

Tests use FastAPI's `TestClient` (synchronous) with no external services required. Docling proxy tests use mocked `httpx` responses. Some tests skip when optional dependencies are missing (WeasyPrint system libraries, PyMuPDF).

See [tests/README.md](tests/README.md) for test documentation.

---

## Documentation

| Document | Description |
|----------|-------------|
| [README.md](README.md) | This file — architecture, setup, deployment |
| [docs/API.md](docs/API.md) | Detailed API reference with request/response examples |
| [tests/README.md](tests/README.md) | Test framework and coverage documentation |
| [CLAUDE.md](CLAUDE.md) | Development guidance for Claude Code |
| [.env.example](.env.example) | Environment variable reference with defaults |
