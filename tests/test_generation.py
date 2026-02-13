"""Tests for document generation (PDF, DOCX, CSV)."""

import importlib.util
import json

import pytest
from fastapi.testclient import TestClient


def get_client():
    from app.main import app
    return TestClient(app)


# ---- PDF ----

@pytest.mark.skipif(
    importlib.util.find_spec("weasyprint") is None,
    reason="weasyprint not available",
)
class TestPdfGeneration:
    def test_generate_pdf_basic(self):
        client = get_client()
        r = client.post(
            "/api/v1/generate/pdf",
            json={"content": "# Hello\n\nWorld"},
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:4] == b"%PDF"

    def test_generate_pdf_with_title(self):
        client = get_client()
        r = client.post(
            "/api/v1/generate/pdf",
            json={"content": "# Report", "title": "My Report", "include_title_page": True},
        )
        assert r.status_code == 200
        assert len(r.content) > 0

    def test_generate_pdf_empty_content(self):
        client = get_client()
        r = client.post(
            "/api/v1/generate/pdf",
            json={"content": ""},
        )
        # Empty markdown is still valid, WeasyPrint can generate a blank page
        assert r.status_code == 200


# ---- DOCX ----

@pytest.mark.skipif(
    importlib.util.find_spec("docx") is None,
    reason="python-docx not available",
)
class TestDocxGeneration:
    def test_generate_docx_basic(self):
        client = get_client()
        r = client.post(
            "/api/v1/generate/docx",
            json={"content": "# Title\n\n- Item 1\n- Item 2"},
        )
        assert r.status_code == 200
        ct = r.headers["content-type"]
        assert "wordprocessingml" in ct
        # DOCX files are ZIP archives starting with PK
        assert r.content[:2] == b"PK"

    def test_generate_docx_with_title(self):
        client = get_client()
        r = client.post(
            "/api/v1/generate/docx",
            json={"content": "Some text", "title": "My Doc"},
        )
        assert r.status_code == 200


# ---- CSV ----

class TestCsvGeneration:
    def test_generate_csv_basic(self):
        client = get_client()
        r = client.post(
            "/api/v1/generate/csv",
            json={
                "data": [
                    {"name": "Alice", "age": 30},
                    {"name": "Bob", "age": 25},
                ],
            },
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        text = r.content.decode("utf-8-sig")
        assert "Alice" in text
        assert "Bob" in text

    def test_generate_csv_with_columns(self):
        client = get_client()
        r = client.post(
            "/api/v1/generate/csv",
            json={
                "data": [{"x": 1, "y": 2, "z": 3}],
                "columns": ["x", "y"],
            },
        )
        assert r.status_code == 200
        text = r.content.decode("utf-8-sig")
        assert "x" in text
        assert "y" in text
        # z should be ignored since not in columns
        lines = text.strip().split("\n")
        assert "z" not in lines[0]

    def test_generate_csv_no_bom(self):
        client = get_client()
        r = client.post(
            "/api/v1/generate/csv",
            json={
                "data": [{"a": 1}],
                "include_bom": False,
            },
        )
        assert r.status_code == 200
        # Should NOT start with BOM
        assert not r.content.startswith(b"\xef\xbb\xbf")

    def test_generate_csv_empty_data_no_columns_fails(self):
        client = get_client()
        r = client.post(
            "/api/v1/generate/csv",
            json={"data": []},
        )
        assert r.status_code == 422
