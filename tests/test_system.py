from fastapi.testclient import TestClient


def get_client():
    from app.main import app
    return TestClient(app)


def test_health_ok():
    client = get_client()
    r = client.get("/api/v1/system/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    assert body.get("service") == "document-service"


def test_supported_formats_nonempty():
    client = get_client()
    r = client.get("/api/v1/system/supported-formats")
    assert r.status_code == 200
    body = r.json()
    exts = body.get("extensions") or []
    assert isinstance(exts, list)
    assert len(exts) > 0
    assert ".docx" in exts
    assert ".pdf" in exts  # New: PDFs are now handled by this service


def test_capabilities():
    client = get_client()
    r = client.get("/api/v1/system/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert "extraction_formats" in body
    assert "generation_formats" in body
    assert ".pdf" in body["extraction_formats"]
    assert "pdf" in body["generation_formats"]
    assert "docx" in body["generation_formats"]
    assert "csv" in body["generation_formats"]
    assert body["triage_available"] is True
