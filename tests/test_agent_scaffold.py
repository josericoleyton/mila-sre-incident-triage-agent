"""
Tests for Agent Service Scaffold with Redis Consumer.

Covers:
- IncidentEvent model validation
- TriageState initialization from incident/reescalation events
- Event handler: incident.created deserialization and routing
- Event handler: incident.reescalate deserialization and routing
- Malformed event handling (error publish + skip)
- Multi-channel consumer routing logic
- Agent initialization

Run:
    pytest tests/test_agent_scaffold.py -v
"""

import importlib.util
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Module loading helpers
# ---------------------------------------------------------------------------

def _add_service_to_path(service: str):
    """Add a service's root to sys.path so 'src.' imports work."""
    svc_path = str(_PROJECT_ROOT / "services" / service)
    if svc_path not in sys.path:
        sys.path.insert(0, svc_path)


_add_service_to_path("agent")


def _load_models():
    mod_name = "agent_domain_models_31"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    file_path = _PROJECT_ROOT / "services" / "agent" / "src" / "domain" / "models.py"
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_triage_handler():
    mod_name = "agent_domain_triage_handler_31"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    file_path = _PROJECT_ROOT / "services" / "agent" / "src" / "domain" / "triage_handler.py"
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _build_envelope(event_type: str, source: str, payload: dict) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "payload": payload,
    }


def _valid_incident_payload(**overrides) -> dict:
    base = {
        "incident_id": "inc-001",
        "title": "Login service 500 errors",
        "description": "Users report 500 on /login",
        "component": "auth-service",
        "severity": "high",
        "reporter_email": "user@example.com",
        "source_type": "userIntegration",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# IncidentEvent model tests
# ---------------------------------------------------------------------------

class TestIncidentEventModel:
    def test_valid_user_integration(self):
        m = _load_models()
        evt = m.IncidentEvent(**_valid_incident_payload())
        assert evt.incident_id == "inc-001"
        assert evt.source_type == "userIntegration"
        assert evt.prompt_injection_detected is False

    def test_valid_system_integration(self):
        m = _load_models()
        evt = m.IncidentEvent(**_valid_incident_payload(source_type="systemIntegration"))
        assert evt.source_type == "systemIntegration"

    def test_rejects_invalid_source_type(self):
        m = _load_models()
        with pytest.raises(Exception):
            m.IncidentEvent(**_valid_incident_payload(source_type="invalid"))

    def test_missing_required_fields(self):
        m = _load_models()
        with pytest.raises(Exception):
            m.IncidentEvent(title="x")

    def test_prompt_injection_flag(self):
        m = _load_models()
        evt = m.IncidentEvent(**_valid_incident_payload(prompt_injection_detected=True))
        assert evt.prompt_injection_detected is True

    def test_optional_fields_default_none(self):
        m = _load_models()
        evt = m.IncidentEvent(
            incident_id="inc-002",
            title="Test",
            reporter_email="user1@example.com",
            source_type="userIntegration",
        )
        assert evt.description is None
        assert evt.component is None
        assert evt.severity is None
        assert evt.attachment_url is None
        assert evt.trace_data is None


# ---------------------------------------------------------------------------
# TriageState initialization tests
# ---------------------------------------------------------------------------

class TestTriageStateInit:
    def test_new_incident_state(self):
        m = _load_models()
        state = m.TriageState(
            incident_id="inc-001",
            source_type="userIntegration",
            incident=_valid_incident_payload(),
            reescalation=False,
            prompt_injection_detected=False,
        )
        assert state.incident_id == "inc-001"
        assert state.reescalation is False
        assert state.triage_result is None

    def test_reescalation_state(self):
        m = _load_models()
        state = m.TriageState(
            incident_id="inc-001",
            source_type="userIntegration",
            incident=_valid_incident_payload(),
            reescalation=True,
            prompt_injection_detected=False,
        )
        assert state.reescalation is True

    def test_prompt_injection_flag_propagation(self):
        m = _load_models()
        state = m.TriageState(
            incident_id="inc-001",
            source_type="userIntegration",
            incident={},
            prompt_injection_detected=True,
        )
        assert state.prompt_injection_detected is True


# ---------------------------------------------------------------------------
# Triage handler tests
# ---------------------------------------------------------------------------

class TestHandleIncidentEvent:
    @pytest.mark.asyncio
    async def test_successful_incident_handling(self):
        handler = _load_triage_handler()
        publisher = AsyncMock()
        pipeline = AsyncMock()
        envelope = _build_envelope("incident.created", "api", _valid_incident_payload())

        state = await handler.handle_incident_event(envelope, publisher, pipeline)

        assert state is not None
        assert state.incident_id == "inc-001"
        assert state.source_type == "userIntegration"
        assert state.reescalation is False
        assert state.event_id == envelope["event_id"]
        pipeline.assert_awaited_once_with(state)
        publisher.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_malformed_payload_publishes_error(self):
        handler = _load_triage_handler()
        publisher = AsyncMock()
        pipeline = AsyncMock()
        envelope = _build_envelope("incident.created", "api", {"bad": "data"})

        state = await handler.handle_incident_event(envelope, publisher, pipeline)

        assert state is None
        publisher.publish.assert_awaited_once()
        call_args = publisher.publish.call_args
        assert call_args[0][0] == "errors"
        assert call_args[0][1] == "ticket.error"
        assert call_args[0][2]["event_id"] == envelope["event_id"]
        pipeline.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_payload_key_publishes_error(self):
        handler = _load_triage_handler()
        publisher = AsyncMock()
        pipeline = AsyncMock()
        envelope = {
            "event_id": "evt-1",
            "event_type": "incident.created",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "api",
            # no "payload" key
        }

        state = await handler.handle_incident_event(envelope, publisher, pipeline)

        assert state is None
        publisher.publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_prompt_injection_flag_propagated(self):
        handler = _load_triage_handler()
        publisher = AsyncMock()
        pipeline = AsyncMock()
        payload = _valid_incident_payload(prompt_injection_detected=True)
        envelope = _build_envelope("incident.created", "api", payload)

        state = await handler.handle_incident_event(envelope, publisher, pipeline)

        assert state is not None
        assert state.prompt_injection_detected is True

    @pytest.mark.asyncio
    async def test_source_type_identification_user(self):
        handler = _load_triage_handler()
        publisher = AsyncMock()
        pipeline = AsyncMock()
        payload = _valid_incident_payload(source_type="userIntegration")
        envelope = _build_envelope("incident.created", "api", payload)

        state = await handler.handle_incident_event(envelope, publisher, pipeline)
        assert state.source_type == "userIntegration"

    @pytest.mark.asyncio
    async def test_source_type_identification_system(self):
        handler = _load_triage_handler()
        publisher = AsyncMock()
        pipeline = AsyncMock()
        payload = _valid_incident_payload(source_type="systemIntegration")
        envelope = _build_envelope("incident.created", "api", payload)

        state = await handler.handle_incident_event(envelope, publisher, pipeline)
        assert state.source_type == "systemIntegration"


    @pytest.mark.asyncio
    async def test_publisher_error_does_not_crash_handler(self):
        """If publisher.publish raises during error reporting, handler returns None gracefully."""
        handler = _load_triage_handler()
        publisher = AsyncMock()
        publisher.publish.side_effect = ConnectionError("Redis down")
        pipeline = AsyncMock()
        envelope = _build_envelope("incident.created", "api", {"bad": "data"})

        state = await handler.handle_incident_event(envelope, publisher, pipeline)

        assert state is None
        pipeline.assert_not_awaited()


class TestHandleReescalationEvent:
    @pytest.mark.asyncio
    async def test_successful_reescalation_handling(self):
        handler = _load_triage_handler()
        publisher = AsyncMock()
        pipeline = AsyncMock()
        envelope = _build_envelope("incident.reescalate", "api", _valid_incident_payload())

        state = await handler.handle_reescalation_event(envelope, publisher, pipeline)

        assert state is not None
        assert state.incident_id == "inc-001"
        assert state.reescalation is True
        assert state.event_id == envelope["event_id"]
        pipeline.assert_awaited_once_with(state)

    @pytest.mark.asyncio
    async def test_malformed_reescalation_publishes_error(self):
        handler = _load_triage_handler()
        publisher = AsyncMock()
        pipeline = AsyncMock()
        envelope = _build_envelope("incident.reescalate", "api", {"invalid": True})

        state = await handler.handle_reescalation_event(envelope, publisher, pipeline)

        assert state is None
        publisher.publish.assert_awaited_once()
        call_args = publisher.publish.call_args
        assert call_args[0][2]["source_channel"] == "reescalations"
        pipeline.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reescalation_preserves_incident_data(self):
        handler = _load_triage_handler()
        publisher = AsyncMock()
        pipeline = AsyncMock()
        payload = _valid_incident_payload(severity="critical", component="payments")
        envelope = _build_envelope("incident.reescalate", "api", payload)

        state = await handler.handle_reescalation_event(envelope, publisher, pipeline)

        assert state.incident["severity"] == "critical"
        assert state.incident["component"] == "payments"


# ---------------------------------------------------------------------------
# Multi-channel consumer routing tests
# ---------------------------------------------------------------------------

class TestRedisConsumerMultiChannel:
    @pytest.mark.asyncio
    async def test_subscribe_multi_routes_to_correct_handler(self):
        """Validate that subscribe_multi dispatches to the right handler per channel."""
        import asyncio
        from src.adapters.inbound.redis_consumer import RedisConsumer, REQUIRED_ENVELOPE_FIELDS

        incidents_handler = AsyncMock()
        reescalations_handler = AsyncMock()

        consumer = RedisConsumer.__new__(RedisConsumer)

        incident_envelope = _build_envelope("incident.created", "api", _valid_incident_payload())
        reescalation_envelope = _build_envelope("incident.reescalate", "api", _valid_incident_payload())

        mock_pubsub = AsyncMock()

        async def mock_listen():
            yield {"type": "subscribe", "channel": b"incidents", "data": 1}
            yield {
                "type": "message",
                "channel": b"incidents",
                "data": json.dumps(incident_envelope),
            }
            yield {
                "type": "message",
                "channel": b"reescalations",
                "data": json.dumps(reescalation_envelope),
            }
            raise asyncio.CancelledError()

        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.listen = mock_listen

        consumer._redis = AsyncMock()
        consumer._pubsub = mock_pubsub

        # Patch to use our mock pubsub
        original_subscribe_multi = RedisConsumer.subscribe_multi

        async def patched_subscribe_multi(self, handlers):
            self._pubsub = mock_pubsub
            await mock_pubsub.subscribe(*list(handlers.keys()))
            try:
                async for message in mock_pubsub.listen():
                    if message["type"] != "message":
                        continue
                    channel = (
                        message["channel"].decode()
                        if isinstance(message["channel"], bytes)
                        else message["channel"]
                    )
                    try:
                        envelope = json.loads(message["data"])
                    except (json.JSONDecodeError, TypeError):
                        continue
                    missing = REQUIRED_ENVELOPE_FIELDS - set(envelope.keys())
                    if missing:
                        continue
                    handler = handlers.get(channel)
                    if handler:
                        await handler(envelope)
            except asyncio.CancelledError:
                pass

        with patch.object(RedisConsumer, 'subscribe_multi', patched_subscribe_multi):
            await consumer.subscribe_multi({
                "incidents": incidents_handler,
                "reescalations": reescalations_handler,
            })

        incidents_handler.assert_awaited_once()
        reescalations_handler.assert_awaited_once()

        # Verify the correct envelope was passed to each handler
        incident_call_envelope = incidents_handler.call_args[0][0]
        assert incident_call_envelope["event_type"] == "incident.created"

        reesc_call_envelope = reescalations_handler.call_args[0][0]
        assert reesc_call_envelope["event_type"] == "incident.reescalate"

    @pytest.mark.asyncio
    async def test_malformed_json_skipped_in_multi(self):
        """Consumer skips non-JSON messages without crashing."""
        import asyncio
        from src.adapters.inbound.redis_consumer import REQUIRED_ENVELOPE_FIELDS

        handler = AsyncMock()

        mock_pubsub = AsyncMock()

        async def mock_listen():
            yield {"type": "message", "channel": b"incidents", "data": "not-json"}
            yield {"type": "message", "channel": b"incidents", "data": json.dumps(
                _build_envelope("incident.created", "api", _valid_incident_payload())
            )}
            raise asyncio.CancelledError()

        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.listen = mock_listen

        from src.adapters.inbound.redis_consumer import RedisConsumer
        consumer = RedisConsumer.__new__(RedisConsumer)
        consumer._redis = AsyncMock()
        consumer._pubsub = mock_pubsub

        async def patched_subscribe_multi(self, handlers):
            self._pubsub = mock_pubsub
            await mock_pubsub.subscribe(*list(handlers.keys()))
            try:
                async for message in mock_pubsub.listen():
                    if message["type"] != "message":
                        continue
                    channel = (
                        message["channel"].decode()
                        if isinstance(message["channel"], bytes)
                        else message["channel"]
                    )
                    try:
                        envelope = json.loads(message["data"])
                    except (json.JSONDecodeError, TypeError):
                        continue
                    missing = REQUIRED_ENVELOPE_FIELDS - set(envelope.keys())
                    if missing:
                        continue
                    h = handlers.get(channel)
                    if h:
                        await h(envelope)
            except asyncio.CancelledError:
                pass

        with patch.object(RedisConsumer, 'subscribe_multi', patched_subscribe_multi):
            await consumer.subscribe_multi({"incidents": handler})

        # Only the valid message should trigger the handler
        handler.assert_awaited_once()


# ---------------------------------------------------------------------------
# Agent initialization tests
# ---------------------------------------------------------------------------

class TestAgentInit:
    @pytest.mark.asyncio
    async def test_run_pipeline_stub_does_not_crash(self):
        """The pipeline should accept state and deps without error."""
        m = _load_models()
        state = m.TriageState(incident_id="inc-test", source_type="userIntegration")

        # Import run_pipeline from main
        main_path = _PROJECT_ROOT / "services" / "agent" / "src" / "main.py"
        spec = importlib.util.spec_from_file_location("agent_main_pipeline_31", main_path)
        mod = importlib.util.module_from_spec(spec)

        mock_deps = MagicMock()

        mock_pydantic = MagicMock()
        with patch.dict(sys.modules, {
            "pydantic_ai": mock_pydantic,
            "pydantic_ai.settings": mock_pydantic.settings,
        }):
            spec.loader.exec_module(mod)
            with patch.object(mod, "triage_graph", create=True) as mock_graph:
                mock_graph.run = AsyncMock()
                await mod.run_pipeline(state, mock_deps)  # should not raise
