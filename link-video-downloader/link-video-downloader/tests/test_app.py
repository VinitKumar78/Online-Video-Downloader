"""
tests/test_app.py
-------------------
Test suite covering:
  1. Input validation helpers (unit tests, no network required)
  2. Flask route behaviour for invalid input (unit/integration, no network)

Tests that would require actually calling yt-dlp against a live URL are
deliberately excluded — hitting real third-party services in a test suite
is slow and flaky. Route tests instead verify the app's own contract
(status codes, error shapes) for inputs it can reject without a network call.

Run with:
    pytest
"""

import shutil

import pytest

from app import create_app
from app.utils.validators import is_valid_url, sanitize_filename
from config import TestingConfig


@pytest.fixture
def app():
    application = create_app(TestingConfig)
    yield application
    shutil.rmtree(TestingConfig.DOWNLOAD_DIR, ignore_errors=True)


@pytest.fixture
def client(app):
    return app.test_client()


# -- Validators --------------------------------------------------------------

class TestIsValidUrl:
    def test_accepts_https_url(self):
        assert is_valid_url("https://www.youtube.com/watch?v=abc123") is True

    def test_accepts_http_url(self):
        assert is_valid_url("http://example.com/video") is True

    def test_rejects_empty_string(self):
        assert is_valid_url("") is False

    def test_rejects_none(self):
        assert is_valid_url(None) is False

    def test_rejects_missing_scheme(self):
        assert is_valid_url("www.youtube.com/watch?v=abc123") is False

    def test_rejects_scheme_without_host(self):
        assert is_valid_url("https://") is False


class TestSanitizeFilename:
    def test_removes_unsafe_characters(self):
        assert sanitize_filename('bad:name*here?') == "badnamehere"

    def test_truncates_long_names(self):
        long_name = "a" * 300
        assert len(sanitize_filename(long_name, max_length=150)) == 150

    def test_falls_back_to_default_for_empty_input(self):
        assert sanitize_filename("") == "video"

    def test_falls_back_when_only_unsafe_chars(self):
        assert sanitize_filename('***???') == "video"


# -- Routes -------------------------------------------------------------------

class TestHealthEndpoint:
    def test_returns_ok(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.get_json() == {"status": "ok"}


class TestIndexPage:
    def test_renders_successfully(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert b"Link" in response.data


class TestInfoEndpoint:
    def test_rejects_missing_url(self, client):
        response = client.post("/api/info", json={})
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_rejects_malformed_url(self, client):
        response = client.post("/api/info", json={"url": "not-a-url"})
        assert response.status_code == 400


class TestDownloadEndpoint:
    def test_rejects_missing_url(self, client):
        response = client.post("/api/download", json={})
        assert response.status_code == 400


class TestStatusEndpoint:
    def test_unknown_job_returns_404(self, client):
        response = client.get("/api/status/does-not-exist")
        assert response.status_code == 404


class TestFileEndpoint:
    def test_unknown_job_returns_404(self, client):
        response = client.get("/api/file/does-not-exist")
        assert response.status_code == 404
