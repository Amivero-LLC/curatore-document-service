# Document Service Tests

## Running Tests

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_extraction.py -v
pytest tests/test_triage.py -v
pytest tests/test_generation.py -v
```

## Test Files

| File | What it tests |
|------|--------------|
| `test_extraction.py` | Manifest-based extraction for all formats (TXT, MD, DOCX, XLSX, PDF) |
| `test_extract_text.py` | Plain text extraction specifics |
| `test_pdf_extraction.py` | PyMuPDF PDF extraction (simple, multi-page, empty) |
| `test_triage.py` | Triage routing logic for all file types |
| `test_generation.py` | PDF, DOCX, CSV generation |
| `test_api_key_middleware.py` | API key auth (dev mode, valid/invalid keys, bypass) |
| `test_docling_proxy.py` | Docling proxy with mocked httpx |
| `test_system.py` | Health, supported-formats, capabilities endpoints |

## Test Fixtures

- `fixtures_docs.py` — Builds minimal DOCX, XLSX, and PDF files in-memory
- `conftest.py` — Auto-materializes test documents before test session

## Environment-Dependent Tests

Some tests are skipped if dependencies are not available:
- `markitdown` — Office document extraction
- `fitz` (PyMuPDF) — PDF extraction and triage
- `weasyprint` — PDF generation
- `docx` (python-docx) — DOCX generation
