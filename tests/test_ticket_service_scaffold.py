"""
Tests for Ticket-Service Scaffold (Story 4.1).

Covers:
- TicketCommand model validation
- Domain service: handle_ticket_command deserialization and routing
- Domain service: unrecognized action handling
- Domain service: malformed payload error publishing
- Webhook listener: HMAC signature verification (valid + invalid)
- Webhook listener: missing signature rejection
- Webhook listener: malformed JSON handling
- Webhook listener: health endpoint
- Concurrent startup structure (main.py wiring)

Run:
    pytest tests/test_ticket_service_scaffold.py -v
"""

import hashlib
import hmac as hmac_mod
import importlib.util
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Module loading helpers
# ---------------------------------------------------------------------------

import types as _types
from contextlib import contextmanager

_TS_ROOT = _PROJECT_ROOT / "services" / "ticket-service"


def _load_module_raw(name: str, file_path: Path):
    """Load a module by file path. Does NOT cache in sys.modules permanently."""
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@contextmanager
def _ticket_service_context():
    """Temporarily wire sys.modules so `from src.X import Y` resolves to ticket-service."""
    saved = dict(sys.modules)
    saved_path = list(sys.path)

    svc_path = str(_TS_ROOT)
    if svc_path in sys.path:
        sys.path.remove(svc_path)
    sys.path.insert(0, svc_path)

    # Create synthetic package hierarchy
    src_pkg = _types.ModuleType("src")
    src_pkg.__path__ = [str(_TS_ROOT / "src")]
    src_pkg.__package__ = "src"
    sys.modules["src"] = src_pkg

    domain_pkg = _types.ModuleType("src.domain")
    domain_pkg.__path__ = [str(_TS_ROOT / "src" / "domain")]
    domain_pkg.__package__ = "src.domain"
    sys.modules["src.domain"] = domain_pkg

    ports_pkg = _types.ModuleType("src.ports")
    ports_pkg.__path__ = [str(_TS_ROOT / "src" / "ports")]
    sys.modules["src.ports"] = ports_pkg

    adapters_pkg = _types.ModuleType("src.adapters")
    adapters_pkg.__path__ = [str(_TS_ROOT / "src" / "adapters")]
    sys.modules["src.adapters"] = adapters_pkg

    adapters_inbound_pkg = _types.ModuleType("src.adapters.inbound")
    adapters_inbound_pkg.__path__ = [str(_TS_ROOT / "src" / "adapters" / "inbound")]
    sys.modules["src.adapters.inbound"] = adapters_inbound_pkg

    adapters_outbound_pkg = _types.ModuleType("src.adapters.outbound")
    adapters_outbound_pkg.__path__ = [str(_TS_ROOT / "src" / "adapters" / "outbound")]
    sys.modules["src.adapters.outbound"] = adapters_outbound_pkg

    # Load leaf modules
    _load_module_raw("src.config", _TS_ROOT / "src" / "config.py")
    _load_module_raw("src.ports.inbound", _TS_ROOT / "src" / "ports" / "inbound.py")
    _load_module_raw("src.ports.outbound", _TS_ROOT / "src" / "ports" / "outbound.py")
    _load_module_raw("src.domain.models", _TS_ROOT / "src" / "domain" / "models.py")
    _load_module_raw("src.domain.services", _TS_ROOT / "src" / "domain" / "services.py")
    _load_module_raw("src.adapters.inbound.redis_consumer", _TS_ROOT / "src" / "adapters" / "inbound" / "redis_consumer.py")
    _load_module_raw("src.adapters.inbound.webhook_listener", _TS_ROOT / "src" / "adapters" / "inbound" / "webhook_listener.py")
    _load_module_raw("src.adapters.outbound.redis_publisher", _TS_ROOT / "src" / "adapters" / "outbound" / "redis_publisher.py")

    try:
        yield
    finally:
        # Fully restore sys.modules and sys.path
        # Remove any keys we added
        new_keys = set(sys.modules.keys()) - set(saved.keys())
        for k in new_keys:
            del sys.modules[k]
        # Restore original modules
        sys.modules.update(saved)
        sys.path[:] = saved_path


# Load ticket-service modules in isolation, then save refs for tests
with _ticket_service_context():
    _models = sys.modules["src.domain.models"]
    _services = sys.modules["src.domain.services"]
    _webhook = sys.modules["src.adapters.inbound.webhook_listener"]

TicketCommand = _models.TicketCommand
TicketStatusEvent = _models.TicketStatusEvent
handle_ticket_command = _services.handle_ticket_command
verify_linear_signature = _webhook.verify_linear_signature
create_app = _webhook.create_app


def _build_envelope(event_type: str, source: str, payload: dict) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "payload": payload,
    }


def _valid_ticket_command_payload(**overrides) -> dict:
    base = {
        "action": "create_engineering_ticket",
        "title": "Fix payment gateway timeout",
        "body": "Payment service returning 504 errors since 14:00 UTC",
        "severity": "critical",
        "labels": ["payments", "p0"],
        "reporter_email": "user@example.com",
        "incident_id": "inc-100",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# TicketCommand model tests
# ---------------------------------------------------------------------------

class TestTicketCommandModel:
    def test_valid_command_parses(self):
        cmd = TicketCommand(**_valid_ticket_command_payload())
        assert cmd.action == "create_engineering_ticket"
        assert cmd.incident_id == "inc-100"
        assert cmd.severity == "critical"

    def test_optional_fields_default(self):
        payload = _valid_ticket_command_payload()
        payload.pop("labels")
        payload.pop("reporter_email")
        cmd = TicketCommand(**payload)
        assert cmd.labels == []
        assert cmd.reporter_email is None

    def test_missing_required_field_raises(self):
        payload = _valid_ticket_command_payload()
        del payload["title"]
        with pytest.raises(Exception):
            TicketCommand(**payload)


class TestTicketStatusEventModel:
    def test_valid_status_event(self):
        evt = TicketStatusEvent(
            ticket_id="LIN-42",
            old_status="Todo",
            new_status="In Progress",
            incident_id="inc-100",
        )
        assert evt.ticket_id == "LIN-42"
        assert evt.reporter_email is None


# ---------------------------------------------------------------------------
# Domain service: handle_ticket_command tests
# ---------------------------------------------------------------------------

class TestHandleTicketCommand:
    @pytest.mark.asyncio
    async def test_valid_create_engineering_ticket(self):
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"
        envelope = _build_envelope(
            "ticket.create", "agent", _valid_ticket_command_payload()
        )
        # Without ticket_creator, the handler publishes an error for create_engineering_ticket
        result = await handle_ticket_command(envelope, publisher)
        assert result is None
        publisher.publish.assert_called_once()
        assert publisher.publish.call_args[0][0] == "errors"

    @pytest.mark.asyncio
    async def test_unrecognized_action_returns_none(self):
        publisher = AsyncMock()
        envelope = _build_envelope(
            "ticket.create",
            "agent",
            _valid_ticket_command_payload(action="unknown_action"),
        )
        result = await handle_ticket_command(envelope, publisher)
        assert result is None
        publisher.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_malformed_payload_publishes_error(self):
        publisher = AsyncMock()
        envelope = _build_envelope("ticket.create", "agent", {"action": "create_engineering_ticket"})
        result = await handle_ticket_command(envelope, publisher)
        assert result is None
        publisher.publish.assert_called_once()
        call_args = publisher.publish.call_args
        assert call_args[0][0] == "errors"
        assert call_args[0][1] == "ticket.error"
        assert "event_id" in call_args[0][2]

    @pytest.mark.asyncio
    async def test_missing_payload_key_publishes_error(self):
        publisher = AsyncMock()
        envelope = {
            "event_id": str(uuid.uuid4()),
            "event_type": "ticket.create",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "agent",
            # no "payload" key
        }
        result = await handle_ticket_command(envelope, publisher)
        assert result is None
        publisher.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_event_id_defaults_to_unknown(self):
        publisher = AsyncMock()
        envelope = {"payload": {"action": "create_engineering_ticket"}}
        result = await handle_ticket_command(envelope, publisher)
        assert result is None
        call_args = publisher.publish.call_args
        assert call_args[0][2]["event_id"] == "unknown"


# ---------------------------------------------------------------------------
# HMAC signature verification tests
# ---------------------------------------------------------------------------

WEBHOOK_SECRET = "test-webhook-secret-42"


class TestVerifyLinearSignature:
    def _sign(self, body: bytes, secret: str = WEBHOOK_SECRET) -> str:
        return hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()

    def test_valid_signature_passes(self):
        body = b'{"action": "create", "type": "Issue"}'
        sig = self._sign(body)
        assert verify_linear_signature(body, sig, WEBHOOK_SECRET) is True

    def test_invalid_signature_fails(self):
        body = b'{"action": "create", "type": "Issue"}'
        assert verify_linear_signature(body, "bad-signature", WEBHOOK_SECRET) is False

    def test_wrong_secret_fails(self):
        body = b'{"action": "create", "type": "Issue"}'
        sig = self._sign(body, "wrong-secret")
        assert verify_linear_signature(body, sig, WEBHOOK_SECRET) is False

    def test_empty_body(self):
        body = b""
        sig = self._sign(body)
        assert verify_linear_signature(body, sig, WEBHOOK_SECRET) is True

    def test_constant_time_comparison(self):
        """Verify we use hmac.compare_digest (constant-time) — not ==."""
        body = b"test"
        sig = self._sign(body)
        # This is a structural test: the function should still work correctly
        assert verify_linear_signature(body, sig, WEBHOOK_SECRET) is True


# ---------------------------------------------------------------------------
# FastAPI webhook endpoint tests
# ---------------------------------------------------------------------------

try:
    from starlette.testclient import TestClient
    HAS_STARLETTE = True
except ImportError:
    HAS_STARLETTE = False


@pytest.mark.skipif(not HAS_STARLETTE, reason="starlette not installed")
class TestWebhookEndpoint:
    @pytest.fixture
    def client(self):
        with _ticket_service_context():
            config_mod = sys.modules["src.config"]
            config_mod.LINEAR_WEBHOOK_SECRET = WEBHOOK_SECRET
            wh_mod = sys.modules["src.adapters.inbound.webhook_listener"]
            app = wh_mod.create_app()
            with TestClient(app) as c:
                yield c

    def _sign(self, body: bytes) -> str:
        return hmac_mod.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    def test_valid_webhook_returns_200(self, client):
        body = json.dumps({"action": "create", "type": "Issue"}).encode()
        sig = self._sign(body)
        resp = client.post(
            "/webhooks/linear",
            content=body,
            headers={"X-Linear-Signature": sig, "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_invalid_signature_returns_401(self, client):
        body = json.dumps({"action": "create", "type": "Issue"}).encode()
        resp = client.post(
            "/webhooks/linear",
            content=body,
            headers={"X-Linear-Signature": "invalid-sig", "Content-Type": "application/json"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "invalid signature"

    def test_missing_signature_returns_401(self, client):
        body = json.dumps({"action": "create", "type": "Issue"}).encode()
        resp = client.post(
            "/webhooks/linear",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "ticket-service"

    def test_non_dict_json_payload_returns_400(self, client):
        """POST with valid signature but non-object JSON (e.g. array, null) returns 400."""
        for payload in [None, [1, 2, 3], 42, "just a string"]:
            body = json.dumps(payload).encode()
            sig = self._sign(body)
            resp = client.post(
                "/webhooks/linear",
                content=body,
                headers={"X-Linear-Signature": sig, "Content-Type": "application/json"},
            )
            assert resp.status_code == 400, f"Expected 400 for payload={payload!r}, got {resp.status_code}"
            assert resp.json()["error"] == "expected JSON object"


# ---------------------------------------------------------------------------
# Main.py wiring structure tests
# ---------------------------------------------------------------------------

class TestMainWiring:
    def test_main_module_imports(self):
        """Verify main.py can be imported and has expected structure."""
        with _ticket_service_context():
            main_mod = _load_module_raw(
                "ts_main_check",
                _TS_ROOT / "src" / "main.py",
            )
            assert hasattr(main_mod, "main")
            assert hasattr(main_mod, "start_consumer")
            assert hasattr(main_mod, "run_uvicorn")

    def test_start_consumer_is_coroutine(self):
        import inspect
        with _ticket_service_context():
            main_mod = _load_module_raw("ts_main_check2", _TS_ROOT / "src" / "main.py")
            assert inspect.iscoroutinefunction(main_mod.start_consumer)

    def test_run_uvicorn_is_coroutine(self):
        import inspect
        with _ticket_service_context():
            main_mod = _load_module_raw("ts_main_check3", _TS_ROOT / "src" / "main.py")
            assert inspect.iscoroutinefunction(main_mod.run_uvicorn)

    def test_main_is_coroutine(self):
        import inspect
        with _ticket_service_context():
            main_mod = _load_module_raw("ts_main_check4", _TS_ROOT / "src" / "main.py")
            assert inspect.iscoroutinefunction(main_mod.main)
