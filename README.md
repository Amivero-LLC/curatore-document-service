# Curatore Document Service

Stateless document format conversion service for the Curatore AI Data Platform. Handles all document extraction (file -> markdown) and generation (markdown/data -> file) use cases.

## Features

- **Extraction**: Convert documents to Markdown
  - Office files (DOCX, PPTX, XLSX, DOC, PPT, XLS) via MarkItDown
  - PDFs via PyMuPDF (fast_pdf) with intelligent triage routing
  - Text files (TXT, MD, CSV, HTML, XML, JSON) via direct read
  - Email files (MSG, EML) via extract-msg
  - Complex documents via Docling proxy (optional)
- **Generation**: Create documents from content
  - PDF from Markdown (via WeasyPrint)
  - DOCX from Markdown (via python-docx)
  - CSV from structured data
- **Triage**: Intelligent document analysis for optimal engine selection
- **API Key Auth**: Bearer token authentication with dev mode bypass

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

### Docker

```bash
docker build -t document-service .
docker run -p 8010:8010 document-service
```

## API

### Extraction

```bash
# Extract text from a document
curl -X POST http://localhost:8010/api/v1/extract \
  -F "file=@document.pdf"

# Force a specific engine
curl -X POST "http://localhost:8010/api/v1/extract?engine=fast_pdf" \
  -F "file=@document.pdf"
```

### Generation

```bash
# Generate PDF
curl -X POST http://localhost:8010/api/v1/generate/pdf \
  -H "Content-Type: application/json" \
  -d '{"content": "# Hello\n\nWorld"}' -o output.pdf

# Generate DOCX
curl -X POST http://localhost:8010/api/v1/generate/docx \
  -H "Content-Type: application/json" \
  -d '{"content": "# Report", "title": "My Report"}' -o output.docx

# Generate CSV
curl -X POST http://localhost:8010/api/v1/generate/csv \
  -H "Content-Type: application/json" \
  -d '{"data": [{"name": "Alice", "age": 30}]}' -o output.csv
```

### System

```bash
# Health check
curl http://localhost:8010/api/v1/system/health

# Capabilities
curl http://localhost:8010/api/v1/system/capabilities
```

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `SERVICE_API_KEY` | (none) | Bearer token for auth. Unset = dev mode (no auth) |
| `DOCLING_SERVICE_URL` | (none) | External Docling service URL. Unset = disabled |
| `UPLOAD_DIR` | `/tmp/document_uploads` | Temp file directory |
| `MAX_FILE_SIZE` | `52428800` | Max upload size in bytes (50MB) |
| `DEBUG` | `false` | Enable debug logging |

See `.env.example` for the complete list.

## Architecture

This service is **stateless** — it receives bytes and returns bytes. The Curatore backend remains the sole owner of MinIO/S3, database, and orchestration.

```
Upload → Triage → Engine Selection → Extraction → Markdown Response
                     ↓
              fast_pdf (PyMuPDF)
              markitdown (Office/text)
              docling (complex PDFs, via proxy)

Markdown/Data → Generation → PDF/DOCX/CSV bytes
```

## Documentation

- [API Reference](docs/API.md)
- [Test Documentation](tests/README.md)
- [Development Guide](CLAUDE.md)
