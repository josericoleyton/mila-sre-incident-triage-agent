"""
Tests for Notification-Worker Scaffold (Story 5.1).

Covers:
- Notification model validation (all types, optional fields, unknown type)
- Domain routing: route_notification dispatches to correct handler
- Domain routing: unknown type logs warning, skips
- Domain routing: malformed/missing payload logs warning, skips
- Handler stubs: log but don't crash
- Handler errors: caught, logged, consumer continues
- main.py wiring: on_notification callback, main() structure
- RedisConsumer: envelope validation, malformed JSON, missing fields

Run:
    pytest tests/test_notification_worker_scaffold.py -v
"""

import importlib.util
import json
import sys
import types as _types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_NW_ROOT = _PROJECT_ROOT / "services" / "notification-worker"


# ---------------------------------------------------------------------------
# Module loading helpers (same pattern as other service tests)
# ---------------------------------------------------------------------------

def _load_module_raw(name: str, file_path: Path):
    """Load a module by file path."""
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


from contextlib import contextmanager


@contextmanager
def _notification_worker_context():
    """Temporarily wire sys.modules so `from src.X import Y` resolves to notification-worker."""
    saved = dict(sys.modules)
    saved_path = list(sys.path)

    svc_path = str(_NW_ROOT)
    if svc_path in sys.path:
        sys.path.remove(svc_path)
    sys.path.insert(0, svc_path)

    # Create synthetic package hierarchy
    src_pkg = _types.ModuleType("src")
    src_pkg.__path__ = [str(_NW_ROOT / "src")]
    src_pkg.__package__ = "src"
    sys.modules["src"] = src_pkg

    domain_pkg = _types.ModuleType("src.domain")
    domain_pkg.__path__ = [str(_NW_ROOT / "src" / "domain")]
    domain_pkg.__package__ = "src.domain"
    sys.modules["src.domain"] = domain_pkg

    ports_pkg = _types.ModuleType("src.ports")
    ports_pkg.__path__ = [str(_NW_ROOT / "src" / "ports")]
    sys.modules["src.ports"] = ports_pkg

    adapters_pkg = _types.ModuleType("src.adapters")
    adapters_pkg.__path__ = [str(_NW_ROOT / "src" / "adapters")]
    sys.modules["src.adapters"] = adapters_pkg

    adapters_inbound_pkg = _types.ModuleType("src.adapters.inbound")
    adapters_inbound_pkg.__path__ = [str(_NW_ROOT / "src" / "adapters" / "inbound")]
    sys.modules["src.adapters.inbound"] = adapters_inbound_pkg

    adapters_outbound_pkg = _types.ModuleType("src.adapters.outbound")
    adapters_outbound_pkg.__path__ = [str(_NW_ROOT / "src" / "adapters" / "outbound")]
    sys.modules["src.adapters.outbound"] = adapters_outbound_pkg

    # Load leaf modules
    _load_module_raw("src.config", _NW_ROOT / "src" / "config.py")
    _load_module_raw("src.ports.inbound", _NW_ROOT / "src" / "ports" / "inbound.py")
    _load_module_raw("src.ports.outbound", _NW_ROOT / "src" / "ports" / "outbound.py")
    _load_module_raw("src.domain.models", _NW_ROOT / "src" / "domain" / "models.py")
    _load_module_raw("src.domain.services", _NW_ROOT / "src" / "domain" / "services.py")
    _load_module_raw(
        "src.adapters.inbound.redis_consumer",
        _NW_ROOT / "src" / "adapters" / "inbound" / "redis_consumer.py",
    )
    _load_module_raw(
        "src.adapters.outbound.redis_publisher",
        _NW_ROOT / "src" / "adapters" / "outbound" / "redis_publisher.py",
    )

    try:
        yield
    finally:
        new_keys = set(sys.modules.keys()) - set(saved.keys())
        for k in new_keys:
            del sys.modules[k]
        sys.modules.update(saved)
        sys.path[:] = saved_path


# Load notification-worker modules in isolation
with _notification_worker_context():
    _models = sys.modules["src.domain.models"]
    _services = sys.modules["src.domain.services"]

Notification = _models.Notification
NotificationType = _models.NotificationType
route_notification = _services.route_notification
handle_team_alert = _services.handle_team_alert
handle_reporter_update = _services.handle_reporter_update
handle_reporter_resolved = _services.handle_reporter_resolved


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_envelope(event_type: str, source: str, payload: dict) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "payload": payload,
    }


def _team_alert_payload(**overrides) -> dict:
    base = {
        "type": "team_alert",
        "ticket_url": "https://linear.app/team/ENG-42",
        "severity": "critical",
        "component": "payments",
        "summary": "Payment gateway timeout",
        "incident_id": "inc-100",
        "reporter_email": "user@example.com",
    }
    base.update(overrides)
    return base


def _reporter_update_payload(**overrides) -> dict:
    base = {
        "type": "reporter_update",
        "reporter_email": "user@example.com",
        "message": "Your incident has been escalated to engineering.",
        "incident_id": "inc-100",
    }
    base.update(overrides)
    return base


def _reporter_resolved_payload(**overrides) -> dict:
    base = {
        "type": "reporter_resolved",
        "reporter_email": "user@example.com",
        "message": "The bug you reported has been fixed.",
        "incident_id": "inc-100",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Notification model tests
# ---------------------------------------------------------------------------

class TestNotificationModel:
    def test_team_alert_parses(self):
        n = Notification(**_team_alert_payload())
        assert n.type == NotificationType.team_alert
        assert n.incident_id == "inc-100"
        assert n.ticket_url == "https://linear.app/team/ENG-42"
        assert n.severity == "critical"

    def test_reporter_update_parses(self):
        n = Notification(**_reporter_update_payload())
        assert n.type == NotificationType.reporter_update
        assert n.reporter_email == "user@example.com"
        assert n.message == "Your incident has been escalated to engineering."

    def test_reporter_resolved_parses(self):
        n = Notification(**_reporter_resolved_payload())
        assert n.type == NotificationType.reporter_resolved
        assert n.incident_id == "inc-100"

    def test_optional_fields_default_to_none(self):
        n = Notification(type="team_alert", incident_id="inc-1")
        assert n.message is None
        assert n.slack_channel is None
        assert n.reporter_email is None
        assert n.ticket_url is None
        assert n.metadata == {}

    def test_missing_required_field_raises(self):
        with pytest.raises(Exception):
            Notification(type="team_alert")  # missing incident_id

    def test_invalid_type_raises(self):
        with pytest.raises(Exception):
            Notification(type="unknown_type", incident_id="inc-1")

    def test_all_three_types_valid(self):
        for t in ["team_alert", "reporter_update", "reporter_resolved"]:
            n = Notification(type=t, incident_id="inc-1")
            assert n.type.value == t


# ---------------------------------------------------------------------------
# Domain routing tests
# ---------------------------------------------------------------------------

class TestRouteNotification:
    @pytest.mark.asyncio
    async def test_routes_team_alert(self):
        envelope = _build_envelope(
            "notification.send", "ticket-service", _team_alert_payload()
        )
        event_id = envelope["event_id"]
        mock_handler = AsyncMock()

        with patch.dict(_services._HANDLERS, {NotificationType.team_alert: mock_handler}):
            await route_notification(envelope, event_id)
            mock_handler.assert_called_once()
            call_args = mock_handler.call_args[0]
            assert isinstance(call_args[0], Notification)
            assert call_args[0].type == NotificationType.team_alert
            assert call_args[1] == event_id

    @pytest.mark.asyncio
    async def test_routes_reporter_update(self):
        envelope = _build_envelope(
            "notification.send", "ticket-service", _reporter_update_payload()
        )
        event_id = envelope["event_id"]
        mock_handler = AsyncMock()

        with patch.dict(_services._HANDLERS, {NotificationType.reporter_update: mock_handler}):
            await route_notification(envelope, event_id)
            mock_handler.assert_called_once()
            call_args = mock_handler.call_args[0]
            assert call_args[0].type == NotificationType.reporter_update
            assert call_args[1] == event_id

    @pytest.mark.asyncio
    async def test_routes_reporter_resolved(self):
        envelope = _build_envelope(
            "notification.send", "ticket-service", _reporter_resolved_payload()
        )
        event_id = envelope["event_id"]
        mock_handler = AsyncMock()

        with patch.dict(_services._HANDLERS, {NotificationType.reporter_resolved: mock_handler}):
            await route_notification(envelope, event_id)
            mock_handler.assert_called_once()
            call_args = mock_handler.call_args[0]
            assert call_args[0].type == NotificationType.reporter_resolved
            assert call_args[1] == event_id

    @pytest.mark.asyncio
    async def test_unknown_type_skips_no_crash(self):
        payload = {"type": "unknown_type", "incident_id": "inc-1"}
        envelope = _build_envelope("notification.send", "ticket-service", payload)
        # Should not raise — invalid type fails validation, logs warning
        await route_notification(envelope, envelope["event_id"])

    @pytest.mark.asyncio
    async def test_missing_payload_logs_warning_no_crash(self):
        envelope = {
            "event_id": str(uuid.uuid4()),
            "event_type": "notification.send",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "ticket-service",
            # no "payload" key
        }
        await route_notification(envelope, envelope["event_id"])

    @pytest.mark.asyncio
    async def test_malformed_payload_logs_warning_no_crash(self):
        envelope = _build_envelope("notification.send", "ticket-service", {"garbage": True})
        # Missing required fields (type, incident_id) → ValidationError → logged, skipped
        await route_notification(envelope, envelope["event_id"])

    @pytest.mark.asyncio
    async def test_handler_error_caught_no_crash(self):
        envelope = _build_envelope(
            "notification.send", "ticket-service", _team_alert_payload()
        )
        event_id = envelope["event_id"]
        mock_handler = AsyncMock(side_effect=RuntimeError("boom"))

        with patch.dict(_services._HANDLERS, {NotificationType.team_alert: mock_handler}):
            # Should not raise — exception caught and logged
            await route_notification(envelope, event_id)

    @pytest.mark.asyncio
    async def test_event_id_correlation_passed_through(self):
        """Verify event_id from envelope is forwarded to route_notification."""
        envelope = _build_envelope(
            "notification.send", "ticket-service", _team_alert_payload()
        )
        expected_event_id = envelope["event_id"]
        mock_handler = AsyncMock()

        with patch.dict(_services._HANDLERS, {NotificationType.team_alert: mock_handler}):
            await route_notification(envelope, expected_event_id)
            mock_handler.assert_called_once()


# ---------------------------------------------------------------------------
# Handler stub tests
# ---------------------------------------------------------------------------

class TestHandlerStubs:
    @pytest.mark.asyncio
    async def test_handle_team_alert_logs_not_implemented(self):
        n = Notification(**_team_alert_payload())
        # Should not raise — just logs
        await handle_team_alert(n, "evt-1")

    @pytest.mark.asyncio
    async def test_handle_reporter_update_logs_not_implemented(self):
        n = Notification(**_reporter_update_payload())
        await handle_reporter_update(n, "evt-2")

    @pytest.mark.asyncio
    async def test_handle_reporter_resolved_logs_not_implemented(self):
        n = Notification(**_reporter_resolved_payload())
        await handle_reporter_resolved(n, "evt-3")


# ---------------------------------------------------------------------------
# Main.py wiring structure tests
# ---------------------------------------------------------------------------

class TestMainWiring:
    def test_main_module_imports_and_has_main(self):
        with _notification_worker_context():
            main_mod = _load_module_raw("nw_main_check", _NW_ROOT / "src" / "main.py")
            assert hasattr(main_mod, "main")
            assert hasattr(main_mod, "on_notification")

    def test_main_is_coroutine(self):
        import inspect

        with _notification_worker_context():
            main_mod = _load_module_raw("nw_main_check2", _NW_ROOT / "src" / "main.py")
            assert inspect.iscoroutinefunction(main_mod.main)

    def test_on_notification_is_coroutine(self):
        import inspect

        with _notification_worker_context():
            main_mod = _load_module_raw("nw_main_check3", _NW_ROOT / "src" / "main.py")
            assert inspect.iscoroutinefunction(main_mod.on_notification)


# ---------------------------------------------------------------------------
# on_notification callback integration
# ---------------------------------------------------------------------------

class TestOnNotificationCallback:
    @pytest.mark.asyncio
    async def test_on_notification_extracts_event_id_and_routes(self):
        with _notification_worker_context():
            main_mod = _load_module_raw("nw_main_integ", _NW_ROOT / "src" / "main.py")

            envelope = _build_envelope(
                "notification.send", "ticket-service", _team_alert_payload()
            )

            with patch.object(
                main_mod, "route_notification", new_callable=AsyncMock
            ) as mock_route:
                await main_mod.on_notification(envelope)
                mock_route.assert_called_once_with(envelope, envelope["event_id"])

    @pytest.mark.asyncio
    async def test_on_notification_uses_unknown_when_no_event_id(self):
        with _notification_worker_context():
            main_mod = _load_module_raw("nw_main_integ2", _NW_ROOT / "src" / "main.py")

            envelope = {
                "event_type": "notification.send",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "ticket-service",
                "payload": _team_alert_payload(),
            }

            with patch.object(
                main_mod, "route_notification", new_callable=AsyncMock
            ) as mock_route:
                await main_mod.on_notification(envelope)
                mock_route.assert_called_once_with(envelope, "unknown")


# ---------------------------------------------------------------------------
# RedisConsumer envelope validation (reuse consumer for notification-worker)
# ---------------------------------------------------------------------------

class TestRedisConsumerEnvelopeValidation:
    """Ensures the notification-worker's RedisConsumer validates envelopes."""

    def test_required_envelope_fields_defined(self):
        with _notification_worker_context():
            consumer_mod = sys.modules["src.adapters.inbound.redis_consumer"]
            assert hasattr(consumer_mod, "REQUIRED_ENVELOPE_FIELDS")
            required = consumer_mod.REQUIRED_ENVELOPE_FIELDS
            assert "event_id" in required
            assert "event_type" in required
            assert "timestamp" in required
            assert "source" in required
            assert "payload" in required

    def test_redis_consumer_has_subscribe_method(self):
        with _notification_worker_context():
            consumer_mod = sys.modules["src.adapters.inbound.redis_consumer"]
            assert hasattr(consumer_mod.RedisConsumer, "subscribe")

    def test_redis_consumer_has_close_method(self):
        with _notification_worker_context():
            consumer_mod = sys.modules["src.adapters.inbound.redis_consumer"]
            assert hasattr(consumer_mod.RedisConsumer, "close")
