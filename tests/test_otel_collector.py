"""Tests for Story 6.3: OTEL Collector for Proactive eShop Error Detection.

Covers:
- OTEL Collector configuration structure validation
- API /api/webhooks/otel OTLP-JSON format handling (resourceSpans)
- Regression: simple JSON format still works
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "services" / "api"))

from fastapi.testclient import TestClient

from src.main import app

COLLECTOR_CONFIG_PATH = _PROJECT_ROOT / "infra" / "otel-collector-config.yaml"


# ==========================================================================
# Fixtures
# ==========================================================================
@pytest.fixture(autouse=True)
def _reset_publisher():
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


def _otlp_payload(
    service_name="catalog-api",
    trace_id="abc123def456",
    span_name="GET /api/products",
    status_message="Internal Server Error",
    http_status_code=500,
    start_time_nano="1712577000000000000",
):
    """Build a minimal OTLP-JSON resourceSpans payload."""
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": service_name},
                        }
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": "span001",
                                "name": span_name,
                                "kind": 2,
                                "startTimeUnixNano": start_time_nano,
                                "endTimeUnixNano": "1712577001000000000",
                                "attributes": [
                                    {
                                        "key": "http.status_code",
                                        "value": {"intValue": str(http_status_code)},
                                    }
                                ],
                                "status": {
                                    "code": 2,
                                    "message": status_message,
                                },
                            }
                        ]
                    }
                ],
            }
        ]
    }


# ==========================================================================
# OTEL Collector Config Validation
# ==========================================================================
class TestOtelCollectorConfig:
    def test_config_file_exists(self):
        assert COLLECTOR_CONFIG_PATH.exists(), "otel-collector-config.yaml missing"

    def test_config_is_valid_yaml(self):
        cfg = yaml.safe_load(COLLECTOR_CONFIG_PATH.read_text())
        assert isinstance(cfg, dict)

    def test_otlp_receiver_grpc(self):
        cfg = yaml.safe_load(COLLECTOR_CONFIG_PATH.read_text())
        grpc = cfg["receivers"]["otlp"]["protocols"]["grpc"]
        assert grpc["endpoint"] == "0.0.0.0:4317"

    def test_otlp_receiver_http(self):
        cfg = yaml.safe_load(COLLECTOR_CONFIG_PATH.read_text())
        http = cfg["receivers"]["otlp"]["protocols"]["http"]
        assert http["endpoint"] == "0.0.0.0:4318"

    def test_filter_processor_exists(self):
        cfg = yaml.safe_load(COLLECTOR_CONFIG_PATH.read_text())
        assert "filter/errors" in cfg["processors"]

    def test_filter_drops_non_errors(self):
        cfg = yaml.safe_load(COLLECTOR_CONFIG_PATH.read_text())
        filt = cfg["processors"]["filter/errors"]
        assert filt["error_mode"] == "ignore"
        conditions = filt["traces"]["span"]
        assert any("STATUS_CODE_ERROR" in c for c in conditions)

    def test_otlphttp_exporter_targets_api(self):
        cfg = yaml.safe_load(COLLECTOR_CONFIG_PATH.read_text())
        exporter = cfg["exporters"]["otlphttp/mila"]
        assert "api:8000" in exporter["traces_endpoint"]
        assert "/api/webhooks/otel" in exporter["traces_endpoint"]

    def test_otlphttp_exporter_json_encoding(self):
        cfg = yaml.safe_load(COLLECTOR_CONFIG_PATH.read_text())
        exporter = cfg["exporters"]["otlphttp/mila"]
        assert exporter.get("encoding") == "json"

    def test_traces_pipeline_wired(self):
        cfg = yaml.safe_load(COLLECTOR_CONFIG_PATH.read_text())
        pipeline = cfg["service"]["pipelines"]["traces"]
        assert "otlp" in pipeline["receivers"]
        assert "filter/errors" in pipeline["processors"]
        assert "otlphttp/mila" in pipeline["exporters"]


# ==========================================================================
# API: OTLP-JSON format (resourceSpans from OTEL Collector)
# ==========================================================================
class TestOtlpWebhook:
    def test_otlp_single_error_span(self, client, mock_publisher):
        response = client.post("/api/webhooks/otel", json=_otlp_payload())
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "ok"
        assert len(body["data"]["incident_ids"]) == 1
        assert "1 incident(s)" in body["data"]["message"]

        payload = mock_publisher.publish.call_args[0][2]
        assert payload["source_type"] == "systemIntegration"
        assert payload["reporter_email"] is None
        assert payload["component"] == "catalog-api"
        assert payload["trace_data"]["trace_id"] == "abc123def456"
        assert payload["trace_data"]["status_code"] == 500
        assert payload["trace_data"]["service_name"] == "catalog-api"

    def test_otlp_error_message_from_status(self, client, mock_publisher):
        response = client.post(
            "/api/webhooks/otel",
            json=_otlp_payload(status_message="Connection refused"),
        )
        assert response.status_code == 201
        payload = mock_publisher.publish.call_args[0][2]
        assert payload["title"] == "Connection refused"
        assert payload["description"] == "Connection refused"

    def test_otlp_fallback_to_span_name(self, client, mock_publisher):
        """When status.message is empty, fall back to span name."""
        data = _otlp_payload(status_message="")
        data["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["status"]["message"] = ""
        response = client.post("/api/webhooks/otel", json=data)
        assert response.status_code == 201
        payload = mock_publisher.publish.call_args[0][2]
        assert payload["title"] == "GET /api/products"

    def test_otlp_timestamp_conversion(self, client, mock_publisher):
        """Nanosecond timestamps are converted to ISO format."""
        response = client.post(
            "/api/webhooks/otel",
            json=_otlp_payload(start_time_nano="1712577000000000000"),
        )
        assert response.status_code == 201
        payload = mock_publisher.publish.call_args[0][2]
        ts = payload["trace_data"]["timestamp"]
        assert ts is not None
        assert "2024-04-08" in ts  # epoch 1712577000 → 2024-04-08

    def test_otlp_multiple_spans(self, client, mock_publisher):
        """Multiple error spans → multiple incidents."""
        data = _otlp_payload()
        # Add a second span
        second_span = {
            "traceId": "second-trace",
            "spanId": "span002",
            "name": "POST /checkout",
            "startTimeUnixNano": "1712577002000000000",
            "attributes": [],
            "status": {"code": 2, "message": "Timeout"},
        }
        data["resourceSpans"][0]["scopeSpans"][0]["spans"].append(second_span)

        response = client.post("/api/webhooks/otel", json=data)
        assert response.status_code == 201
        body = response.json()
        assert len(body["data"]["incident_ids"]) == 2
        assert mock_publisher.publish.call_count == 2

    def test_otlp_empty_resource_spans(self, client, mock_publisher):
        response = client.post(
            "/api/webhooks/otel", json={"resourceSpans": []}
        )
        assert response.status_code == 201
        body = response.json()
        assert body["data"]["message"] == "No error spans found"
        mock_publisher.publish.assert_not_called()

    def test_otlp_no_spans_in_scope(self, client, mock_publisher):
        data = {
            "resourceSpans": [
                {
                    "resource": {"attributes": []},
                    "scopeSpans": [{"spans": []}],
                }
            ]
        }
        response = client.post("/api/webhooks/otel", json=data)
        assert response.status_code == 201
        assert response.json()["data"]["message"] == "No error spans found"

    def test_otlp_redis_failure(self, client):
        """All spans fail to publish → 503."""
        mock = AsyncMock()
        mock.publish = AsyncMock(side_effect=Exception("Redis down"))
        with patch("src.adapters.inbound.fastapi_routes.get_publisher", return_value=mock):
            response = client.post("/api/webhooks/otel", json=_otlp_payload())
        assert response.status_code == 503
        assert response.json()["code"] == "PUBLISH_ERROR"

    def test_otlp_partial_redis_failure(self, client):
        """First span succeeds, second fails → partial response."""
        mock = AsyncMock()
        call_count = 0

        async def publish_side_effect(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Redis down on second span")
            return "test-event-id"

        mock.publish = AsyncMock(side_effect=publish_side_effect)
        data = _otlp_payload()
        second_span = {
            "traceId": "second-trace",
            "spanId": "span002",
            "name": "POST /checkout",
            "startTimeUnixNano": "1712577002000000000",
            "attributes": [],
            "status": {"code": 2, "message": "Timeout"},
        }
        data["resourceSpans"][0]["scopeSpans"][0]["spans"].append(second_span)

        with patch("src.adapters.inbound.fastapi_routes.get_publisher", return_value=mock):
            response = client.post("/api/webhooks/otel", json=data)
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "partial"
        assert len(body["data"]["incident_ids"]) == 1
        assert body["data"]["failed_count"] == 1

    def test_otlp_missing_http_status_code(self, client, mock_publisher):
        """Span without http.status_code attribute → status_code is None."""
        data = _otlp_payload()
        data["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"] = []
        response = client.post("/api/webhooks/otel", json=data)
        assert response.status_code == 201
        payload = mock_publisher.publish.call_args[0][2]
        assert payload["trace_data"]["status_code"] is None

    def test_otlp_missing_service_name(self, client, mock_publisher):
        """Resource without service.name attribute → component is None."""
        data = _otlp_payload()
        data["resourceSpans"][0]["resource"]["attributes"] = []
        response = client.post("/api/webhooks/otel", json=data)
        assert response.status_code == 201
        payload = mock_publisher.publish.call_args[0][2]
        assert payload["component"] is None
        assert payload["trace_data"]["service_name"] is None

    def test_otlp_non_numeric_status_code(self, client, mock_publisher):
        """Non-numeric http.status_code → status_code is None, not a crash."""
        data = _otlp_payload()
        data["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"] = [
            {"key": "http.status_code", "value": {"stringValue": "OK"}}
        ]
        response = client.post("/api/webhooks/otel", json=data)
        assert response.status_code == 201
        payload = mock_publisher.publish.call_args[0][2]
        assert payload["trace_data"]["status_code"] is None

    def test_otlp_null_attributes_in_resource(self, client, mock_publisher):
        """Resource with 'attributes': null → does not crash."""
        data = _otlp_payload()
        data["resourceSpans"][0]["resource"]["attributes"] = None
        response = client.post("/api/webhooks/otel", json=data)
        assert response.status_code == 201
        payload = mock_publisher.publish.call_args[0][2]
        assert payload["component"] is None

    def test_otlp_null_attributes_in_span(self, client, mock_publisher):
        """Span with 'attributes': null → does not crash."""
        data = _otlp_payload()
        data["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"] = None
        response = client.post("/api/webhooks/otel", json=data)
        assert response.status_code == 201
        payload = mock_publisher.publish.call_args[0][2]
        assert payload["trace_data"]["status_code"] is None

    def test_otlp_null_item_in_resource_spans(self, client, mock_publisher):
        """null item in resourceSpans array → skipped, not crash."""
        data = {"resourceSpans": [None, _otlp_payload()["resourceSpans"][0]]}
        response = client.post("/api/webhooks/otel", json=data)
        assert response.status_code == 201
        body = response.json()
        assert len(body["data"]["incident_ids"]) == 1

    def test_otlp_null_item_in_scope_spans(self, client, mock_publisher):
        """null item in scopeSpans array → skipped, not crash."""
        data = _otlp_payload()
        data["resourceSpans"][0]["scopeSpans"].append(None)
        response = client.post("/api/webhooks/otel", json=data)
        assert response.status_code == 201

    def test_otlp_null_item_in_spans(self, client, mock_publisher):
        """null item in spans array → skipped, not crash."""
        data = _otlp_payload()
        data["resourceSpans"][0]["scopeSpans"][0]["spans"].append(None)
        response = client.post("/api/webhooks/otel", json=data)
        assert response.status_code == 201
        assert len(response.json()["data"]["incident_ids"]) == 1

    def test_otlp_null_status_in_span(self, client, mock_publisher):
        """Span with 'status': null → falls back to span name."""
        data = _otlp_payload()
        data["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["status"] = None
        response = client.post("/api/webhooks/otel", json=data)
        assert response.status_code == 201
        payload = mock_publisher.publish.call_args[0][2]
        assert payload["title"] == "GET /api/products"


# ==========================================================================
# Regression: simple JSON format (Story 2.2) still works
# ==========================================================================
class TestSimpleOtelWebhookRegression:
    def test_simple_json_format(self, client, mock_publisher):
        payload = {
            "error_message": "HTTP 500 Internal Server Error",
            "service_name": "catalog-api",
            "trace_id": "abc123",
            "status_code": 500,
            "timestamp": "2026-04-08T10:30:00Z",
        }
        response = client.post("/api/webhooks/otel", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "ok"
        assert "incident_id" in body["data"]

        pub_payload = mock_publisher.publish.call_args[0][2]
        assert pub_payload["source_type"] == "systemIntegration"
        assert pub_payload["reporter_email"] is None
        assert pub_payload["trace_data"]["trace_id"] == "abc123"

    def test_malformed_json_returns_400(self, client, mock_publisher):
        response = client.post(
            "/api/webhooks/otel",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "VALIDATION_ERROR"


# ==========================================================================
# Docker Compose structure validation
# ==========================================================================
class TestDockerComposeOtel:
    def test_otel_collector_defined(self):
        dc = yaml.safe_load(
            (_PROJECT_ROOT / "docker-compose.yml").read_text()
        )
        assert "otel-collector" in dc["services"]

    def test_config_volume_mounted(self):
        dc = yaml.safe_load(
            (_PROJECT_ROOT / "docker-compose.yml").read_text()
        )
        svc = dc["services"]["otel-collector"]
        volumes = svc.get("volumes", [])
        assert any("otel-collector-config.yaml" in v for v in volumes)

    def test_ports_not_published_externally(self):
        dc = yaml.safe_load(
            (_PROJECT_ROOT / "docker-compose.yml").read_text()
        )
        svc = dc["services"]["otel-collector"]
        # 'ports' should not exist (external publish removed)
        assert "ports" not in svc, "OTLP ports should NOT be published externally"

    def test_ports_exposed_internally(self):
        dc = yaml.safe_load(
            (_PROJECT_ROOT / "docker-compose.yml").read_text()
        )
        svc = dc["services"]["otel-collector"]
        exposed = [str(p) for p in svc.get("expose", [])]
        assert "4317" in exposed
        assert "4318" in exposed

    def test_depends_on_api(self):
        dc = yaml.safe_load(
            (_PROJECT_ROOT / "docker-compose.yml").read_text()
        )
        svc = dc["services"]["otel-collector"]
        deps = svc.get("depends_on", {})
        assert "api" in deps

    def test_depends_on_api_has_condition(self):
        dc = yaml.safe_load(
            (_PROJECT_ROOT / "docker-compose.yml").read_text()
        )
        svc = dc["services"]["otel-collector"]
        deps = svc.get("depends_on", {})
        assert isinstance(deps, dict), "depends_on should use condition syntax"
        assert "condition" in deps.get("api", {})

    def test_agent_dns_for_external_resolution(self):
        dc = yaml.safe_load(
            (_PROJECT_ROOT / "docker-compose.yml").read_text()
        )
        svc = dc["services"]["agent"]
        dns = svc.get("dns", [])
        assert len(dns) > 0, "Agent needs DNS for external services (Langfuse cloud)"

    def test_on_mila_network(self):
        dc = yaml.safe_load(
            (_PROJECT_ROOT / "docker-compose.yml").read_text()
        )
        svc = dc["services"]["otel-collector"]
        assert "mila-net" in svc.get("networks", [])
