"""Tests for Story 2.2: API Incident Intake Endpoints."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "services" / "api"))

from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture(autouse=True)
def _reset_publisher():
    """Reset the global publisher before each test."""
    import src.adapters.inbound.fastapi_routes as routes_mod
    routes_mod.publisher = None
    yield
    routes_mod.publisher = None


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_publisher():
    mock = AsyncMock()
    mock.publish = AsyncMock(return_value="test-event-id")
    with patch("src.adapters.inbound.fastapi_routes.get_publisher", return_value=mock):
        yield mock


# ==========================================================================
# Domain validation tests
# ==========================================================================
class TestValidation:
    def test_validate_incident_empty_title(self):
        from src.domain.services import ValidationError, validate_incident
        with pytest.raises(ValidationError, match="Title is required"):
            validate_incident("")

    def test_validate_incident_whitespace_title(self):
        from src.domain.services import ValidationError, validate_incident
        with pytest.raises(ValidationError, match="Title is required"):
            validate_incident("   ")

    def test_validate_incident_valid_title(self):
        from src.domain.services import validate_incident
        validate_incident("Valid title")  # should not raise

    def test_validate_incident_allowed_image_type(self):
        from src.domain.services import validate_incident
        validate_incident("Title", file_content_type="image/png", file_size=100)

    def test_validate_incident_allowed_video_type(self):
        from src.domain.services import validate_incident
        validate_incident("Title", file_content_type="video/mp4", file_size=100)

    def test_validate_incident_allowed_text_type(self):
        from src.domain.services import validate_incident
        validate_incident("Title", file_content_type="text/plain", file_size=100)

    def test_validate_incident_disallowed_file_type(self):
        from src.domain.services import ValidationError, validate_incident
        with pytest.raises(ValidationError, match="not allowed"):
            validate_incident("Title", file_content_type="application/zip", file_size=100)

    def test_validate_incident_file_too_large(self):
        from src.domain.services import ValidationError, validate_incident
        with pytest.raises(ValidationError, match="50MB"):
            validate_incident("Title", file_size=51 * 1024 * 1024)


# ==========================================================================
# POST /api/incidents
# ==========================================================================
class TestCreateIncident:
    def test_success_minimal(self, client, mock_publisher):
        response = client.post("/api/incidents", data={"title": "Server is down"})
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "ok"
        assert "incident_id" in body["data"]
        assert body["data"]["message"] == "Incident received"
        mock_publisher.publish.assert_awaited_once()
        call_args = mock_publisher.publish.call_args
        assert call_args[0][0] == "incidents"
        assert call_args[0][1] == "incident.created"
        payload = call_args[0][2]
        assert payload["source_type"] == "userIntegration"

    def test_success_with_optional_fields(self, client, mock_publisher):
        response = client.post(
            "/api/incidents",
            data={
                "title": "DB timeout",
                "description": "Postgres connections exhausted",
                "component": "database",
                "severity": "high",
            },
        )
        assert response.status_code == 201
        payload = mock_publisher.publish.call_args[0][2]
        assert payload["title"] == "DB timeout"
        assert payload["description"] == "Postgres connections exhausted"
        assert payload["component"] == "database"
        assert payload["severity"] == "high"

    def test_missing_title_returns_422(self, client, mock_publisher):
        response = client.post("/api/incidents", data={"title": ""})
        assert response.status_code == 422
        body = response.json()
        assert body["status"] == "error"
        assert body["code"] == "VALIDATION_ERROR"
        assert "Title is required" in body["message"]

    def test_success_with_file(self, client, mock_publisher, tmp_path):
        response = client.post(
            "/api/incidents",
            data={"title": "Bug with screenshot"},
            files={"file": ("screenshot.png", b"fakepngdata", "image/png")},
        )
        assert response.status_code == 201

    def test_path_traversal_blocked(self, client, mock_publisher):
        response = client.post(
            "/api/incidents",
            data={"title": "Traversal test"},
            files={"file": ("../../etc/passwd", b"malicious", "text/plain")},
        )
        assert response.status_code == 201
        payload = mock_publisher.publish.call_args[0][2]
        assert ".." not in (payload["attachment_url"] or "")

    def test_redis_failure_returns_503(self, client):
        mock = AsyncMock()
        mock.publish = AsyncMock(side_effect=Exception("Redis is down"))
        with patch("src.adapters.inbound.fastapi_routes.get_publisher", return_value=mock):
            response = client.post("/api/incidents", data={"title": "Failing test"})
        assert response.status_code == 503
        body = response.json()
        assert body["code"] == "PUBLISH_ERROR"


# ==========================================================================
# POST /api/webhooks/otel
# ==========================================================================
class TestOtelWebhook:
    def test_success(self, client, mock_publisher):
        otel_payload = {
            "error_message": "HTTP 500 Internal Server Error",
            "service_name": "catalog-api",
            "trace_id": "abc123",
            "status_code": 500,
            "timestamp": "2026-04-08T10:30:00Z",
        }
        response = client.post("/api/webhooks/otel", json=otel_payload)
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "ok"
        assert "incident_id" in body["data"]

        payload = mock_publisher.publish.call_args[0][2]
        assert payload["source_type"] == "systemIntegration"
        assert payload["reporter_slack_user_id"] is None
        assert payload["trace_data"]["trace_id"] == "abc123"
        assert payload["trace_data"]["status_code"] == 500

    def test_redis_failure_returns_503(self, client):
        mock = AsyncMock()
        mock.publish = AsyncMock(side_effect=Exception("Redis down"))
        with patch("src.adapters.inbound.fastapi_routes.get_publisher", return_value=mock):
            response = client.post("/api/webhooks/otel", json={"error_message": "err"})
        assert response.status_code == 503

    def test_malformed_json_returns_400(self, client, mock_publisher):
        response = client.post(
            "/api/webhooks/otel",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "VALIDATION_ERROR"


# ==========================================================================
# POST /api/webhooks/slack
# ==========================================================================
class TestSlackWebhook:
    def test_success(self, client, mock_publisher):
        response = client.post(
            "/api/webhooks/slack",
            json={"incident_id": "abc-123", "action": "reescalate"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"

        call_args = mock_publisher.publish.call_args
        assert call_args[0][0] == "reescalations"
        assert call_args[0][1] == "incident.reescalate"

    def test_missing_incident_id_returns_400(self, client, mock_publisher):
        response = client.post("/api/webhooks/slack", json={"action": "reescalate"})
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "VALIDATION_ERROR"

    def test_redis_failure_returns_503(self, client):
        mock = AsyncMock()
        mock.publish = AsyncMock(side_effect=Exception("Redis down"))
        with patch("src.adapters.inbound.fastapi_routes.get_publisher", return_value=mock):
            response = client.post(
                "/api/webhooks/slack",
                json={"incident_id": "abc-123"},
            )
        assert response.status_code == 503

    def test_malformed_json_returns_400(self, client, mock_publisher):
        response = client.post(
            "/api/webhooks/slack",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "VALIDATION_ERROR"


# ==========================================================================
# Health check (regression)
# ==========================================================================
class TestHealth:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
