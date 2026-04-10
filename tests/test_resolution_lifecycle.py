"""
Tests for Resolution Lifecycle (Story 4.3).

Covers:
- handle_resolution_webhook: resolved state detection (Done, Resolved)
- handle_resolution_webhook: non-resolution state changes ignored
- handle_resolution_webhook: non-Issue webhook types ignored
- handle_resolution_webhook: non-update actions ignored
- Ticket-incident correlation via TicketMappingStore
- Non-tracked ticket graceful skip
- Reporter notification published with correct payload
- Proactive incident (no reporter) skips notification
- Idempotency: duplicate resolution webhooks ignored
- Notification publish failure handling
- Webhook listener integration: HMAC + resolution flow end-to-end
- RedisTicketMappingStore: save, get, mark_resolved

Run:
    pytest tests/test_resolution_lifecycle.py -v
"""

import hashlib
import hmac as hmac_mod
import importlib.util
import json
import sys
import types as _types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TS_ROOT = _PROJECT_ROOT / "services" / "ticket-service"


# ---------------------------------------------------------------------------
# Module loading helpers (same pattern as other ticket-service tests)
# ---------------------------------------------------------------------------
from contextlib import contextmanager


def _load_module_raw(name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@contextmanager
def _ticket_service_context():
    saved = dict(sys.modules)
    saved_path = list(sys.path)

    svc_path = str(_TS_ROOT)
    if svc_path in sys.path:
        sys.path.remove(svc_path)
    sys.path.insert(0, svc_path)

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

    _load_module_raw("src.config", _TS_ROOT / "src" / "config.py")
    _load_module_raw("src.ports.inbound", _TS_ROOT / "src" / "ports" / "inbound.py")
    _load_module_raw("src.ports.outbound", _TS_ROOT / "src" / "ports" / "outbound.py")
    _load_module_raw("src.ports.ticket_mapping", _TS_ROOT / "src" / "ports" / "ticket_mapping.py")
    _load_module_raw("src.domain.models", _TS_ROOT / "src" / "domain" / "models.py")
    _load_module_raw("src.domain.services", _TS_ROOT / "src" / "domain" / "services.py")
    _load_module_raw("src.adapters.inbound.redis_consumer", _TS_ROOT / "src" / "adapters" / "inbound" / "redis_consumer.py")
    _load_module_raw("src.adapters.inbound.webhook_listener", _TS_ROOT / "src" / "adapters" / "inbound" / "webhook_listener.py")
    _load_module_raw("src.adapters.outbound.redis_publisher", _TS_ROOT / "src" / "adapters" / "outbound" / "redis_publisher.py")
    _load_module_raw("src.adapters.outbound.linear_client", _TS_ROOT / "src" / "adapters" / "outbound" / "linear_client.py")
    _load_module_raw("src.adapters.outbound.redis_ticket_mapping", _TS_ROOT / "src" / "adapters" / "outbound" / "redis_ticket_mapping.py")

    try:
        yield
    finally:
        new_keys = set(sys.modules.keys()) - set(saved.keys())
        for k in new_keys:
            del sys.modules[k]
        sys.modules.update(saved)
        sys.path[:] = saved_path


with _ticket_service_context():
    _services = sys.modules["src.domain.services"]
    _webhook = sys.modules["src.adapters.inbound.webhook_listener"]
    _config = sys.modules["src.config"]

handle_resolution_webhook = _services.handle_resolution_webhook
RESOLVED_STATES = _services.RESOLVED_STATES
verify_linear_signature = _webhook.verify_linear_signature
create_app = _webhook.create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolution_webhook_payload(
    state_name: str = "Done",
    state_type: str = "completed",
    action: str = "update",
    webhook_type: str = "Issue",
    linear_ticket_id: str = "issue-uuid-123",
    identifier: str = "ENG-42",
    title: str = "[P2] NullReferenceException in OrderController.cs",
    url: str = "https://linear.app/team/issue/ENG-42",
    old_state_name: str = "In Progress",
    old_state_type: str = "started",
) -> dict:
    return {
        "action": action,
        "type": webhook_type,
        "data": {
            "id": linear_ticket_id,
            "identifier": identifier,
            "title": title,
            "state": {"name": state_name, "type": state_type},
            "url": url,
            "description": "...markdown body with incident_id embedded...",
        },
        "updatedFrom": {
            "state": {"name": old_state_name, "type": old_state_type},
        },
    }


def _mock_mapping_store(
    mapping: dict | None = None,
    mark_resolved_returns: bool = True,
) -> AsyncMock:
    store = AsyncMock()
    store.get_mapping.return_value = mapping
    store.mark_resolved.return_value = mark_resolved_returns
    store.save_mapping.return_value = None
    return store


def _default_mapping() -> dict:
    return {
        "incident_id": "inc-200",
        "reporter_email": "user@example.com",
        "identifier": "ENG-42",
        "url": "https://linear.app/team/issue/ENG-42",
    }


# ---------------------------------------------------------------------------
# handle_resolution_webhook — state detection tests
# ---------------------------------------------------------------------------

class TestResolutionStateDetection:
    @pytest.mark.asyncio
    async def test_done_state_triggers_resolution(self):
        payload = _resolution_webhook_payload(state_name="Done")
        store = _mock_mapping_store(mapping=_default_mapping())
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is True
        store.mark_resolved.assert_called_once_with("issue-uuid-123")

    @pytest.mark.asyncio
    async def test_resolved_state_triggers_resolution(self):
        payload = _resolution_webhook_payload(state_name="Resolved")
        store = _mock_mapping_store(mapping=_default_mapping())
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is True

    @pytest.mark.asyncio
    async def test_in_progress_state_ignored(self):
        payload = _resolution_webhook_payload(state_name="In Progress")
        store = _mock_mapping_store()
        publisher = AsyncMock()

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is False
        store.mark_resolved.assert_not_called()
        publisher.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_todo_state_ignored(self):
        payload = _resolution_webhook_payload(state_name="Todo")
        store = _mock_mapping_store()
        publisher = AsyncMock()

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is False

    @pytest.mark.asyncio
    async def test_non_issue_type_ignored(self):
        payload = _resolution_webhook_payload(webhook_type="Comment")
        store = _mock_mapping_store()
        publisher = AsyncMock()

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is False
        store.mark_resolved.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_update_action_ignored(self):
        payload = _resolution_webhook_payload(action="create")
        store = _mock_mapping_store()
        publisher = AsyncMock()

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is False


# ---------------------------------------------------------------------------
# Ticket-incident correlation tests
# ---------------------------------------------------------------------------

class TestTicketIncidentCorrelation:
    @pytest.mark.asyncio
    async def test_non_tracked_ticket_skipped(self):
        """Webhook for a ticket not created by mila is silently ignored."""
        payload = _resolution_webhook_payload()
        store = _mock_mapping_store(mapping=None)
        publisher = AsyncMock()

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is False
        publisher.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_tracked_ticket_does_not_burn_resolved_flag(self):
        """Non-tracked tickets should not mark resolved (get_mapping runs first)."""
        payload = _resolution_webhook_payload()
        store = _mock_mapping_store(mapping=None)
        publisher = AsyncMock()

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is False
        store.get_mapping.assert_called_once()
        store.mark_resolved.assert_not_called()
        publisher.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_mapping_lookup_uses_linear_ticket_id(self):
        payload = _resolution_webhook_payload(linear_ticket_id="special-id-999")
        store = _mock_mapping_store(mapping=_default_mapping())
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        store.get_mapping.assert_called_once_with("special-id-999")


# ---------------------------------------------------------------------------
# Reporter notification tests
# ---------------------------------------------------------------------------

class TestReporterResolvedNotification:
    @pytest.mark.asyncio
    async def test_publishes_correct_notification_payload(self):
        payload = _resolution_webhook_payload(
            title="[P2] NullRef in OrderController",
            url="https://linear.app/team/issue/ENG-42",
        )
        mapping = {
            "incident_id": "inc-200",
            "reporter_email": "user@example.com",
            "identifier": "ENG-42",
            "url": "https://linear.app/team/issue/ENG-42",
        }
        store = _mock_mapping_store(mapping=mapping)
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is True
        publisher.publish.assert_called_once()
        call_args = publisher.publish.call_args[0]
        assert call_args[0] == "notifications"
        assert call_args[1] == "notification.send"

        notification_payload = call_args[2]
        assert notification_payload["type"] == "reporter_resolved"
        assert notification_payload["reporter_email"] == "user@example.com"
        assert notification_payload["incident_id"] == "inc-200"
        assert notification_payload["ticket_url"] == "https://linear.app/team/issue/ENG-42"
        assert notification_payload["title"] == "[P2] NullRef in OrderController"
        assert "resolved" in notification_payload["message"]

    @pytest.mark.asyncio
    async def test_proactive_incident_no_notification(self):
        """Proactive incidents have no reporter — no notification should be sent."""
        payload = _resolution_webhook_payload()
        mapping = {
            "incident_id": "inc-300",
            "reporter_email": None,
            "identifier": "ENG-50",
            "url": "https://linear.app/team/issue/ENG-50",
        }
        store = _mock_mapping_store(mapping=mapping)
        publisher = AsyncMock()

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is False
        publisher.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_notification_publish_failure_returns_false(self):
        payload = _resolution_webhook_payload()
        store = _mock_mapping_store(mapping=_default_mapping())
        publisher = AsyncMock()
        publisher.publish.side_effect = ConnectionError("Redis down")

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is False


# ---------------------------------------------------------------------------
# Idempotency tests
# ---------------------------------------------------------------------------

class TestIdempotency:
    @pytest.mark.asyncio
    async def test_duplicate_resolution_skipped(self):
        """Second resolution webhook for same ticket should not send notification."""
        payload = _resolution_webhook_payload()
        store = _mock_mapping_store(mapping=_default_mapping(), mark_resolved_returns=False)
        publisher = AsyncMock()

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is False
        # get_mapping is called first (before idempotency gate)
        store.get_mapping.assert_called_once()
        store.mark_resolved.assert_called_once()
        publisher.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_first_resolution_proceeds(self):
        payload = _resolution_webhook_payload()
        store = _mock_mapping_store(mapping=_default_mapping(), mark_resolved_returns=True)
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is True


# ---------------------------------------------------------------------------
# Webhook listener integration tests
# ---------------------------------------------------------------------------

class TestWebhookListenerResolution:
    def _sign(self, body: bytes, secret: str = "test-secret") -> str:
        return hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()

    @pytest.mark.asyncio
    async def test_resolution_webhook_end_to_end(self):
        """Full flow: signed webhook → parsed → resolution handler called → 200."""
        mapping_store = _mock_mapping_store(mapping=_default_mapping())
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        with patch.object(_config, "LINEAR_WEBHOOK_SECRET", "test-secret"):
            app = create_app(mapping_store=mapping_store, publisher=publisher)

            from starlette.testclient import TestClient
            client = TestClient(app)

            payload = _resolution_webhook_payload()
            body = json.dumps(payload).encode()
            sig = self._sign(body)

            response = client.post(
                "/webhooks/linear",
                content=body,
                headers={
                    "X-Linear-Signature": sig,
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 200
            assert response.json()["status"] == "ok"
            publisher.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_resolution_webhook_no_notification(self):
        """A webhook that is not a resolution should return 200 but not publish."""
        mapping_store = _mock_mapping_store()
        publisher = AsyncMock()

        with patch.object(_config, "LINEAR_WEBHOOK_SECRET", "test-secret"):
            app = create_app(mapping_store=mapping_store, publisher=publisher)

            from starlette.testclient import TestClient
            client = TestClient(app)

            payload = _resolution_webhook_payload(state_name="In Progress")
            body = json.dumps(payload).encode()
            sig = self._sign(body)

            response = client.post(
                "/webhooks/linear",
                content=body,
                headers={
                    "X-Linear-Signature": sig,
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 200
            publisher.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_app_without_dependencies_still_works(self):
        """Backward compat: create_app() without mapping_store/publisher returns 200."""
        with patch.object(_config, "LINEAR_WEBHOOK_SECRET", "test-secret"):
            app = create_app()

            from starlette.testclient import TestClient
            client = TestClient(app)

            payload = _resolution_webhook_payload()
            body = json.dumps(payload).encode()
            sig = self._sign(body)

            response = client.post(
                "/webhooks/linear",
                content=body,
                headers={
                    "X-Linear-Signature": sig,
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_resolution_handler_exception_returns_200(self):
        """If resolution handler raises, webhook still returns 200 (no 500)."""
        mapping_store = AsyncMock()
        mapping_store.get_mapping.side_effect = RuntimeError("unexpected boom")
        publisher = AsyncMock()

        with patch.object(_config, "LINEAR_WEBHOOK_SECRET", "test-secret"):
            app = create_app(mapping_store=mapping_store, publisher=publisher)

            from starlette.testclient import TestClient
            client = TestClient(app, raise_server_exceptions=False)

            payload = _resolution_webhook_payload()
            body = json.dumps(payload).encode()
            sig = self._sign(body)

            response = client.post(
                "/webhooks/linear",
                content=body,
                headers={
                    "X-Linear-Signature": sig,
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_signature_still_rejected(self):
        """HMAC verification still rejects bad signatures."""
        mapping_store = _mock_mapping_store()
        publisher = AsyncMock()

        with patch.object(_config, "LINEAR_WEBHOOK_SECRET", "test-secret"):
            app = create_app(mapping_store=mapping_store, publisher=publisher)

            from starlette.testclient import TestClient
            client = TestClient(app)

            payload = _resolution_webhook_payload()
            body = json.dumps(payload).encode()

            response = client.post(
                "/webhooks/linear",
                content=body,
                headers={
                    "X-Linear-Signature": "bad-signature",
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 401


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_data_section(self):
        """Webhook with missing data section should not crash."""
        payload = {"action": "update", "type": "Issue"}
        store = _mock_mapping_store()
        publisher = AsyncMock()

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is False

    @pytest.mark.asyncio
    async def test_missing_state_in_data(self):
        """Webhook with data but no state should not crash."""
        payload = {
            "action": "update",
            "type": "Issue",
            "data": {"id": "x", "identifier": "ENG-1", "title": "test", "url": "http://x"},
        }
        store = _mock_mapping_store()
        publisher = AsyncMock()

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is False

    @pytest.mark.asyncio
    async def test_empty_reporter_string_treated_as_no_reporter(self):
        """If reporter_email is empty string, treat as no reporter."""
        payload = _resolution_webhook_payload()
        mapping = {
            "incident_id": "inc-400",
            "reporter_email": "",
            "identifier": "ENG-60",
            "url": "https://linear.app/team/issue/ENG-60",
        }
        store = _mock_mapping_store(mapping=mapping)
        publisher = AsyncMock()

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is False
        publisher.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_linear_ticket_id_rejected(self):
        """Webhook with empty data.id should be rejected early."""
        payload = _resolution_webhook_payload(linear_ticket_id="")
        store = _mock_mapping_store()
        publisher = AsyncMock()

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is False
        store.get_mapping.assert_not_called()
        store.mark_resolved.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_data_id_field_rejected(self):
        """Webhook where data has no id key should be rejected."""
        payload = {
            "action": "update",
            "type": "Issue",
            "data": {
                "identifier": "ENG-99",
                "title": "test",
                "state": {"name": "Done", "type": "completed"},
                "url": "http://x",
            },
        }
        store = _mock_mapping_store()
        publisher = AsyncMock()

        result = await handle_resolution_webhook(payload, store, publisher, "evt-abc")

        assert result is False
        store.get_mapping.assert_not_called()
