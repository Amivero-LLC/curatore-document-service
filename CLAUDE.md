# CLAUDE.md

Development guidance for Claude Code working with the Curatore Document Service.

## Project Overview

Stateless document format conversion service. Receives bytes, returns bytes. No database, no object storage, no orchestration.

### What it does
- **Extraction**: file -> markdown (Office, PDF, text, email)
- **Generation**: markdown/data -> file (PDF, DOCX, CSV)
- **Triage**: Lightweight analysis to route documents to optimal extraction engine

### Tech Stack
- **Framework**: FastAPI (Python 3.12+)
- **PDF Extraction**: PyMuPDF (fitz)
- **Office Extraction**: MarkItDown, LibreOffice (legacy formats)
- **PDF Generation**: WeasyPrint
- **DOCX Generation**: python-docx
- **Docling Proxy**: httpx (proxies to external IBM Docling service)

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run tests
pytest tests/ -v

# Run service
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload

# Docker build
docker build -t document-service .
docker run -p 8010:8010 document-service
```

## Project Structure

```
app/
├── main.py                     # FastAPI app + middleware
├── config.py                   # Settings (env vars)
├── models.py                   # Request/response models
├── middleware/api_key.py        # Bearer token auth
├── api/v1/routers/
│   ├── extract.py              # POST /api/v1/extract
│   ├── generate.py             # POST /api/v1/generate/{pdf,docx,csv}
│   └── system.py               # GET /health, /supported-formats, /capabilities
└── services/
    ├── extraction_service.py    # Office/text/email extraction (MarkItDown)
    ├── metadata_extractor.py    # Office metadata from ZIP/XML
    ├── pdf_extraction_service.py # PyMuPDF PDF extraction
    ├── triage_service.py        # Document analysis + engine routing
    ├── docling_proxy_service.py # Proxy to external Docling service
    ├── docling_health_service.py # Docling reachability monitoring (periodic probe)
    └── generation_service.py    # PDF/DOCX/CSV generation
```

## Key APIs

```
POST /api/v1/extract           # File upload -> markdown extraction
POST /api/v1/generate/pdf      # Markdown -> PDF bytes
POST /api/v1/generate/docx     # Markdown -> DOCX bytes
POST /api/v1/generate/csv      # Data -> CSV bytes
GET  /api/v1/system/health     # Health check (no auth)
GET  /api/v1/system/capabilities # Service capabilities (no auth)
```

## Configuration

Key environment variables (see `.env.example` for full list):

| Variable | Default | Purpose |
|----------|---------|---------|
| `SERVICE_API_KEY` | (none) | Bearer token for auth. Unset = dev mode |
| `DOCLING_SERVICE_URL` | (none) | Docling service URL. Unset = disabled |
| `UPLOAD_DIR` | `/tmp/document_uploads` | Temp file directory |
| `MAX_FILE_SIZE` | `52428800` | Max upload size (50MB) |
| `DOCLING_TIMEOUT` | `300` | Docling request timeout (seconds) |
| `DOCLING_VERIFY_SSL` | `true` | Verify SSL for Docling calls |

## Testing

Tests are in `tests/`. Run with `pytest tests/ -v`.

Some tests skip when optional dependencies are missing (WeasyPrint, PyMuPDF, etc.).
The Docling proxy tests use mocked httpx - no real Docling service needed.
Auth middleware tests use `monkeypatch` to set/unset `SERVICE_API_KEY`.

## CI

GitHub Actions workflow at `.github/workflows/ci.yml` runs on push/PR to `main`:
1. Installs system deps (LibreOffice, WeasyPrint libs)
2. Installs Python dependencies
3. Runs `pytest tests/ -v`

## Adding Features

### New extraction engine
1. Add service in `app/services/`
2. Add routing logic in `app/services/triage_service.py`
3. Wire into `app/api/v1/routers/extract.py`

### New generation format
1. Add method to `app/services/generation_service.py`
2. Add request model in `app/models.py`
3. Add endpoint in `app/api/v1/routers/generate.py`
