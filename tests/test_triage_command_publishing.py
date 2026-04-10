"""
Tests for Story 3.4: Triage Command Publishing — Bug Path

Covers:
- _map_severity: severity text to P1-P4 mapping
- _format_ticket_body: markdown body generation with all required sections
- _build_ticket_command: full ticket.create payload structure
- _build_triage_completed_payload: observability event payload (metadata only)
- GenerateOutputNode: bug path publishes ticket.create, all paths publish triage.completed
- Duration tracking: triage_started_at → duration_ms calculation

Run:
    pytest tests/test_triage_command_publishing.py -v
"""

import importlib.util
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _add_service_to_path(service: str):
    svc_path = str(_PROJECT_ROOT / "services" / service)
    if svc_path not in sys.path:
        sys.path.insert(0, svc_path)


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


def _load_models():
    return _load_module("agent_models_34", "services/agent/src/domain/models.py")


def _load_generate_output():
    return _load_module("agent_gen_output_34", "services/agent/src/graph/nodes/generate_output.py")


def _valid_incident(**overrides) -> dict:
    base = {
        "incident_id": "inc-200",
        "title": "NullReferenceException in OrderController.cs",
        "description": "Users report checkout 500 errors on empty cart.",
        "component": "Ordering",
        "severity": "High",
        "attachment_url": "https://example.com/screenshot.png",
        "reporter_email": "reporter99@example.com",
        "source_type": "userIntegration",
    }
    base.update(overrides)
    return base


def _make_state(**overrides):
    m = _load_models()
    incident = overrides.pop("incident", _valid_incident())
    defaults = {
        "incident_id": incident.get("incident_id", "inc-200"),
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
    m = _load_models()
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
    m = _load_models()
    defaults = {
        "classification": m.Classification.non_incident,
        "confidence": 0.92,
        "reasoning": "User error — expected behavior when cart is cleared",
        "resolution_explanation": "This is expected behavior",
        "severity_assessment": "low — no impact",
    }
    defaults.update(overrides)
    return m.TriageResult(**defaults)


def _mock_ctx(state, publisher=None):
    ctx = MagicMock()
    ctx.state = state
    ctx.deps = MagicMock()
    ctx.deps.publisher = publisher or AsyncMock()
    return ctx


# ---------------------------------------------------------------------------
# _map_severity tests
# ---------------------------------------------------------------------------

class TestMapSeverity:
    def test_critical_maps_to_p1(self):
        mod = _load_generate_output()
        assert mod._map_severity("critical — system down") == "P1"

    def test_high_maps_to_p2(self):
        mod = _load_generate_output()
        assert mod._map_severity("high — affects checkout flow") == "P2"

    def test_medium_maps_to_p3(self):
        mod = _load_generate_output()
        assert mod._map_severity("medium — intermittent issue") == "P3"

    def test_low_maps_to_p4(self):
        mod = _load_generate_output()
        assert mod._map_severity("low — cosmetic issue") == "P4"

    def test_unknown_maps_to_p4(self):
        mod = _load_generate_output()
        assert mod._map_severity("unknown — classification failed") == "P4"

    def test_case_insensitive(self):
        mod = _load_generate_output()
        assert mod._map_severity("CRITICAL impact") == "P1"
        assert mod._map_severity("HIGH severity") == "P2"


# ---------------------------------------------------------------------------
# _format_ticket_body tests
# ---------------------------------------------------------------------------

class TestFormatTicketBody:
    def test_contains_all_required_sections(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        assert "## 📍 Affected Files" in body
        assert "## 🔍 Root Cause" in body
        assert "## 🛠️ Suggested Investigation" in body
        assert "## 📋 Original Report" in body
        assert "## 🔗 Tracking" in body
        assert "## 📎 Attachments" in body
        assert "## 🧠 Triage Reasoning" in body
        assert "## 📊 Severity Assessment" in body

    def test_file_refs_rendered(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)
        assert "OrderController.cs" in body
        assert "OrderService.cs" in body

    def test_empty_file_refs(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result(file_refs=[])
        body = mod._format_ticket_body(state, result)
        assert "No specific files identified" in body

    def test_root_cause_included(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)
        assert "NullReferenceException when order items collection is empty" in body

    def test_missing_root_cause_fallback(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result(root_cause=None)
        body = mod._format_ticket_body(state, result)
        assert "Unable to determine root cause" in body

    def test_missing_suggested_fix_fallback(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result(suggested_fix=None)
        body = mod._format_ticket_body(state, result)
        assert "Further investigation required" in body

    def test_original_report_fields(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)
        assert "NullReferenceException in OrderController.cs" in body  # title
        assert "Ordering" in body  # component
        assert "High" in body  # severity

    def test_description_fenced_against_markdown_injection(self):
        mod = _load_generate_output()
        incident = _valid_incident(description="## Injected Heading\nmalicious content")
        state = _make_state(incident=incident)
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)
        # Description should be inside a code fence, not rendered as markdown
        assert "```\n## Injected Heading" in body
        assert body.count("```") >= 2  # opening and closing fence

    def test_tracking_id_included(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)
        assert f"`{state.incident_id}`" in body

    def test_attachment_url_included(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)
        assert "https://example.com/screenshot.png" in body

    def test_multimodal_attachments_fallback(self):
        mod = _load_generate_output()
        incident = _valid_incident(attachment_url=None)
        del incident["attachment_url"]
        state = _make_state(incident=incident)
        state.multimodal_content = [{"filename": "error.log"}, {"filename": "screenshot.png"}]
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)
        assert "error.log" in body
        assert "screenshot.png" in body

    def test_no_attachments(self):
        mod = _load_generate_output()
        incident = _valid_incident(attachment_url=None)
        del incident["attachment_url"]
        state = _make_state(incident=incident)
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)
        assert "_None_" in body

    def test_reasoning_included(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)
        assert "Traced execution path" in body

    def test_severity_in_assessment(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)
        assert "P2" in body

    def test_low_confidence_not_in_ticket_body(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result(confidence=0.45)
        body = mod._format_ticket_body(state, result)
        assert "🔎 Confidence" not in body

    def test_no_low_confidence_when_above_threshold(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result(confidence=0.85)
        body = mod._format_ticket_body(state, result)
        assert "🟡" not in body


# ---------------------------------------------------------------------------
# _build_ticket_command tests
# ---------------------------------------------------------------------------

class TestBuildTicketCommand:
    def test_command_structure(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        cmd = mod._build_ticket_command(state, result)

        assert cmd["action"] == "create_engineering_ticket"
        assert cmd["title"].startswith("[P2]")
        assert "NullReferenceException" in cmd["title"]
        assert cmd["severity"] == "P2"
        assert cmd["incident_id"] == state.incident_id
        assert cmd["reporter_email"] == "reporter99@example.com"
        assert cmd["event_id"] == state.event_id
        assert isinstance(cmd["body"], str)
        assert isinstance(cmd["labels"], list)

    def test_labels_include_required(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        cmd = mod._build_ticket_command(state, result)

        assert "triaged-by-mila" in cmd["labels"]
        assert "Ordering" in cmd["labels"]
        assert "bug" in cmd["labels"]

    def test_labels_without_component(self):
        mod = _load_generate_output()
        incident = _valid_incident(component=None)
        del incident["component"]
        state = _make_state(incident=incident)
        result = _make_bug_result()
        cmd = mod._build_ticket_command(state, result)

        assert "triaged-by-mila" in cmd["labels"]
        assert "bug" in cmd["labels"]

    def test_severity_mapping_in_title(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result(severity_assessment="critical — system down")
        cmd = mod._build_ticket_command(state, result)
        assert cmd["title"].startswith("[P1]")
        assert cmd["severity"] == "P1"


# ---------------------------------------------------------------------------
# _build_triage_completed_payload tests
# ---------------------------------------------------------------------------

class TestBuildTriageCompletedPayload:
    def test_payload_structure_bug(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=1500)

        assert payload["incident_id"] == state.incident_id
        assert payload["source_type"] == "userIntegration"
        assert payload["classification"] == "bug"
        assert payload["confidence"] == 0.87
        assert isinstance(payload["reasoning_length"], int)
        assert payload["reasoning_length"] >= 0
        assert payload["severity_assessment"] == "high — affects checkout flow but only on edge case"
        assert payload["forced_escalation"] is False
        assert payload["reescalation"] is False
        assert payload["event_id"] == state.event_id
        assert payload["duration_ms"] == 1500

    def test_payload_structure_non_incident(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=800)

        assert payload["classification"] == "non_incident"
        assert payload["confidence"] == 0.92

    def test_reescalation_flag_propagated(self):
        mod = _load_generate_output()
        state = _make_state(reescalation=True)
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=1000)
        assert payload["reescalation"] is True

    def test_no_raw_user_input_in_payload(self):
        """NFR5: triage.completed must NOT include raw user input text."""
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=500)

        # Should not contain the incident description or title as raw input
        payload_str = str(payload)
        assert isinstance(payload.get("reasoning_length"), int)  # metadata only — no raw text
        # Verify no raw fields from incident
        assert "title" not in payload or payload.get("title") is None
        assert "description" not in payload

    def test_reasoning_truncated_to_500(self):
        mod = _load_generate_output()
        state = _make_state()
        long_reasoning = "A" * 600
        result = _make_bug_result(reasoning=long_reasoning)
        payload = mod._build_triage_completed_payload(state, result, duration_ms=100)
        assert payload["reasoning_length"] == 600


# ---------------------------------------------------------------------------
# GenerateOutputNode: bug path → ticket.create + triage.completed
# ---------------------------------------------------------------------------

class TestGenerateOutputNodeBugPath:
    @pytest.mark.asyncio
    async def test_publishes_ticket_create_for_bug(self):
        from pydantic_graph import End

        publisher = AsyncMock()
        publisher.publish.return_value = "evt-123"

        state = _make_state()
        result = _make_bug_result()
        state.triage_result = result

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        end_result = await node.run(ctx)

        assert isinstance(end_result, End)
        assert end_result.data.classification.value == "bug"

        # Verify ticket.create was published
        calls = publisher.publish.call_args_list
        ticket_calls = [c for c in calls if c[0][0] == "ticket-commands" and c[0][1] == "ticket.create"]
        assert len(ticket_calls) == 1

        payload = ticket_calls[0][0][2]
        assert payload["action"] == "create_engineering_ticket"
        assert payload["title"].startswith("[P2]")
        assert payload["severity"] == "P2"
        assert payload["incident_id"] == state.incident_id

    @pytest.mark.asyncio
    async def test_publishes_triage_completed_for_bug(self):
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-456"

        state = _make_state()
        state.triage_result = _make_bug_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        completed_calls = [c for c in calls if c[0][0] == "observability" and c[0][1] == "triage.completed"]
        assert len(completed_calls) == 1

        payload = completed_calls[0][0][2]
        assert payload["incident_id"] == state.incident_id
        assert payload["classification"] == "bug"
        assert payload["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_ticket_body_contains_required_sections(self):
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-789"

        state = _make_state()
        state.triage_result = _make_bug_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        ticket_calls = [c for c in calls if c[0][1] == "ticket.create"]
        body = ticket_calls[0][0][2]["body"]

        assert "📍 Affected Files" in body
        assert "🔍 Root Cause" in body
        assert "🛠️ Suggested Investigation" in body
        assert "📋 Original Report" in body
        assert "🔗 Tracking" in body
        assert "📎 Attachments" in body
        assert "🧠 Triage Reasoning" in body
        assert "📊 Severity Assessment" in body


# ---------------------------------------------------------------------------
# GenerateOutputNode: non-incident path → only triage.completed
# ---------------------------------------------------------------------------

class TestGenerateOutputNodeNonIncidentPath:
    @pytest.mark.asyncio
    async def test_does_not_publish_ticket_for_non_incident(self):
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-100"

        state = _make_state()
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        ticket_calls = [c for c in calls if c[0][0] == "ticket-commands"]
        assert len(ticket_calls) == 0

    @pytest.mark.asyncio
    async def test_publishes_triage_completed_for_non_incident(self):
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-101"

        state = _make_state()
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        completed_calls = [c for c in calls if c[0][1] == "triage.completed"]
        assert len(completed_calls) == 1

        payload = completed_calls[0][0][2]
        assert payload["classification"] == "non_incident"


# ---------------------------------------------------------------------------
# GenerateOutputNode: missing triage_result fallback
# ---------------------------------------------------------------------------

class TestGenerateOutputNodeFallback:
    @pytest.mark.asyncio
    async def test_fallback_publishes_triage_completed(self):
        from pydantic_graph import End

        publisher = AsyncMock()
        publisher.publish.return_value = "evt-200"

        state = _make_state()
        state.triage_result = None

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        end_result = await node.run(ctx)

        assert isinstance(end_result, End)
        assert end_result.data.confidence == 0.0

        # Should still publish triage.completed
        calls = publisher.publish.call_args_list
        completed_calls = [c for c in calls if c[0][1] == "triage.completed"]
        assert len(completed_calls) == 1

    @pytest.mark.asyncio
    async def test_fallback_does_not_publish_ticket(self):
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-201"

        state = _make_state()
        state.triage_result = None

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        ticket_calls = [c for c in calls if c[0][0] == "ticket-commands"]
        assert len(ticket_calls) == 0


# ---------------------------------------------------------------------------
# Duration tracking tests
# ---------------------------------------------------------------------------

class TestDurationTracking:
    @pytest.mark.asyncio
    async def test_duration_ms_calculated(self):
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-300"

        state = _make_state()
        state.triage_started_at = time.monotonic() - 2.0  # 2 seconds ago
        state.triage_result = _make_bug_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        completed_calls = [c for c in calls if c[0][1] == "triage.completed"]
        payload = completed_calls[0][0][2]

        # Should be approximately 2000ms (with some tolerance)
        assert payload["duration_ms"] >= 1900
        assert payload["duration_ms"] < 5000

    @pytest.mark.asyncio
    async def test_duration_zero_when_no_start_time(self):
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-301"

        state = _make_state(triage_started_at=None)
        state.triage_result = _make_bug_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        completed_calls = [c for c in calls if c[0][1] == "triage.completed"]
        payload = completed_calls[0][0][2]
        assert payload["duration_ms"] == 0


# ---------------------------------------------------------------------------
# Error resilience: publisher failures don't crash the node
# ---------------------------------------------------------------------------

class TestPublisherErrorResilience:
    @pytest.mark.asyncio
    async def test_ticket_create_failure_doesnt_crash(self):
        from pydantic_graph import End

        publisher = AsyncMock()
        # ticket.create fails, but triage.completed succeeds
        publisher.publish.side_effect = [
            Exception("Redis connection lost"),  # ticket.create
            "evt-ok",  # triage.completed
        ]

        state = _make_state()
        state.triage_result = _make_bug_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        end_result = await node.run(ctx)

        # Should still return the result despite publish failure
        assert isinstance(end_result, End)
        assert end_result.data.classification.value == "bug"

    @pytest.mark.asyncio
    async def test_triage_completed_failure_doesnt_crash(self):
        from pydantic_graph import End

        publisher = AsyncMock()
        # ticket.create succeeds, triage.completed fails
        publisher.publish.side_effect = [
            "evt-ok",  # ticket.create
            Exception("Redis connection lost"),  # triage.completed
        ]

        state = _make_state()
        state.triage_result = _make_bug_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        end_result = await node.run(ctx)

        assert isinstance(end_result, End)
        assert end_result.data.classification.value == "bug"


# ---------------------------------------------------------------------------
# TriageState: triage_started_at field tests
# ---------------------------------------------------------------------------

class TestTriageStateStartedAt:
    def test_default_none(self):
        m = _load_models()
        state = m.TriageState(incident_id="x", source_type="userIntegration")
        assert state.triage_started_at is None

    def test_can_set_monotonic(self):
        m = _load_models()
        now = time.monotonic()
        state = m.TriageState(incident_id="x", source_type="userIntegration", triage_started_at=now)
        assert state.triage_started_at == now


# ===========================================================================
# Story 3.5: Proactive Incident Processing (systemIntegration — Always Escalate)
# ===========================================================================

def _otel_incident(**overrides) -> dict:
    """Build a systemIntegration (OTEL) incident with trace_data."""
    base = {
        "incident_id": "inc-otel-500",
        "title": "High error rate on Ordering.API",
        "description": "OTEL alert: error_rate > 5% for 5 minutes",
        "component": "Ordering",
        "severity": "High",
        "reporter_email": None,
        "source_type": "systemIntegration",
        "trace_data": {
            "service_name": "ordering-api",
            "trace_id": "abc123def456",
            "status_code": "500",
            "error_message": "Connection refused to downstream service",
        },
    }
    base.update(overrides)
    return base


def _make_otel_state(**overrides):
    m = _load_models()
    incident = overrides.pop("incident", _otel_incident())
    defaults = {
        "incident_id": incident.get("incident_id", "inc-otel-500"),
        "source_type": "systemIntegration",
        "event_id": str(uuid.uuid4()),
        "incident": incident,
        "reescalation": False,
        "prompt_injection_detected": False,
        "triage_started_at": time.monotonic(),
    }
    defaults.update(overrides)
    return m.TriageState(**defaults)


# ---------------------------------------------------------------------------
# Task 1: source_type conditional forces classification to bug
# ---------------------------------------------------------------------------

class TestProactiveForcesBugClassification:
    @pytest.mark.asyncio
    async def test_system_integration_forces_bug_even_if_llm_says_non_incident(self):
        """AC: classification is always forced to bug for systemIntegration."""
        from pydantic_graph import End

        publisher = AsyncMock()
        publisher.publish.return_value = "evt-otel-1"

        state = _make_otel_state()
        # LLM classifies as non_incident — but should be overridden
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        end_result = await node.run(ctx)

        assert isinstance(end_result, End)
        assert end_result.data.classification.value == "bug"

    @pytest.mark.asyncio
    async def test_system_integration_sets_forced_escalation_on_state(self):
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-otel-2"

        state = _make_otel_state()
        state.triage_result = _make_non_incident_result()
        assert state.forced_escalation is False  # default

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        assert state.forced_escalation is True

    @pytest.mark.asyncio
    async def test_system_integration_publishes_ticket_create(self):
        """AC: a ticket.create command is published for systemIntegration."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-otel-3"

        state = _make_otel_state()
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        ticket_calls = [c for c in calls if c[0][0] == "ticket-commands" and c[0][1] == "ticket.create"]
        assert len(ticket_calls) == 1

    @pytest.mark.asyncio
    async def test_system_integration_bug_still_publishes_ticket(self):
        """When LLM already classifies as bug, still force-escalate and publish."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-otel-4"

        state = _make_otel_state()
        state.triage_result = _make_bug_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        assert state.forced_escalation is True
        calls = publisher.publish.call_args_list
        ticket_calls = [c for c in calls if c[0][0] == "ticket-commands"]
        assert len(ticket_calls) == 1

    @pytest.mark.asyncio
    async def test_user_integration_not_force_escalated(self):
        """userIntegration incidents should NOT be force-escalated."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-user-1"

        state = _make_state()  # userIntegration
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        assert state.forced_escalation is False
        # non_incident userIntegration should NOT publish ticket.create
        calls = publisher.publish.call_args_list
        ticket_calls = [c for c in calls if c[0][0] == "ticket-commands"]
        assert len(ticket_calls) == 0

    @pytest.mark.asyncio
    async def test_agent_preserves_analysis_fields(self):
        """AC: agent still produces confidence, reasoning, file_refs, root_cause, suggested_fix normally."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-otel-5"

        state = _make_otel_state()
        result = _make_non_incident_result(
            confidence=0.92,
            reasoning="User error — expected behavior",
        )
        state.triage_result = result

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        end_result = await node.run(ctx)

        # Classification forced, but other fields preserved
        assert end_result.data.classification.value == "bug"
        assert end_result.data.confidence == 0.92
        assert end_result.data.reasoning == "User error — expected behavior"


# ---------------------------------------------------------------------------
# Task 2: forced_escalation indicator in ticket body + OTEL metadata
# ---------------------------------------------------------------------------

class TestProactiveTicketBody:
    def test_proactive_banner_in_ticket_body(self):
        """AC: ticket includes proactive detection banner."""
        mod = _load_generate_output()
        state = _make_otel_state()
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        assert "\U0001f916 Proactive Detection" in body
        assert "auto-detected from production telemetry" in body
        assert "not user-reported" in body
        # F1 hybrid: full spec text as heading, em dash included
        assert "\u2014" in body.split("\n")[0] or "\u2014 This incident" in body

    def test_otel_trace_metadata_in_ticket_body(self):
        """AC: OTEL trace metadata (service name, trace ID, status code, error message) displayed."""
        mod = _load_generate_output()
        state = _make_otel_state()
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        assert "\U0001f4e1 OTEL Trace Metadata" in body
        assert "ordering-api" in body
        assert "abc123def456" in body
        assert "500" in body
        assert "Connection refused" in body

    def test_user_integration_no_banner(self):
        """userIntegration tickets should NOT have proactive banner."""
        mod = _load_generate_output()
        state = _make_state()  # userIntegration
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        assert "\U0001f916 Proactive Detection" not in body
        assert "\U0001f4e1 OTEL Trace Metadata" not in body

    def test_otel_missing_trace_data(self):
        """When trace_data is None, banner still shown but no metadata section."""
        mod = _load_generate_output()
        incident = _otel_incident(trace_data=None)
        state = _make_otel_state(incident=incident)
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        assert "\U0001f916 Proactive Detection" in body
        assert "\U0001f4e1 OTEL Trace Metadata" not in body

    def test_otel_partial_trace_data(self):
        """When trace_data has only some fields, only those are shown."""
        mod = _load_generate_output()
        incident = _otel_incident(trace_data={"service_name": "catalog-api"})
        state = _make_otel_state(incident=incident)
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        assert "catalog-api" in body
        assert "Trace ID" not in body
        assert "Status Code" not in body

    def test_proactive_banner_appears_before_affected_files(self):
        """Banner should be the first section in the ticket body."""
        mod = _load_generate_output()
        state = _make_otel_state()
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        banner_pos = body.index("\U0001f916 Proactive Detection")
        files_pos = body.index("\U0001f4cd Affected Files")
        assert banner_pos < files_pos


# ---------------------------------------------------------------------------
# Task 3: forced_escalation in triage.completed event
# ---------------------------------------------------------------------------

class TestProactiveTriageCompletedPayload:
    def test_forced_escalation_true_for_system_integration(self):
        """AC: triage.completed includes forced_escalation: true."""
        mod = _load_generate_output()
        state = _make_otel_state()
        state.forced_escalation = True
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=1000)

        assert payload["forced_escalation"] is True

    def test_source_type_in_triage_completed(self):
        """AC: triage.completed includes source_type: systemIntegration."""
        mod = _load_generate_output()
        state = _make_otel_state()
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=1000)

        assert payload["source_type"] == "systemIntegration"

    def test_forced_escalation_false_for_user_integration(self):
        mod = _load_generate_output()
        state = _make_state()  # userIntegration, forced_escalation defaults False
        result = _make_bug_result()
        payload = mod._build_triage_completed_payload(state, result, duration_ms=1000)

        assert payload["forced_escalation"] is False

    @pytest.mark.asyncio
    async def test_full_pipeline_triage_completed_has_forced_escalation(self):
        """End-to-end: forced_escalation flows through to triage.completed event."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-otel-tc"

        state = _make_otel_state()
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        completed_calls = [c for c in calls if c[0][1] == "triage.completed"]
        assert len(completed_calls) == 1

        payload = completed_calls[0][0][2]
        assert payload["forced_escalation"] is True
        assert payload["source_type"] == "systemIntegration"
        assert payload["classification"] == "bug"


# ---------------------------------------------------------------------------
# Task 4: Skip reporter notification for proactive incidents
# ---------------------------------------------------------------------------

class TestProactiveReporterHandling:
    def test_reporter_email_empty_for_otel(self):
        """AC: reporter_email is null/empty for systemIntegration events."""
        mod = _load_generate_output()
        state = _make_otel_state()
        result = _make_bug_result()
        cmd = mod._build_ticket_command(state, result)

        # reporter_email should be empty (None from incident -> "" via .get default)
        assert cmd["reporter_email"] in ("", None)

    @pytest.mark.asyncio
    async def test_full_pipeline_ticket_has_no_reporter(self):
        """End-to-end: proactive ticket command has no reporter_email."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-otel-rpt"

        state = _make_otel_state()
        state.triage_result = _make_bug_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        ticket_calls = [c for c in calls if c[0][1] == "ticket.create"]
        assert len(ticket_calls) == 1

        payload = ticket_calls[0][0][2]
        assert payload["reporter_email"] in ("", None)


# ---------------------------------------------------------------------------
# TriageState: forced_escalation field tests
# ---------------------------------------------------------------------------

class TestTriageStateForcedEscalation:
    def test_default_false(self):
        m = _load_models()
        state = m.TriageState(incident_id="x", source_type="userIntegration")
        assert state.forced_escalation is False

    def test_can_set_true(self):
        m = _load_models()
        state = m.TriageState(incident_id="x", source_type="systemIntegration", forced_escalation=True)
        assert state.forced_escalation is True


# ---------------------------------------------------------------------------
# Review patch tests: edge cases caught by code review
# ---------------------------------------------------------------------------

class TestReviewPatchEdgeCases:
    """Tests for fixes identified during Story 3.5 code review."""

    def test_trace_data_non_dict_does_not_crash(self):
        """F3: trace_data as string should not crash _format_ticket_body."""
        mod = _load_generate_output()
        incident = _otel_incident(trace_data="not-a-dict")
        state = _make_otel_state(incident=incident)
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        # Banner still shown, but no metadata section
        assert "\U0001f916 Proactive Detection" in body
        assert "\U0001f4e1 OTEL Trace Metadata" not in body

    def test_trace_data_list_does_not_crash(self):
        """F3: trace_data as list should not crash."""
        mod = _load_generate_output()
        incident = _otel_incident(trace_data=["item1", "item2"])
        state = _make_otel_state(incident=incident)
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)
        assert "\U0001f916 Proactive Detection" in body

    def test_status_code_zero_included(self):
        """F4: status_code=0 (falsy int) should still appear in metadata."""
        mod = _load_generate_output()
        incident = _otel_incident(trace_data={"status_code": 0})
        state = _make_otel_state(incident=incident)
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        assert "Status Code" in body
        assert "0" in body

    def test_error_message_triple_backtick_sanitized(self):
        """F2: error_message containing triple backticks should be sanitized."""
        mod = _load_generate_output()
        incident = _otel_incident(
            trace_data={"error_message": "fail ```injection``` attempt"}
        )
        state = _make_otel_state(incident=incident)
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        assert "```injection```" not in body
        assert "'''injection'''" in body

    def test_service_name_markdown_chars_sanitized(self):
        """F2: service_name with markdown chars should be stripped."""
        mod = _load_generate_output()
        incident = _otel_incident(
            trace_data={"service_name": "**malicious_name**"}
        )
        state = _make_otel_state(incident=incident)
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        assert "**malicious" not in body.replace("**Service:**", "")
        assert "maliciousname" in body

    @pytest.mark.asyncio
    async def test_fallback_path_forced_escalation_for_system_integration(self):
        """F5: triage_result=None + systemIntegration should still set forced_escalation."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-fallback-otel"

        state = _make_otel_state()
        state.triage_result = None  # No result from LLM

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        end_result = await node.run(ctx)

        # forced_escalation should be True even on fallback
        assert state.forced_escalation is True
        # Fallback classification should be bug for systemIntegration
        assert end_result.data.classification.value == "bug"
        # triage.completed should have forced_escalation=True
        calls = publisher.publish.call_args_list
        completed_calls = [c for c in calls if c[0][1] == "triage.completed"]
        assert len(completed_calls) == 1
        assert completed_calls[0][0][2]["forced_escalation"] is True

    @pytest.mark.asyncio
    async def test_fallback_path_user_integration_unchanged(self):
        """F5: triage_result=None + userIntegration should remain non_incident."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-fallback-user"

        state = _make_state()  # userIntegration
        state.triage_result = None

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        end_result = await node.run(ctx)

        assert state.forced_escalation is False
        assert end_result.data.classification.value == "non_incident"

    @pytest.mark.asyncio
    async def test_original_classification_logged(self):
        """F6: original LLM classification should be logged before override."""
        import logging
        import io

        publisher = AsyncMock()
        publisher.publish.return_value = "evt-log-check"

        state = _make_otel_state()
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()

        # Capture logs from the module's actual logger
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)
        mod.logger.addHandler(handler)
        orig_level = mod.logger.level
        mod.logger.setLevel(logging.INFO)
        try:
            await node.run(ctx)
            log_output = log_capture.getvalue()
            assert "Forced classification from non_incident to bug" in log_output
        finally:
            mod.logger.removeHandler(handler)
            mod.logger.setLevel(orig_level)


# ===========================================================================
# Story 3.6: Non-Incident Dismissal with Reporter Notification
# ===========================================================================


# ---------------------------------------------------------------------------
# _build_notification_payload tests
# ---------------------------------------------------------------------------

class TestBuildNotificationPayload:
    def test_payload_structure(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result(
            resolution_explanation="This is expected behavior during scheduled cache rebuild.",
        )
        payload = mod._build_notification_payload(state, result)

        assert payload["type"] == "reporter_update"
        assert payload["reporter_email"] == "reporter99@example.com"
        assert payload["message"] == "This is expected behavior during scheduled cache rebuild."
        assert payload["incident_id"] == state.incident_id
        assert payload["allow_reescalation"] is True
        assert payload["event_id"] == state.event_id

    def test_uses_reasoning_when_no_resolution_explanation(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result(resolution_explanation=None)
        payload = mod._build_notification_payload(state, result)

        assert payload["message"] == result.reasoning

    def test_uses_reasoning_when_resolution_explanation_empty(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result(resolution_explanation="")
        payload = mod._build_notification_payload(state, result)

        assert payload["message"] == result.reasoning

    def test_low_confidence_caveat_prepended(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result(
            confidence=0.5,
            resolution_explanation="Looks like expected behavior.",
        )
        payload = mod._build_notification_payload(state, result)

        assert payload["message"].startswith("I'm less certain about this classification.")
        assert "please re-escalate" in payload["message"]
        assert "Looks like expected behavior." in payload["message"]

    def test_no_caveat_when_above_threshold(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result(
            confidence=0.85,
            resolution_explanation="Expected behavior.",
        )
        payload = mod._build_notification_payload(state, result)

        assert not payload["message"].startswith("I'm less certain")
        assert payload["message"] == "Expected behavior."

    def test_no_caveat_when_exactly_at_threshold(self):
        """At exactly the threshold, no caveat should be added."""
        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result(
            confidence=0.75,  # equals default CONFIDENCE_THRESHOLD
            resolution_explanation="Expected behavior.",
        )
        payload = mod._build_notification_payload(state, result)

        assert not payload["message"].startswith("I'm less certain")

    def test_allow_reescalation_always_true(self):
        """allow_reescalation must ALWAYS be true for non-incidents."""
        mod = _load_generate_output()
        state = _make_state()
        for conf in [0.3, 0.5, 0.75, 0.85, 0.99]:
            result = _make_non_incident_result(confidence=conf)
            payload = mod._build_notification_payload(state, result)
            assert payload["allow_reescalation"] is True

    def test_event_id_correlation(self):
        """ER3: event_id must be included for correlation."""
        mod = _load_generate_output()
        state = _make_state(event_id="evt-correlation-123")
        result = _make_non_incident_result()
        payload = mod._build_notification_payload(state, result)

        assert payload["event_id"] == "evt-correlation-123"


# ---------------------------------------------------------------------------
# GenerateOutputNode: non-incident + userIntegration → notification.send
# ---------------------------------------------------------------------------

class TestNonIncidentDismissalPath:
    @pytest.mark.asyncio
    async def test_publishes_notification_for_user_non_incident(self):
        """AC: non-incident + userIntegration → notification.send to notifications channel."""
        from pydantic_graph import End

        publisher = AsyncMock()
        publisher.publish.return_value = "evt-notif-1"

        state = _make_state()  # userIntegration
        state.triage_result = _make_non_incident_result(
            resolution_explanation="Expected behavior during cache rebuild.",
        )

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        end_result = await node.run(ctx)

        assert isinstance(end_result, End)
        assert end_result.data.classification.value == "non_incident"

        # Verify notification.send was published to notifications channel
        calls = publisher.publish.call_args_list
        notif_calls = [c for c in calls if c[0][0] == "notifications" and c[0][1] == "notification.send"]
        assert len(notif_calls) == 1

        payload = notif_calls[0][0][2]
        assert payload["type"] == "reporter_update"
        assert payload["reporter_email"] == "reporter99@example.com"
        assert payload["message"] == "Expected behavior during cache rebuild."
        assert payload["incident_id"] == state.incident_id
        assert payload["allow_reescalation"] is True

    @pytest.mark.asyncio
    async def test_does_not_publish_ticket_for_user_non_incident(self):
        """Non-incident userIntegration should NOT create a ticket."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-notif-2"

        state = _make_state()
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        ticket_calls = [c for c in calls if c[0][0] == "ticket-commands"]
        assert len(ticket_calls) == 0

    @pytest.mark.asyncio
    async def test_publishes_triage_completed_for_non_incident(self):
        """triage.completed is always published, including for non-incidents."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-notif-3"

        state = _make_state()
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        completed_calls = [c for c in calls if c[0][0] == "observability" and c[0][1] == "triage.completed"]
        assert len(completed_calls) == 1

        payload = completed_calls[0][0][2]
        assert payload["classification"] == "non_incident"
        assert payload["incident_id"] == state.incident_id

    @pytest.mark.asyncio
    async def test_notification_published_before_triage_completed(self):
        """AR10: notification.send to notifications channel happens, then triage.completed."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-notif-order"

        state = _make_state()
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        channels = [c[0][0] for c in calls]
        event_types = [c[0][1] for c in calls]

        notif_idx = next(i for i, e in enumerate(event_types) if e == "notification.send")
        completed_idx = next(i for i, e in enumerate(event_types) if e == "triage.completed")
        assert notif_idx < completed_idx

    @pytest.mark.asyncio
    async def test_system_integration_non_incident_still_gets_ticket(self):
        """AC: systemIntegration non-incident is forced to bug (Story 3.5), gets ticket NOT notification."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-sys-notif"

        state = _make_otel_state()
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        end_result = await node.run(ctx)

        # Classification forced to bug by Story 3.5
        assert end_result.data.classification.value == "bug"

        calls = publisher.publish.call_args_list
        # Should have ticket.create, NOT notification.send
        ticket_calls = [c for c in calls if c[0][0] == "ticket-commands"]
        notif_calls = [c for c in calls if c[0][0] == "notifications"]
        assert len(ticket_calls) == 1
        assert len(notif_calls) == 0

    @pytest.mark.asyncio
    async def test_low_confidence_caveat_in_notification(self):
        """AC: low confidence adds caveat to message."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-low-conf"

        state = _make_state()
        state.triage_result = _make_non_incident_result(
            confidence=0.5,
            resolution_explanation="Looks normal.",
        )

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        notif_calls = [c for c in calls if c[0][1] == "notification.send"]
        assert len(notif_calls) == 1

        payload = notif_calls[0][0][2]
        assert "I'm less certain about this classification" in payload["message"]
        assert "please re-escalate" in payload["message"]
        assert "Looks normal." in payload["message"]
        assert payload["allow_reescalation"] is True

    @pytest.mark.asyncio
    async def test_high_confidence_no_caveat_in_notification(self):
        """High confidence non-incident should NOT have caveat."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-high-conf"

        state = _make_state()
        state.triage_result = _make_non_incident_result(
            confidence=0.92,
            resolution_explanation="Expected behavior.",
        )

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        notif_calls = [c for c in calls if c[0][1] == "notification.send"]
        payload = notif_calls[0][0][2]
        assert payload["message"] == "Expected behavior."
        assert "less certain" not in payload["message"]

    @pytest.mark.asyncio
    async def test_notification_includes_incident_id(self):
        """Notification payload must include incident_id."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-conf-val"

        state = _make_state()
        state.triage_result = _make_non_incident_result(confidence=0.88)

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        notif_calls = [c for c in calls if c[0][1] == "notification.send"]
        payload = notif_calls[0][0][2]
        assert payload["incident_id"] == state.incident_id


# ---------------------------------------------------------------------------
# Non-incident notification: error resilience
# ---------------------------------------------------------------------------

class TestNonIncidentNotificationResilience:
    @pytest.mark.asyncio
    async def test_notification_failure_doesnt_crash(self):
        """Publisher failure on notification.send should not crash the pipeline."""
        from pydantic_graph import End

        publisher = AsyncMock()
        # notification.send fails, triage.completed succeeds
        publisher.publish.side_effect = [
            Exception("Redis connection lost"),  # notification.send
            "evt-ok",  # triage.completed
        ]

        state = _make_state()
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        end_result = await node.run(ctx)

        assert isinstance(end_result, End)
        assert end_result.data.classification.value == "non_incident"

    @pytest.mark.asyncio
    async def test_notification_failure_still_publishes_triage_completed(self):
        """Even if notification.send fails, triage.completed should still be published."""
        publisher = AsyncMock()
        publisher.publish.side_effect = [
            Exception("Redis timeout"),  # notification.send
            "evt-completed",  # triage.completed
        ]

        state = _make_state()
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        # Even though notification failed, publisher was called twice
        assert publisher.publish.call_count == 2


# ---------------------------------------------------------------------------
# Non-incident triage.completed payload specifics
# ---------------------------------------------------------------------------

class TestNonIncidentTriageCompleted:
    @pytest.mark.asyncio
    async def test_triage_completed_has_non_incident_classification(self):
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-tc-ni"

        state = _make_state()
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        completed_calls = [c for c in calls if c[0][1] == "triage.completed"]
        payload = completed_calls[0][0][2]

        assert payload["classification"] == "non_incident"
        assert payload["forced_escalation"] is False
        assert payload["source_type"] == "userIntegration"

    @pytest.mark.asyncio
    async def test_triage_completed_duration_tracked(self):
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-tc-dur"

        state = _make_state()
        state.triage_started_at = time.monotonic() - 1.5  # 1.5 seconds ago
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        completed_calls = [c for c in calls if c[0][1] == "triage.completed"]
        payload = completed_calls[0][0][2]

        assert payload["duration_ms"] >= 1400
        assert payload["duration_ms"] < 5000


# ---------------------------------------------------------------------------
# NFR5: metadata-only logging for notifications
# ---------------------------------------------------------------------------

class TestNonIncidentNFR5Compliance:
    @pytest.mark.asyncio
    async def test_notification_logs_metadata_not_raw_text(self):
        """NFR5: logs should contain metadata (confidence, has_explanation) not raw incident text."""
        import io
        import logging

        publisher = AsyncMock()
        publisher.publish.return_value = "evt-nfr5"

        state = _make_state()
        state.triage_result = _make_non_incident_result(
            resolution_explanation="Detailed explanation with sensitive info about user's error",
        )

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)
        mod.logger.addHandler(handler)
        orig_level = mod.logger.level
        mod.logger.setLevel(logging.INFO)
        try:
            await node.run(ctx)
            log_output = log_capture.getvalue()
            # Logs should mention metadata fields, not raw explanation text
            assert "has_explanation=True" in log_output
            assert "confidence=" in log_output
            # Should NOT contain the raw resolution text
            assert "sensitive info about user's error" not in log_output
        finally:
            mod.logger.removeHandler(handler)
            mod.logger.setLevel(orig_level)


# ===========================================================================
# Story 3.6 Review Fixes
# ===========================================================================


# ---------------------------------------------------------------------------
# D2: Fallback path sends notification for userIntegration
# ---------------------------------------------------------------------------

class TestFallbackNotification:
    @pytest.mark.asyncio
    async def test_fallback_user_integration_publishes_notification(self):
        """D2: When LLM fails (triage_result=None) + userIntegration, reporter gets notification."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-fallback-notif"

        state = _make_state()  # userIntegration
        state.triage_result = None

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        notif_calls = [c for c in calls if c[0][0] == "notifications" and c[0][1] == "notification.send"]
        assert len(notif_calls) == 1

        payload = notif_calls[0][0][2]
        assert payload["type"] == "reporter_update"
        assert "couldn't fully analyze" in payload["message"]
        assert payload["allow_reescalation"] is True

    @pytest.mark.asyncio
    async def test_fallback_user_integration_has_generic_message(self):
        """D2: Fallback notification uses the generic classification-failed message."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-fallback-msg"

        state = _make_state()
        state.triage_result = None

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        end_result = await node.run(ctx)

        # Fallback TriageResult should have the generic resolution_explanation
        assert "couldn't fully analyze" in end_result.data.resolution_explanation

    @pytest.mark.asyncio
    async def test_fallback_system_integration_no_notification(self):
        """D2: systemIntegration fallback should NOT publish notification."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-fallback-sys"

        state = _make_otel_state()
        state.triage_result = None

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        notif_calls = [c for c in calls if c[0][0] == "notifications"]
        assert len(notif_calls) == 0

    @pytest.mark.asyncio
    async def test_fallback_notification_before_triage_completed(self):
        """D2: Fallback notification should be published before triage.completed."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-fallback-ord"

        state = _make_state()
        state.triage_result = None

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        event_types = [c[0][1] for c in calls]

        notif_idx = next(i for i, e in enumerate(event_types) if e == "notification.send")
        completed_idx = next(i for i, e in enumerate(event_types) if e == "triage.completed")
        assert notif_idx < completed_idx

    @pytest.mark.asyncio
    async def test_fallback_notification_has_low_confidence_caveat(self):
        """D2: Fallback has confidence=0.0,  below threshold, so caveat should be prepended."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-fallback-caveat"

        state = _make_state()
        state.triage_result = None

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        notif_calls = [c for c in calls if c[0][1] == "notification.send"]
        payload = notif_calls[0][0][2]
        assert payload["message"].startswith("I'm less certain about this classification.")
        assert "couldn't fully analyze" in payload["message"]


# ---------------------------------------------------------------------------
# D3: Reasoning fallback logs warning
# ---------------------------------------------------------------------------

class TestReasoningFallbackWarning:
    def test_logs_warning_when_using_reasoning_fallback(self):
        """D3: When resolution_explanation is missing, a warning should be logged."""
        import io
        import logging

        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result(resolution_explanation=None)

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.WARNING)
        mod.logger.addHandler(handler)
        orig_level = mod.logger.level
        mod.logger.setLevel(logging.WARNING)
        try:
            mod._build_notification_payload(state, result)
            log_output = log_capture.getvalue()
            assert "Missing resolution_explanation" in log_output
            assert "falling back to reasoning" in log_output
        finally:
            mod.logger.removeHandler(handler)
            mod.logger.setLevel(orig_level)

    def test_no_warning_when_resolution_explanation_present(self):
        """D3: No warning when resolution_explanation is present."""
        import io
        import logging

        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result(
            resolution_explanation="This is expected behavior.",
        )

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.WARNING)
        mod.logger.addHandler(handler)
        orig_level = mod.logger.level
        mod.logger.setLevel(logging.WARNING)
        try:
            mod._build_notification_payload(state, result)
            log_output = log_capture.getvalue()
            assert "Missing resolution_explanation" not in log_output
        finally:
            mod.logger.removeHandler(handler)
            mod.logger.setLevel(orig_level)


# ---------------------------------------------------------------------------
# P1: Empty message guard
# ---------------------------------------------------------------------------

class TestEmptyMessageGuard:
    def test_fallback_message_when_both_fields_empty(self):
        """P1: When both resolution_explanation and reasoning are empty, use fallback message."""
        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result(
            resolution_explanation="",
            reasoning="",
            confidence=0.92,
        )
        payload = mod._build_notification_payload(state, result)

        assert "not an incident" in payload["message"]
        assert "re-escalate" in payload["message"]

    def test_fallback_message_when_both_fields_none(self):
        """P1: When both resolution_explanation and reasoning are None."""
        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result(
            resolution_explanation=None,
            confidence=0.92,
        )
        # Force reasoning to empty string
        result.reasoning = ""
        payload = mod._build_notification_payload(state, result)

        assert "not an incident" in payload["message"]
        assert "re-escalate" in payload["message"]

    def test_fallback_message_with_low_confidence_gets_caveat(self):
        """P1: Fallback message + low confidence = caveat prepended to fallback."""
        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result(
            resolution_explanation="",
            reasoning="",
            confidence=0.3,
        )
        payload = mod._build_notification_payload(state, result)

        assert payload["message"].startswith("I'm less certain")
        assert "not an incident" in payload["message"]


# ---------------------------------------------------------------------------
# P2: Explicit source_type guard — unknown source_type
# ---------------------------------------------------------------------------

class TestUnknownSourceTypeGuard:
    @pytest.mark.asyncio
    async def test_unknown_source_type_no_notification(self):
        """P2: Unknown source_type + non-incident should NOT publish notification."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-unk-src"

        m = _load_models()
        state = m.TriageState(
            incident_id="inc-unknown",
            source_type="unknownIntegration",
            event_id="evt-unknown",
            incident={"reporter_email": ""},
            triage_started_at=time.monotonic(),
        )
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        notif_calls = [c for c in calls if c[0][0] == "notifications"]
        assert len(notif_calls) == 0

    @pytest.mark.asyncio
    async def test_unknown_source_type_logs_warning(self):
        """P2: Unknown source_type should produce a warning log."""
        import io
        import logging

        publisher = AsyncMock()
        publisher.publish.return_value = "evt-unk-warn"

        m = _load_models()
        state = m.TriageState(
            incident_id="inc-unknown",
            source_type="unknownIntegration",
            event_id="evt-unknown",
            incident={"reporter_email": ""},
            triage_started_at=time.monotonic(),
        )
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.WARNING)
        mod.logger.addHandler(handler)
        orig_level = mod.logger.level
        mod.logger.setLevel(logging.WARNING)
        try:
            await node.run(ctx)
            log_output = log_capture.getvalue()
            assert "unexpected source_type=unknownIntegration" in log_output
        finally:
            mod.logger.removeHandler(handler)
            mod.logger.setLevel(orig_level)

    @pytest.mark.asyncio
    async def test_unknown_source_type_still_publishes_triage_completed(self):
        """P2: Even unknown source_type should still get triage.completed."""
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-unk-tc"

        m = _load_models()
        state = m.TriageState(
            incident_id="inc-unknown",
            source_type="unknownIntegration",
            event_id="evt-unknown",
            incident={"reporter_email": ""},
            triage_started_at=time.monotonic(),
        )
        state.triage_result = _make_non_incident_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        completed_calls = [c for c in calls if c[0][1] == "triage.completed"]
        assert len(completed_calls) == 1
