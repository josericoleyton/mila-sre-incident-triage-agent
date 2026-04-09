"""
Tests for Story 3.7: Confidence-Based Decision Quality & Severity Analysis

Covers:
- CONFIDENCE_THRESHOLD config from env var with default 0.75
- Low-confidence bug tickets: 🟡 Low Confidence indicator, score, manual review note, uncertainty reasoning
- Low-confidence non-incident notifications: caveat prepended, re-escalation emphasized
- Severity assessment in ticket body: agent severity, reporter input, delta explanation
- Severity assessment with no reporter input: purely code-based, no reporter reference
- System prompt: P1-P4 severity criteria, reporter acknowledgement instructions

Run:
    pytest tests/test_confidence_severity.py -v
"""

import importlib.util
import os
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
    return _load_module("agent_models_37", "services/agent/src/domain/models.py")


def _load_generate_output():
    return _load_module("agent_gen_output_37", "services/agent/src/graph/nodes/generate_output.py")


def _load_prompts():
    return _load_module("agent_prompts_37", "services/agent/src/domain/prompts.py")


def _load_config():
    return _load_module("agent_config_37", "services/agent/src/config.py")


def _valid_incident(**overrides) -> dict:
    base = {
        "incident_id": "inc-370",
        "title": "Checkout timeout on large orders",
        "description": "Users report timeout errors during checkout with 50+ items.",
        "component": "Ordering.API",
        "severity": "High",
        "attachment_url": None,
        "reporter_email": "reporter37@example.com",
        "source_type": "userIntegration",
    }
    base.update(overrides)
    return base


def _make_state(**overrides):
    m = _load_models()
    incident = overrides.pop("incident", _valid_incident())
    defaults = {
        "incident_id": incident.get("incident_id", "inc-370"),
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
        "reasoning": "Found timeout in OrderService.ProcessLargeOrder(). Database query N+1 pattern detected.",
        "file_refs": ["src/Ordering.API/Services/OrderService.cs"],
        "root_cause": "N+1 query pattern when processing large order items",
        "suggested_fix": "Batch database queries for order items instead of per-item queries",
        "severity_assessment": "P2 (High) — checkout flow impacted for large orders, workaround exists by reducing cart size",
    }
    defaults.update(overrides)
    return m.TriageResult(**defaults)


def _make_non_incident_result(**overrides):
    m = _load_models()
    defaults = {
        "classification": m.Classification.non_incident,
        "confidence": 0.92,
        "reasoning": "Expected timeout behavior for uncommonly large carts — known limitation",
        "resolution_explanation": "This is a known limitation for carts with 50+ items.",
        "severity_assessment": "P4 (Low) — cosmetic, known limitation",
    }
    defaults.update(overrides)
    return m.TriageResult(**defaults)


def _mock_ctx(state, publisher=None):
    ctx = MagicMock()
    ctx.state = state
    ctx.deps = MagicMock()
    ctx.deps.publisher = publisher or AsyncMock()
    return ctx


# ===========================================================================
# Task 1: CONFIDENCE_THRESHOLD configuration
# ===========================================================================

class TestConfidenceThresholdConfig:
    def test_default_threshold_is_float(self):
        cfg = _load_config()
        assert isinstance(cfg.CONFIDENCE_THRESHOLD, float)
        assert 0.0 < cfg.CONFIDENCE_THRESHOLD <= 1.0

    def test_threshold_read_from_env(self, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.60")
        # Reload to pick up env
        mod_name = "agent_config_37_env"
        file_path = _PROJECT_ROOT / "services/agent/src/config.py"
        spec = importlib.util.spec_from_file_location(mod_name, file_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.CONFIDENCE_THRESHOLD == 0.60

    def test_default_075_when_no_env(self, monkeypatch):
        monkeypatch.delenv("CONFIDENCE_THRESHOLD", raising=False)
        mod_name = "agent_config_37_default"
        file_path = _PROJECT_ROOT / "services/agent/src/config.py"
        spec = importlib.util.spec_from_file_location(mod_name, file_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.CONFIDENCE_THRESHOLD == 0.75


# ===========================================================================
# Task 2: Low-confidence bug ticket body enhancements
# ===========================================================================

class TestLowConfidenceBugTicket:
    def test_low_confidence_shows_indicator(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result(confidence=0.55)
        body = mod._format_ticket_body(state, result)

        assert "🟡" in body
        assert "Low Confidence" in body

    def test_low_confidence_includes_score_and_manual_review(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result(confidence=0.55)
        body = mod._format_ticket_body(state, result)

        assert "Agent confidence: 0.55" in body
        assert "This classification may need manual review" in body

    def test_low_confidence_includes_uncertainty_reasoning(self):
        mod = _load_generate_output()
        state = _make_state()
        reasoning = "Partial evidence found. Could be timeout or network issue, not clear from code."
        result = _make_bug_result(confidence=0.50, reasoning=reasoning)
        body = mod._format_ticket_body(state, result)

        assert "Uncertainty Reasoning" in body
        # Should reference the reasoning section, not duplicate it
        assert "See Triage Reasoning above" in body

    def test_low_confidence_empty_reasoning_no_uncertainty_line(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result(confidence=0.50, reasoning="")
        body = mod._format_ticket_body(state, result)

        assert "🟡" in body
        assert "Uncertainty Reasoning" not in body

    def test_high_confidence_no_low_indicator(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result(confidence=0.90)
        body = mod._format_ticket_body(state, result)

        assert "🟡" not in body
        assert "Low Confidence" not in body
        assert "may need manual review" not in body

    def test_threshold_boundary_exact(self):
        """Confidence exactly at threshold should NOT show low-confidence indicator."""
        mod = _load_generate_output()
        cfg = _load_config()
        state = _make_state()
        result = _make_bug_result(confidence=cfg.CONFIDENCE_THRESHOLD)
        body = mod._format_ticket_body(state, result)

        assert "🟡" not in body

    def test_threshold_just_below(self):
        """Confidence just below threshold should show low-confidence indicator."""
        mod = _load_generate_output()
        cfg = _load_config()
        state = _make_state()
        result = _make_bug_result(confidence=cfg.CONFIDENCE_THRESHOLD - 0.01)
        body = mod._format_ticket_body(state, result)

        assert "🟡" in body
        assert "Low Confidence" in body


# ===========================================================================
# Task 3: Low-confidence non-incident notification
# ===========================================================================

class TestLowConfidenceNonIncidentNotification:
    def test_low_confidence_prepends_caveat(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result(confidence=0.55)
        payload = mod._build_notification_payload(state, result)

        assert "less certain" in payload["message"].lower()
        assert "re-escalate" in payload["message"].lower()
        assert payload["allow_reescalation"] is True

    def test_high_confidence_no_caveat(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result(confidence=0.92)
        payload = mod._build_notification_payload(state, result)

        assert "less certain" not in payload["message"].lower()

    def test_notification_includes_confidence_value(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result(confidence=0.55)
        payload = mod._build_notification_payload(state, result)

        assert payload["confidence"] == 0.55

    def test_notification_allows_reescalation(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_non_incident_result(confidence=0.50)
        payload = mod._build_notification_payload(state, result)

        assert payload["allow_reescalation"] is True


# ===========================================================================
# Task 4: System prompt severity assessment instructions
# ===========================================================================

class TestSystemPromptSeverity:
    def test_prompt_contains_p1_p4_criteria(self):
        mod = _load_prompts()
        prompt = mod.TRIAGE_SYSTEM_PROMPT

        assert "P1" in prompt
        assert "P2" in prompt
        assert "P3" in prompt
        assert "P4" in prompt
        assert "Critical" in prompt
        assert "data loss" in prompt.lower()

    def test_prompt_instructs_reporter_severity_acknowledgement(self):
        mod = _load_prompts()
        prompt = mod.TRIAGE_SYSTEM_PROMPT

        assert "reporter" in prompt.lower()
        assert "Reporter indicated" in prompt

    def test_prompt_instructs_delta_explanation(self):
        mod = _load_prompts()
        prompt = mod.TRIAGE_SYSTEM_PROMPT

        assert "delta" in prompt.lower() or "differ" in prompt.lower() or "difference" in prompt.lower()

    def test_prompt_instructs_code_only_when_no_reporter_severity(self):
        mod = _load_prompts()
        prompt = mod.TRIAGE_SYSTEM_PROMPT

        assert "no reporter severity" in prompt.lower() or "no reference to reporter" in prompt.lower()

    def test_prompt_retains_security_guardrails(self):
        mod = _load_prompts()
        prompt = mod.TRIAGE_SYSTEM_PROMPT

        assert "UNTRUSTED USER INPUT" in prompt
        assert "adversarial" in prompt.lower()


# ===========================================================================
# Task 5: Severity assessment formatting in ticket body
# ===========================================================================

class TestSeverityAssessmentInTicket:
    def test_agent_severity_shown(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        assert "Agent Severity" in body
        assert "P2" in body

    def test_reporter_severity_acknowledged(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        assert "Reporter Indicated" in body
        assert "High" in body

    def test_delta_explanation_when_different(self):
        mod = _load_generate_output()
        # Reporter says "Critical" (P1) but agent assesses P3 (medium) — structured P-level mismatch
        incident = _valid_incident(severity="Critical")
        state = _make_state(incident=incident)
        result = _make_bug_result(severity_assessment="P3 (Medium) — limited impact, workaround exists")
        body = mod._format_ticket_body(state, result)

        assert "Delta" in body
        assert "Critical" in body
        assert "P1" in body  # reporter mapped to P1

    def test_delta_detects_mismatch_even_when_word_appears_in_prose(self):
        """Structured P-level comparison catches delta even when reporter's word appears in assessment text."""
        mod = _load_generate_output()
        # Reporter says "High" (P2) but agent assesses P3 with 'high' appearing in prose
        incident = _valid_incident(severity="High")
        state = _make_state(incident=incident)
        result = _make_bug_result(
            severity_assessment="P3 (Medium) — high error volume observed but scope is limited"
        )
        body = mod._format_ticket_body(state, result)

        # With structured comparison, P2 != P3 so delta MUST appear
        assert "Delta" in body

    def test_no_reporter_severity_shows_code_only(self):
        mod = _load_generate_output()
        incident = _valid_incident(severity=None)
        del incident["severity"]
        state = _make_state(incident=incident)
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        assert "Reporter Indicated" not in body
        assert "purely from code analysis" in body.lower() or "no reporter severity" in body.lower()

    def test_severity_section_header(self):
        mod = _load_generate_output()
        state = _make_state()
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        assert "## 📊 Severity Assessment" in body

    def test_reporter_severity_matching_no_delta(self):
        """When reporter severity maps to same P-level as agent, no delta."""
        mod = _load_generate_output()
        # Reporter says "High" (P2) and agent assesses P2
        incident = _valid_incident(severity="High")
        state = _make_state(incident=incident)
        result = _make_bug_result(
            severity_assessment="P2 (High) — checkout flow impacted, High severity confirmed"
        )
        body = mod._format_ticket_body(state, result)

        assert "Reporter Indicated" in body
        assert "Delta" not in body

    def test_reporter_severity_sanitized(self):
        """Markdown injection in reporter severity is stripped."""
        mod = _load_generate_output()
        incident = _valid_incident(severity="**Critical**\n## INJECTED")
        state = _make_state(incident=incident)
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        assert "## INJECTED" not in body
        assert "**Critical**" not in body  # asterisks stripped
        assert "Reporter Indicated" in body

    def test_whitespace_only_severity_treated_as_absent(self):
        """Whitespace-only severity should be treated the same as None."""
        mod = _load_generate_output()
        incident = _valid_incident(severity="   ")
        state = _make_state(incident=incident)
        result = _make_bug_result()
        body = mod._format_ticket_body(state, result)

        assert "Reporter Indicated" not in body
        assert "No reporter severity" in body or "purely from code analysis" in body.lower()


# ===========================================================================
# Integration: GenerateOutputNode with confidence & severity
# ===========================================================================

class TestGenerateOutputNodeConfidenceSeverity:
    @pytest.mark.asyncio
    async def test_low_confidence_bug_ticket_includes_indicator(self):
        from pydantic_graph import End

        publisher = AsyncMock()
        publisher.publish.return_value = "evt-370"

        state = _make_state()
        state.triage_result = _make_bug_result(confidence=0.50)

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        end_result = await node.run(ctx)

        assert isinstance(end_result, End)

        calls = publisher.publish.call_args_list
        ticket_calls = [c for c in calls if c[0][0] == "ticket-commands"]
        assert len(ticket_calls) == 1

        body = ticket_calls[0][0][2]["body"]
        assert "🟡" in body
        assert "Low Confidence" in body
        assert "0.50" in body

    @pytest.mark.asyncio
    async def test_high_confidence_bug_ticket_no_indicator(self):
        from pydantic_graph import End

        publisher = AsyncMock()
        publisher.publish.return_value = "evt-371"

        state = _make_state()
        state.triage_result = _make_bug_result(confidence=0.95)

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        ticket_calls = [c for c in calls if c[0][0] == "ticket-commands"]
        body = ticket_calls[0][0][2]["body"]
        assert "🟡" not in body

    @pytest.mark.asyncio
    async def test_low_confidence_non_incident_notification_has_caveat(self):
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-372"

        state = _make_state()
        state.triage_result = _make_non_incident_result(confidence=0.55)

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        notification_calls = [c for c in calls if c[0][0] == "notifications"]
        assert len(notification_calls) == 1

        payload = notification_calls[0][0][2]
        assert "less certain" in payload["message"].lower()
        assert payload["allow_reescalation"] is True

    @pytest.mark.asyncio
    async def test_severity_assessment_in_ticket_body(self):
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-373"

        state = _make_state()
        state.triage_result = _make_bug_result()

        ctx = _mock_ctx(state, publisher)
        mod = _load_generate_output()
        node = mod.GenerateOutputNode()
        await node.run(ctx)

        calls = publisher.publish.call_args_list
        ticket_calls = [c for c in calls if c[0][0] == "ticket-commands"]
        body = ticket_calls[0][0][2]["body"]

        assert "Agent Severity" in body
        assert "Reporter Indicated" in body


# ===========================================================================
# Review fixes: _map_severity, _map_reporter_severity, bounds, sanitization
# ===========================================================================

class TestMapSeverityEdgeCases:
    def test_empty_severity_returns_p4(self):
        mod = _load_generate_output()
        assert mod._map_severity("") == "P4"

    def test_whitespace_severity_returns_p4(self):
        mod = _load_generate_output()
        assert mod._map_severity("   ") == "P4"


class TestMapReporterSeverity:
    def test_high_maps_to_p2(self):
        mod = _load_generate_output()
        assert mod._map_reporter_severity("High") == "P2"

    def test_critical_maps_to_p1(self):
        mod = _load_generate_output()
        assert mod._map_reporter_severity("Critical") == "P1"

    def test_medium_maps_to_p3(self):
        mod = _load_generate_output()
        assert mod._map_reporter_severity("Medium") == "P3"

    def test_low_maps_to_p4(self):
        mod = _load_generate_output()
        assert mod._map_reporter_severity("Low") == "P4"

    def test_p_labels_map_directly(self):
        mod = _load_generate_output()
        assert mod._map_reporter_severity("P1") == "P1"
        assert mod._map_reporter_severity("P2") == "P2"
        assert mod._map_reporter_severity("P3") == "P3"
        assert mod._map_reporter_severity("P4") == "P4"

    def test_empty_string_returns_p4(self):
        mod = _load_generate_output()
        assert mod._map_reporter_severity("") == "P4"

    def test_whitespace_returns_p4(self):
        mod = _load_generate_output()
        assert mod._map_reporter_severity("   ") == "P4"

    def test_urgent_maps_to_p1(self):
        mod = _load_generate_output()
        assert mod._map_reporter_severity("Urgent") == "P1"

    def test_unknown_freetext_maps_to_p4(self):
        mod = _load_generate_output()
        assert mod._map_reporter_severity("something random") == "P4"


class TestSanitizeMarkdown:
    def test_strips_asterisks_and_backticks(self):
        mod = _load_generate_output()
        assert mod._sanitize_markdown("**bold** `code`") == "bold code"

    def test_strips_headings_and_newlines(self):
        mod = _load_generate_output()
        result = mod._sanitize_markdown("## heading\nline2")
        assert "#" not in result
        assert "\n" not in result


class TestConfidenceThresholdBounds:
    def test_above_1_clamped(self, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_THRESHOLD", "1.5")
        mod_name = "agent_config_37_clamp_high"
        file_path = _PROJECT_ROOT / "services/agent/src/config.py"
        spec = importlib.util.spec_from_file_location(mod_name, file_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.CONFIDENCE_THRESHOLD == 1.0

    def test_negative_clamped(self, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_THRESHOLD", "-0.5")
        mod_name = "agent_config_37_clamp_low"
        file_path = _PROJECT_ROOT / "services/agent/src/config.py"
        spec = importlib.util.spec_from_file_location(mod_name, file_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.CONFIDENCE_THRESHOLD == 0.0
