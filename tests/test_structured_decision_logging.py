"""
Tests for Story 6.1: Structured Decision Logging Across Pipeline

Covers:
- StructuredJsonFormatter: proper JSON output with required fields
- setup_logging: configures root logger correctly
- _build_input_summary: metadata-only input summary (NFR5)
- _build_triage_completed_payload: enhanced with input_summary + files_examined
- NFR5 compliance: no raw user text in triage.completed payload
- Pipeline stage logging: each service produces structured log entries
- search_code log sanitization: no raw query in logs

Run:
    pytest tests/test_structured_decision_logging.py -v
"""

import importlib.util
import json
import logging
import sys
import time
import uuid
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _add_service_to_path(service: str):
    svc_path = str(_PROJECT_ROOT / "services" / service)
    if svc_path not in sys.path:
        sys.path.insert(0, svc_path)


# Only add agent to path — other services' json_logging.py have no internal imports
# so they can be loaded via importlib without adding to sys.path.
_add_service_to_path("agent")


def _load_module(mod_name: str, rel_path: str):
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    file_path = _PROJECT_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_json_logging(service: str):
    mod_name = f"{service.replace('-', '_')}_json_logging_61"
    return _load_module(mod_name, f"services/{service}/src/json_logging.py")


def _load_agent_models():
    return _load_module("agent_models_61", "services/agent/src/domain/models.py")


def _load_generate_output():
    return _load_module("agent_gen_output_61", "services/agent/src/graph/nodes/generate_output.py")


def _valid_incident(**overrides) -> dict:
    base = {
        "incident_id": "inc-601",
        "title": "NullReferenceException in OrderController.cs",
        "description": "Users report checkout 500 errors on empty cart.",
        "component": "Ordering",
        "severity": "High",
        "attachment_url": "https://example.com/screenshot.png",
        "reporter_slack_user_id": "U99999",
        "source_type": "userIntegration",
    }
    base.update(overrides)
    return base


def _make_state(**overrides):
    m = _load_agent_models()
    incident = overrides.pop("incident", _valid_incident())
    defaults = {
        "incident_id": incident.get("incident_id", "inc-601"),
        "source_type": incident.get("source_type", "userIntegration"),
        "event_id": str(uuid.uuid4()),
        "incident": incident,
        "reescalation": False,
        "prompt_injection_detected": False,
        "triage_started_at": time.monotonic(),
    }
    defaults.update(overrides)
    return m.TriageState(**defaults)


def _make_bug_result(**overrides):
    m = _load_agent_models()
    defaults = {
        "classification": m.Classification.bug,
        "confidence": 0.87,
        "reasoning": "Found NullReferenceException in OrderController.ProcessOrder(). Traced execution path.",
        "file_refs": [
            "src/Ordering.API/Controllers/OrderController.cs (lines 42-58)",
            "src/Ordering.API/Services/OrderService.cs (lines 110-125)",
        ],
        "root_cause": "NullReferenceException when order items collection is empty",
        "suggested_fix": "Add null/empty check for order.Items before calling CalculateTotal()",
        "severity_assessment": "high — affects checkout flow but only on edge case",
    }
    defaults.update(overrides)
    return m.TriageResult(**defaults)


def _make_non_incident_result(**overrides):
    m = _load_agent_models()
    defaults = {
        "classification": m.Classification.non_incident,
        "confidence": 0.92,
        "reasoning": "User error — expected behavior when cart is cleared",
        "resolution_explanation": "This is expected behavior",
        "severity_assessment": "low — no impact",
    }
    defaults.update(overrides)
    return m.TriageResult(**defaults)


# ============================================================================
# StructuredJsonFormatter tests
# ============================================================================

class TestStructuredJsonFormatter:
    """Verify the JSON formatter produces valid JSON with all required fields."""

    def _make_formatted_output(self, service: str, msg: str, **kwargs) -> dict:
        mod = _load_json_logging(service)
        formatter = mod.StructuredJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in kwargs.items():
            setattr(record, k, v)
        output = formatter.format(record)
        return json.loads(output)

    def test_output_is_valid_json(self):
        entry = self._make_formatted_output("api", "test message")
        assert isinstance(entry, dict)

    def test_required_fields_present(self):
        entry = self._make_formatted_output("api", "test message")
        assert "timestamp" in entry
        assert "level" in entry
        assert "service" in entry
        assert "event_id" in entry
        assert "message" in entry

    def test_service_name_correct_api(self):
        entry = self._make_formatted_output("api", "test")
        assert entry["service"] == "api"

    def test_service_name_correct_agent(self):
        entry = self._make_formatted_output("agent", "test")
        assert entry["service"] == "agent"

    def test_service_name_correct_ticket_service(self):
        entry = self._make_formatted_output("ticket-service", "test")
        assert entry["service"] == "ticket-service"

    def test_service_name_correct_notification_worker(self):
        entry = self._make_formatted_output("notification-worker", "test")
        assert entry["service"] == "notification-worker"

    def test_timestamp_is_iso8601(self):
        entry = self._make_formatted_output("api", "test")
        ts = entry["timestamp"]
        assert "T" in ts
        assert ts.endswith("Z")

    def test_level_is_string(self):
        entry = self._make_formatted_output("api", "test")
        assert entry["level"] == "INFO"

    def test_message_preserved(self):
        entry = self._make_formatted_output("api", "hello world")
        assert entry["message"] == "hello world"

    def test_event_id_empty_when_not_set(self):
        entry = self._make_formatted_output("api", "test")
        assert entry["event_id"] == ""

    def test_event_id_from_record_attribute(self):
        entry = self._make_formatted_output("api", "test", event_id="evt-123")
        assert entry["event_id"] == "evt-123"

    def test_error_field_on_exception(self):
        mod = _load_json_logging("api")
        formatter = mod.StructuredJsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys as _sys
            exc_info = _sys.exc_info()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="something failed",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        entry = json.loads(output)
        assert "error" in entry
        assert "ValueError" in entry["error"]
        assert "boom" in entry["error"]

    def test_no_error_field_without_exception(self):
        entry = self._make_formatted_output("api", "no error")
        assert "error" not in entry


class TestSetupLogging:
    """Verify setup_logging configures root logger with JSON formatter."""

    def test_setup_adds_handler(self):
        mod = _load_json_logging("api")
        root = logging.getLogger()
        old_handlers = list(root.handlers)
        try:
            mod.setup_logging()
            assert len(root.handlers) == 1
            handler = root.handlers[0]
            assert isinstance(handler.formatter, mod.StructuredJsonFormatter)
        finally:
            root.handlers = old_handlers

    def test_setup_clears_previous_handlers(self):
        mod = _load_json_logging("api")
        root = logging.getLogger()
        old_handlers = list(root.handlers)
        try:
            root.addHandler(logging.StreamHandler())
            root.addHandler(logging.StreamHandler())
            assert len(root.handlers) >= 2
            mod.setup_logging()
            assert len(root.handlers) == 1
        finally:
            root.handlers = old_handlers

    def test_timestamp_uses_record_created(self):
        """Timestamp should reflect event time (record.created), not format time."""
        mod = _load_json_logging("api")
        formatter = mod.StructuredJsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="ts test", args=(), exc_info=None,
        )
        # Set a known creation time: 2000-01-01T00:00:00Z
        record.created = 946684800.0
        output = formatter.format(record)
        entry = json.loads(output)
        assert entry["timestamp"].startswith("2000-01-01T00:00:00")

    def test_getmessage_failure_falls_back_to_str(self):
        """If record.getMessage() raises, formatter should fallback gracefully."""
        mod = _load_json_logging("api")
        formatter = mod.StructuredJsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="value is %d", args=("not_a_number",), exc_info=None,
        )
        output = formatter.format(record)
        entry = json.loads(output)
        # Should not crash — falls back to str(record.msg)
        assert entry["message"] == "value is %d"


# ============================================================================
# _build_input_summary tests (metadata-only — NFR5)
# ============================================================================

class TestBuildInputSummary:
    """Verify input_summary contains only metadata, never raw user text."""

    def test_summary_has_required_fields(self):
        mod = _load_generate_output()
        state = _make_state()
        summary = mod._build_input_summary(state)
        assert "title_length" in summary
        assert "has_description" in summary
        assert "component" in summary
        assert "severity" in summary
        assert "has_attachment" in summary
        assert "source_type" in summary

    def test_title_length_not_title_text(self):
        mod = _load_generate_output()
        state = _make_state()
        summary = mod._build_input_summary(state)
        assert isinstance(summary["title_length"], int)
        assert summary["title_length"] == len("NullReferenceException in OrderController.cs")

    def test_has_description_is_boolean(self):
        mod = _load_generate_output()
        state = _make_state()
        summary = mod._build_input_summary(state)
        assert summary["has_description"] is True

    def test_has_description_false_when_empty(self):
        mod = _load_generate_output()
        incident = _valid_incident(description="")
        state = _make_state(incident=incident)
        summary = mod._build_input_summary(state)
        assert summary["has_description"] is False

    def test_has_description_false_when_none(self):
        mod = _load_generate_output()
        incident = _valid_incident(description=None)
        state = _make_state(incident=incident)
        summary = mod._build_input_summary(state)
        assert summary["has_description"] is False

    def test_component_and_severity_passed_through(self):
        mod = _load_generate_output()
        state = _make_state()
        summary = mod._build_input_summary(state)
        assert summary["component"] == "Ordering"
        assert summary["severity"] == "High"

    def test_has_attachment_true(self):
        mod = _load_generate_output()
        state = _make_state()
        summary = mod._build_input_summary(state)
        assert summary["has_attachment"] is True

    def test_has_attachment_false_when_missing(self):
        mod = _load_generate_output()
        incident = _valid_incident(attachment_url=None)
        state = _make_state(incident=incident)
        summary = mod._build_input_summary(state)
        assert summary["has_attachment"] is False

    def test_source_type_propagated(self):
        mod = _load_generate_output()
        state = _make_state()
        summary = mod._build_input_summary(state)
        assert summary["source_type"] == "userIntegration"

    def test_no_raw_user_text_in_summary(self):
        """NFR5: input_summary must NEVER contain raw user input."""
        mod = _load_generate_output()
        state = _make_state()
        summary = mod._build_input_summary(state)
        summary_str = json.dumps(summary)
        # Verify no raw incident title or description
        assert "NullReferenceException" not in summary_str
        assert "checkout 500 errors" not in summary_str
        assert "empty cart" not in summary_str

    def test_non_string_title_does_not_crash(self):
        """Guard: non-string title (e.g. int from malformed JSON) should not raise TypeError."""
        mod = _load_generate_output()
        incident = _valid_incident()
        incident["title"] = 12345  # integer instead of string
        state = _make_state(incident=incident)
        summary = mod._build_input_summary(state)
        assert summary["title_length"] == 5  # len("12345")
        assert isinstance(summary["title_length"], int)


# ============================================================================
# Enhanced _build_triage_completed_payload tests
# ============================================================================

class TestBuildTriageCompletedPayloadEnhanced:
    """Verify triage.completed payload includes new fields from Story 6.1."""

    def test_payload_includes_input_summary(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=1500)
        assert "input_summary" in payload
        assert isinstance(payload["input_summary"], dict)
        assert "title_length" in payload["input_summary"]

    def test_payload_includes_files_examined(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=1500)
        assert "files_examined" in payload
        assert isinstance(payload["files_examined"], list)
        assert len(payload["files_examined"]) == 2
        assert "OrderController.cs" in payload["files_examined"][0]

    def test_files_examined_empty_when_no_refs(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result(file_refs=[])
        payload = mod._build_triage_completed_payload(state, result, duration_ms=500)
        assert payload["files_examined"] == []

    def test_all_required_ac_fields_present(self):
        """Verify ALL fields from Story 6.1 AC are present."""
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=1500)

        # All fields from the first AC
        assert "incident_id" in payload
        assert "source_type" in payload
        assert "input_summary" in payload
        assert "classification" in payload
        assert "confidence" in payload
        assert "reasoning_length" in payload
        assert "reasoning_mentions_files" in payload
        assert "files_examined" in payload
        assert "severity_assessment" in payload
        assert "forced_escalation" in payload
        assert "reescalation" in payload
        assert "duration_ms" in payload

    def test_no_raw_user_input_in_payload(self):
        """NFR5: triage.completed must NOT contain raw user input text."""
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=500)
        payload_str = json.dumps(payload)
        # Raw incident title and description should NOT appear
        assert "NullReferenceException in OrderController.cs" not in payload_str
        assert "checkout 500 errors" not in payload_str
        assert "Users report" not in payload_str
        # reasoning_summary must NOT exist — replaced with metadata-only fields
        assert "reasoning_summary" not in payload
        assert "reasoning_length" in payload
        assert isinstance(payload["reasoning_length"], int)
        assert "reasoning_mentions_files" in payload
        assert isinstance(payload["reasoning_mentions_files"], bool)

    def test_input_summary_no_raw_text(self):
        """Double-check input_summary has only metadata."""
        mod = _load_generate_output()
        incident = _valid_incident(
            title="Sensitive user report about crash",
            description="My password is hunter2 and the app crashed",
        )
        state = _make_state(incident=incident)
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=500)
        summary_str = json.dumps(payload["input_summary"])
        assert "Sensitive" not in summary_str
        assert "hunter2" not in summary_str
        assert "crashed" not in summary_str
        assert "password" not in summary_str

    def test_confidence_is_float(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=1500)
        assert isinstance(payload["confidence"], float)
        assert 0.0 <= payload["confidence"] <= 1.0

    def test_duration_ms_is_int(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=1500)
        assert isinstance(payload["duration_ms"], int)
        assert payload["duration_ms"] == 1500

    def test_system_integration_source_type(self):
        mod = _load_generate_output()
        incident = _valid_incident(source_type="systemIntegration")
        state = _make_state(incident=incident, source_type="systemIntegration")
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=500)
        assert payload["source_type"] == "systemIntegration"
        assert payload["input_summary"]["source_type"] == "systemIntegration"

    def test_reescalation_flag(self):
        mod = _load_generate_output()
        state = _make_state(reescalation=True)
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=500)
        assert payload["reescalation"] is True

    def test_forced_escalation_flag(self):
        mod = _load_generate_output()
        state = _make_state(forced_escalation=True)
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=500)
        assert payload["forced_escalation"] is True


# ============================================================================
# Pipeline stage logging tests
# ============================================================================

class TestPipelineStageLogging:
    """Verify each pipeline stage produces structured JSON log entries."""

    def test_api_json_formatter_outputs_valid_json(self):
        mod = _load_json_logging("api")
        formatter = mod.StructuredJsonFormatter()
        record = logging.LogRecord(
            name="api_test", level=logging.INFO, pathname="",
            lineno=0, msg="Incident received incident_id=inc-1", args=(), exc_info=None,
        )
        output = formatter.format(record)
        entry = json.loads(output)
        assert entry["service"] == "api"
        assert "Incident received" in entry["message"]

    def test_agent_json_formatter_outputs_valid_json(self):
        mod = _load_json_logging("agent")
        formatter = mod.StructuredJsonFormatter()
        record = logging.LogRecord(
            name="agent_test", level=logging.INFO, pathname="",
            lineno=0, msg="Triage started for incident inc-1", args=(), exc_info=None,
        )
        output = formatter.format(record)
        entry = json.loads(output)
        assert entry["service"] == "agent"
        assert "Triage started" in entry["message"]

    def test_ticket_service_json_formatter_outputs_valid_json(self):
        mod = _load_json_logging("ticket-service")
        formatter = mod.StructuredJsonFormatter()
        record = logging.LogRecord(
            name="ts_test", level=logging.INFO, pathname="",
            lineno=0, msg="Ticket command consumed event_id=evt-1", args=(), exc_info=None,
        )
        output = formatter.format(record)
        entry = json.loads(output)
        assert entry["service"] == "ticket-service"
        assert "command consumed" in entry["message"]

    def test_notification_worker_json_formatter_outputs_valid_json(self):
        mod = _load_json_logging("notification-worker")
        formatter = mod.StructuredJsonFormatter()
        record = logging.LogRecord(
            name="nw_test", level=logging.INFO, pathname="",
            lineno=0, msg="Notification consumed event_id=evt-1", args=(), exc_info=None,
        )
        output = formatter.format(record)
        entry = json.loads(output)
        assert entry["service"] == "notification-worker"
        assert "Notification consumed" in entry["message"]

    def test_all_services_share_same_schema(self):
        """All services must produce logs with the same field set."""
        services = ["api", "agent", "ticket-service", "notification-worker"]
        entries = []
        for svc in services:
            mod = _load_json_logging(svc)
            formatter = mod.StructuredJsonFormatter()
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="",
                lineno=0, msg="test", args=(), exc_info=None,
            )
            output = formatter.format(record)
            entries.append(json.loads(output))

        # All entries should have the same keys
        expected_keys = {"timestamp", "level", "service", "event_id", "message"}
        for entry in entries:
            assert set(entry.keys()) == expected_keys


# ============================================================================
# search_code NFR5 compliance
# ============================================================================

class TestSearchCodeLogSanitization:
    """Verify search_code tool does not log raw query text (NFR5)."""

    def test_search_code_logs_length_not_query(self):
        """search_code should log query_length, not the raw query string."""
        mod = _load_module(
            "agent_search_code_61",
            "services/agent/src/graph/tools/search_code.py",
        )
        import inspect
        source = inspect.getsource(mod.search_code)
        # Should NOT contain a log that dumps the raw query
        assert 'query: %s' not in source
        assert 'query=%s' not in source
        # Should contain the sanitized version
        assert 'query_length' in source


# ============================================================================
# GenerateOutputNode integration (triage.completed publishes enhanced payload)
# ============================================================================

class TestGenerateOutputNodeTriageCompleted:
    """Verify GenerateOutputNode publishes triage.completed with all Story 6.1 fields."""

    @pytest.mark.asyncio
    async def test_bug_path_publishes_triage_completed_with_input_summary(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        state.triage_result = result

        publisher = AsyncMock()
        publisher.publish = AsyncMock(return_value="evt-pub")
        ctx = MagicMock()
        ctx.state = state
        ctx.deps = MagicMock()
        ctx.deps.publisher = publisher

        node = mod.GenerateOutputNode()
        await node.run(ctx)

        # Find the triage.completed publish call
        triage_completed_call = None
        for call in publisher.publish.call_args_list:
            args = call[0]
            if len(args) >= 2 and args[1] == "triage.completed":
                triage_completed_call = call
                break

        assert triage_completed_call is not None, "triage.completed event was not published"
        payload = triage_completed_call[0][2]
        assert "input_summary" in payload
        assert "files_examined" in payload
        assert isinstance(payload["input_summary"], dict)
        assert payload["input_summary"]["title_length"] > 0

    @pytest.mark.asyncio
    async def test_non_incident_path_publishes_triage_completed_with_input_summary(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result()
        state.triage_result = result

        publisher = AsyncMock()
        publisher.publish = AsyncMock(return_value="evt-pub")
        ctx = MagicMock()
        ctx.state = state
        ctx.deps = MagicMock()
        ctx.deps.publisher = publisher

        node = mod.GenerateOutputNode()
        await node.run(ctx)

        triage_completed_call = None
        for call in publisher.publish.call_args_list:
            args = call[0]
            if len(args) >= 2 and args[1] == "triage.completed":
                triage_completed_call = call
                break

        assert triage_completed_call is not None
        payload = triage_completed_call[0][2]
        assert "input_summary" in payload
        assert "files_examined" in payload
        assert payload["files_examined"] == []  # non-incident typically has no file refs
