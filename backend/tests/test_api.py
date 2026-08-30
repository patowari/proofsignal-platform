"""API tests.

Endpoint behavior that does not need a database runs here in the default suite.
Tests touching PostgreSQL are marked `integration`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Rate limits would otherwise make repeated test runs flaky.
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()
    return TestClient(create_app())


class TestHealth:
    def test_health_is_cheap_and_ok(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["version"]

    def test_openapi_is_generated(self, client: TestClient) -> None:
        response = client.get("/api/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        for expected in (
            "/api/health",
            "/api/ready",
            "/api/submissions/text",
            "/api/submissions/url",
            "/api/submissions/image",
            "/api/submissions/video",
            "/api/verifications/{public_id}",
            "/api/verifications/{public_id}/status",
            "/api/verifications/{public_id}/claims",
            "/api/verifications/{public_id}/evidence",
            "/api/recent",
        ):
            assert expected in paths, f"missing route: {expected}"


class TestPublicIdValidation:
    """Malformed ids must be rejected before reaching a query."""

    @pytest.mark.parametrize(
        "bad_id",
        [
            "not-an-id",
            "1",
            "sub_wrongprefix12345",
            "vfy_short",
            "../../etc/passwd",
            "vfy_" + "A" * 100,
        ],
    )
    def test_malformed_ids_rejected(self, client: TestClient, bad_id: str) -> None:
        response = client.get(f"/api/verifications/{bad_id}")
        assert response.status_code in (400, 404, 422)

    def test_error_envelope_shape(self, client: TestClient) -> None:
        """One envelope shape everywhere, so the frontend never guesses."""
        body = client.get("/api/verifications/not-an-id").json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]


class TestSubmissionValidation:
    def test_empty_text_rejected(self, client: TestClient) -> None:
        assert client.post("/api/submissions/text", json={"text": ""}).status_code == 422

    def test_too_short_text_rejected(self, client: TestClient) -> None:
        assert client.post("/api/submissions/text", json={"text": "hi"}).status_code == 422

    def test_whitespace_only_text_rejected(self, client: TestClient) -> None:
        response = client.post("/api/submissions/text", json={"text": "          "})
        assert response.status_code == 422

    def test_missing_field_rejected(self, client: TestClient) -> None:
        assert client.post("/api/submissions/text", json={}).status_code == 422


class TestSSRFAtAPIBoundary:
    """SSRF must be blocked at the edge, before any work is queued."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/admin",
            "http://localhost:6379/",
            "http://169.254.169.254/latest/meta-data/",
            "http://192.168.1.1/",
            "http://10.0.0.1/",
            "file:///etc/passwd",
            "gopher://example.com/",
            "http://[::1]/",
            "http://2130706433/",
            "http://metadata.google.internal/",
        ],
    )
    def test_unsafe_urls_rejected(self, client: TestClient, url: str) -> None:
        response = client.post("/api/submissions/url", json={"url": url})
        assert response.status_code == 400, f"{url} was not rejected"
        assert response.json()["error"]["code"] in ("UNSAFE_URL", "VALIDATION_ERROR")

    def test_error_does_not_disclose_internal_detail(self, client: TestClient) -> None:
        """A prober must not learn which internal range they hit."""
        response = client.post(
            "/api/submissions/url", json={"url": "http://169.254.169.254/latest/meta-data/"}
        )
        message = response.json()["error"]["message"]
        assert "169.254" not in message
        assert "metadata" not in message.lower()


class TestUploadRejection:
    """Rejections must happen before storage or queueing."""

    def test_php_disguised_as_png_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/submissions/image",
            files={"file": ("evil.png", b"<?php system($_GET[0]); ?>", "image/png")},
        )
        assert response.status_code == 415

    def test_html_polyglot_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/submissions/image",
            files={"file": ("x.gif", b"GIF89a<html><script>alert(1)</script>", "image/gif")},
        )
        assert response.status_code == 415

    def test_empty_file_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/submissions/image", files={"file": ("empty.png", b"", "image/png")}
        )
        assert response.status_code in (400, 415)

    def test_image_rejected_as_video(self, client: TestClient, png_bytes: bytes) -> None:
        response = client.post(
            "/api/submissions/video", files={"file": ("fake.mp4", png_bytes, "video/mp4")}
        )
        assert response.status_code == 415


class TestCORS:
    def test_credentials_not_allowed(self, client: TestClient) -> None:
        """No auth means no credentialed cross-origin requests."""
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-credentials") != "true"


@pytest.mark.integration
class TestSubmissionFlow:
    """Full flow against a real database. Requires docker compose up."""

    def test_text_submission_creates_verification(self, client: TestClient) -> None:
        response = client.post(
            "/api/submissions/text",
            json={"text": "A 7.8 magnitude earthquake struck Japan today, killing 500 people."},
        )
        assert response.status_code == 202
        body = response.json()
        assert body["submission_public_id"].startswith("sub_")
        assert body["verification_public_id"].startswith("vfy_")
        assert body["status"] == "QUEUED"

    def test_status_endpoint_reports_real_stages(self, client: TestClient) -> None:
        created = client.post(
            "/api/submissions/text",
            json={"text": "The central bank raised interest rates by 0.5 percent yesterday."},
        ).json()

        response = client.get(f"/api/verifications/{created['verification_public_id']}/status")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in ("QUEUED", "RUNNING", "COMPLETED")
        assert body["stage_count"] > 0

    def test_unknown_id_returns_404(self, client: TestClient) -> None:
        response = client.get("/api/verifications/vfy_AAAAAAAAAAAAAAAA")
        assert response.status_code == 404

    def test_recent_returns_real_data_only(self, client: TestClient) -> None:
        response = client.get("/api/recent?limit=5")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["items"], list)
        # Whatever is returned must be real records, never placeholder content.
        for item in body["items"]:
            assert item["public_id"].startswith("vfy_")
