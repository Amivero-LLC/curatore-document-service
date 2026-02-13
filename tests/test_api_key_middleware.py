"""Tests for API key authentication middleware."""

import io
import tempfile

from fastapi.testclient import TestClient


def get_client():
    from app.main import app
    return TestClient(app)


def test_health_always_accessible(monkeypatch):
    """Health endpoint should not require auth even when key is set."""
    from app import config
    monkeypatch.setattr(config.settings, "SERVICE_API_KEY", "secret123", raising=True)

    client = get_client()
    r = client.get("/api/v1/system/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_dev_mode_no_key_required(monkeypatch):
    """When SERVICE_API_KEY is empty, all requests pass (dev mode)."""
    from app import config
    monkeypatch.setattr(config.settings, "SERVICE_API_KEY", "", raising=True)

    client = get_client()
    r = client.get("/api/v1/system/capabilities")
    assert r.status_code == 200


def test_valid_key_accepted(monkeypatch):
    """Valid bearer token should pass."""
    from app import config
    monkeypatch.setattr(config.settings, "SERVICE_API_KEY", "test-key-123", raising=True)

    client = get_client()
    r = client.get(
        "/api/v1/system/capabilities",
        headers={"Authorization": "Bearer test-key-123"},
    )
    assert r.status_code == 200


def test_invalid_key_rejected(monkeypatch):
    """Invalid bearer token should return 401."""
    from app import config
    monkeypatch.setattr(config.settings, "SERVICE_API_KEY", "correct-key", raising=True)

    client = get_client()
    r = client.get(
        "/api/v1/system/capabilities",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert r.status_code == 401


def test_missing_auth_header_rejected(monkeypatch):
    """Missing Authorization header should return 401 when key is configured."""
    from app import config
    monkeypatch.setattr(config.settings, "SERVICE_API_KEY", "my-key", raising=True)

    client = get_client()
    r = client.get("/api/v1/system/capabilities")
    assert r.status_code == 401


def test_non_bearer_auth_rejected(monkeypatch):
    """Non-Bearer auth scheme should return 401."""
    from app import config
    monkeypatch.setattr(config.settings, "SERVICE_API_KEY", "my-key", raising=True)

    client = get_client()
    r = client.get(
        "/api/v1/system/capabilities",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert r.status_code == 401


def test_extract_requires_key(monkeypatch):
    """Extract endpoint should require auth when key is set."""
    from app import config
    monkeypatch.setattr(config.settings, "SERVICE_API_KEY", "secret", raising=True)

    client = get_client()
    files = {"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")}
    r = client.post("/api/v1/extract", files=files)
    assert r.status_code == 401

    # With valid key it should work
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(config.settings, "UPLOAD_DIR", tmpdir, raising=True)
        files = {"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")}
        r = client.post(
            "/api/v1/extract",
            files=files,
            headers={"Authorization": "Bearer secret"},
        )
        assert r.status_code == 200
