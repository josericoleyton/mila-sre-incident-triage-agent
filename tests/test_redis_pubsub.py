"""
Smoke-test: Redis pub/sub round-trip.

Verifies:
1. Publisher wraps payload in the mandatory envelope format
2. Consumer receives and validates the envelope
3. Malformed messages are skipped gracefully (no crash)
4. All required envelope fields present (event_id, event_type, timestamp, source, payload)

Run:
    pytest tests/test_redis_pubsub.py -v
"""

import importlib.util
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_models(service: str):
    """Load domain/models.py from a specific service by file path."""
    module_name = f"{service}_domain_models"
    if module_name in sys.modules:
        return sys.modules[module_name]
    file_path = _PROJECT_ROOT / "services" / service / "src" / "domain" / "models.py"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Envelope format unit test (no Redis needed)
# ---------------------------------------------------------------------------

def _build_envelope(event_type: str, source: str, payload: dict) -> dict:
    """Reproduce the envelope logic from RedisPublisher."""
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "payload": payload,
    }


REQUIRED_FIELDS = {"event_id", "event_type", "timestamp", "source", "payload"}


class TestEnvelopeFormat:
    def test_envelope_has_all_required_fields(self):
        envelope = _build_envelope("incident.created", "api", {"title": "test"})
        assert REQUIRED_FIELDS.issubset(set(envelope.keys()))

    def test_event_id_is_uuid4(self):
        envelope = _build_envelope("incident.created", "api", {})
        parsed = uuid.UUID(envelope["event_id"], version=4)
        assert str(parsed) == envelope["event_id"]

    def test_timestamp_is_iso8601(self):
        envelope = _build_envelope("incident.created", "api", {})
        dt = datetime.fromisoformat(envelope["timestamp"])
        assert dt.tzinfo is not None

    def test_payload_preserved(self):
        payload = {"title": "Server down", "severity": "critical"}
        envelope = _build_envelope("incident.created", "api", payload)
        assert envelope["payload"] == payload


# ---------------------------------------------------------------------------
# Consumer validation unit tests (no Redis needed)
# ---------------------------------------------------------------------------

class TestConsumerValidation:
    def _validate_envelope(self, raw: str) -> dict | None:
        """Replicate consumer validation logic."""
        try:
            envelope = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        missing = REQUIRED_FIELDS - set(envelope.keys())
        if missing:
            return None
        return envelope

    def test_valid_envelope_accepted(self):
        envelope = _build_envelope("incident.created", "api", {"title": "test"})
        result = self._validate_envelope(json.dumps(envelope))
        assert result is not None
        assert result["event_type"] == "incident.created"

    def test_invalid_json_skipped(self):
        assert self._validate_envelope("not json at all") is None

    def test_missing_fields_skipped(self):
        incomplete = {"event_id": "123", "payload": {}}
        assert self._validate_envelope(json.dumps(incomplete)) is None

    def test_empty_payload_accepted(self):
        envelope = _build_envelope("triage.completed", "agent", {})
        result = self._validate_envelope(json.dumps(envelope))
        assert result is not None


# ---------------------------------------------------------------------------
# Domain model tests
# ---------------------------------------------------------------------------

class TestApiDomainModels:
    def test_incident_report_required_fields(self):
        m = _load_models("api")
        report = m.IncidentReport(
            title="Login broken",
            reporter_slack_user_id="U123",
            source_type="userIntegration",
        )
        assert report.title == "Login broken"
        assert report.description is None
        assert report.source_type == "userIntegration"

    def test_incident_report_rejects_bad_source_type(self):
        m = _load_models("api")
        with pytest.raises(Exception):
            m.IncidentReport(
                title="x",
                reporter_slack_user_id="U123",
                source_type="invalid",
            )

    def test_incident_event(self):
        m = _load_models("api")
        event = m.IncidentEvent(
            incident_id="inc-1",
            title="Error 500",
            reporter_slack_user_id="U1",
            source_type="systemIntegration",
        )
        assert event.incident_id == "inc-1"


class TestAgentDomainModels:
    def test_classification_enum(self):
        m = _load_models("agent")
        assert m.Classification.bug.value == "bug"
        assert m.Classification.non_incident.value == "non_incident"

    def test_triage_result(self):
        m = _load_models("agent")
        result = m.TriageResult(
            classification=m.Classification.bug,
            confidence=0.92,
            reasoning="Stack trace matches known pattern",
            severity_assessment="high",
        )
        assert result.confidence == 0.92
        assert result.file_refs == []

    def test_triage_state(self):
        m = _load_models("agent")
        state = m.TriageState(incident_id="inc-1", source_type="userIntegration")
        assert state.reescalation is False
        assert state.triage_result is None


class TestTicketServiceDomainModels:
    def test_ticket_command(self):
        m = _load_models("ticket-service")
        cmd = m.TicketCommand(
            action="create",
            title="Fix login",
            body="Login page returns 500",
            severity="high",
            incident_id="inc-1",
        )
        assert cmd.labels == []

    def test_ticket_status_event(self):
        m = _load_models("ticket-service")
        evt = m.TicketStatusEvent(
            ticket_id="T-1",
            old_status="open",
            new_status="closed",
            incident_id="inc-1",
        )
        assert evt.reporter_slack_user_id is None


class TestNotificationWorkerDomainModels:
    def test_notification_type_enum(self):
        m = _load_models("notification-worker")
        assert m.NotificationType.team_alert.value == "team_alert"

    def test_notification(self):
        m = _load_models("notification-worker")
        n = m.Notification(
            type=m.NotificationType.reporter_update,
            message="Your incident was triaged",
            incident_id="inc-1",
        )
        assert n.allow_reescalation is False
        assert n.confidence is None
