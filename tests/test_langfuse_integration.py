"""
Tests for Langfuse Integration (Story 6.2).

Covers:
- Tracing setup with valid Langfuse credentials
- Tracing skipped when credentials are missing
- Graceful degradation when OTEL exporter fails
- Idempotent setup (double-call guard)
- Whitespace-only credential rejection
- LANGFUSE_HOST validation (empty / trailing slash)
- Metadata recording when tracer is available
- Metadata recording no-op when span is None
- severity_assessment truncation
- Provider shutdown
- run_pipeline records triage metadata after completing

Run:
    pytest tests/test_langfuse_integration.py -v
"""

import importlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _add_service_to_path(service: str):
    svc_path = str(_PROJECT_ROOT / "services" / service)
    if svc_path not in sys.path:
        sys.path.insert(0, svc_path)


_add_service_to_path("agent")


def _load_tracing():
    mod_name = "agent_tracing_62"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    file_path = _PROJECT_ROOT / "services" / "agent" / "src" / "tracing.py"
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_main():
    mod_name = "agent_main_62"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    file_path = _PROJECT_ROOT / "services" / "agent" / "src" / "main.py"
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# -----------------------------------------------------------------------
# setup_tracing
# -----------------------------------------------------------------------

class TestSetupTracing:
    """Tests for setup_tracing() initialization."""

    def test_skips_when_public_key_missing(self):
        """Tracing disabled when LANGFUSE_PUBLIC_KEY is empty."""
        tracing = _load_tracing()
        with patch.object(tracing, "LANGFUSE_PUBLIC_KEY", ""), \
             patch.object(tracing, "LANGFUSE_SECRET_KEY", "sk-test"):
            tracing._tracer = None
            tracing.setup_tracing()
            assert tracing.get_tracer() is None

    def test_skips_when_secret_key_missing(self):
        """Tracing disabled when LANGFUSE_SECRET_KEY is empty."""
        tracing = _load_tracing()
        with patch.object(tracing, "LANGFUSE_PUBLIC_KEY", "pk-test"), \
             patch.object(tracing, "LANGFUSE_SECRET_KEY", ""):
            tracing._tracer = None
            tracing.setup_tracing()
            assert tracing.get_tracer() is None

    def test_skips_when_public_key_whitespace_only(self):
        """Tracing disabled when LANGFUSE_PUBLIC_KEY is whitespace-only."""
        tracing = _load_tracing()
        with patch.object(tracing, "LANGFUSE_PUBLIC_KEY", "  "), \
             patch.object(tracing, "LANGFUSE_SECRET_KEY", "sk-test"):
            tracing._tracer = None
            tracing.setup_tracing()
            assert tracing.get_tracer() is None

    def test_skips_when_host_empty(self):
        """Tracing disabled when LANGFUSE_HOST is empty."""
        tracing = _load_tracing()
        with patch.object(tracing, "LANGFUSE_PUBLIC_KEY", "pk-test"), \
             patch.object(tracing, "LANGFUSE_SECRET_KEY", "sk-test"), \
             patch.object(tracing, "LANGFUSE_HOST", ""):
            tracing._tracer = None
            tracing.setup_tracing()
            assert tracing.get_tracer() is None

    def test_configures_tracer_with_valid_credentials(self):
        """Tracer is set when both keys are provided."""
        tracing = _load_tracing()
        mock_provider = MagicMock()
        mock_tracer = MagicMock()
        mock_provider.get_tracer.return_value = mock_tracer

        with patch.object(tracing, "LANGFUSE_PUBLIC_KEY", "pk-test"), \
             patch.object(tracing, "LANGFUSE_SECRET_KEY", "sk-test"), \
             patch.object(tracing, "LANGFUSE_HOST", "http://langfuse:3000"), \
             patch("agent_tracing_62.OTLPSpanExporter") as mock_exporter_cls, \
             patch("agent_tracing_62.TracerProvider", return_value=mock_provider), \
             patch("agent_tracing_62.BatchSpanProcessor") as mock_processor_cls, \
             patch("agent_tracing_62.otel_trace") as mock_otel_trace, \
             patch("pydantic_ai.Agent.instrument_all") as mock_instrument, \
             patch("agent_tracing_62.atexit"):
            tracing._tracer = None
            tracing.setup_tracing()

            mock_exporter_cls.assert_called_once()
            call_kwargs = mock_exporter_cls.call_args
            assert "/api/public/otel/v1/traces" in call_kwargs.kwargs["endpoint"]
            assert "Authorization" in call_kwargs.kwargs["headers"]

            mock_processor_cls.assert_called_once()
            mock_provider.add_span_processor.assert_called_once()
            mock_otel_trace.set_tracer_provider.assert_called_once_with(mock_provider)
            mock_instrument.assert_called_once()
            assert tracing._tracer is mock_tracer

    def test_strips_trailing_slash_from_host(self):
        """Trailing slash on LANGFUSE_HOST is stripped."""
        tracing = _load_tracing()
        mock_provider = MagicMock()
        mock_provider.get_tracer.return_value = MagicMock()

        with patch.object(tracing, "LANGFUSE_PUBLIC_KEY", "pk-test"), \
             patch.object(tracing, "LANGFUSE_SECRET_KEY", "sk-test"), \
             patch.object(tracing, "LANGFUSE_HOST", "http://langfuse:3000/"), \
             patch("agent_tracing_62.OTLPSpanExporter") as mock_exporter_cls, \
             patch("agent_tracing_62.TracerProvider", return_value=mock_provider), \
             patch("agent_tracing_62.BatchSpanProcessor"), \
             patch("agent_tracing_62.otel_trace"), \
             patch("pydantic_ai.Agent.instrument_all"), \
             patch("agent_tracing_62.atexit"):
            tracing._tracer = None
            tracing.setup_tracing()

            endpoint = mock_exporter_cls.call_args.kwargs["endpoint"]
            assert "//" not in endpoint.replace("http://", "")

    def test_graceful_degradation_on_exporter_error(self):
        """Tracing disabled gracefully when exporter creation fails."""
        tracing = _load_tracing()
        with patch.object(tracing, "LANGFUSE_PUBLIC_KEY", "pk-test"), \
             patch.object(tracing, "LANGFUSE_SECRET_KEY", "sk-test"), \
             patch.object(tracing, "LANGFUSE_HOST", "http://langfuse:3000"), \
             patch("agent_tracing_62.OTLPSpanExporter", side_effect=Exception("connection refused")):
            tracing._tracer = None
            tracing.setup_tracing()
            assert tracing.get_tracer() is None

    def test_idempotent_double_call(self):
        """Second call to setup_tracing() is a no-op."""
        tracing = _load_tracing()
        sentinel = MagicMock()
        tracing._tracer = sentinel  # simulate already initialised

        with patch.object(tracing, "LANGFUSE_PUBLIC_KEY", "pk-test"), \
             patch.object(tracing, "LANGFUSE_SECRET_KEY", "sk-test"), \
             patch("agent_tracing_62.OTLPSpanExporter") as mock_exporter_cls:
            tracing.setup_tracing()
            mock_exporter_cls.assert_not_called()
            assert tracing._tracer is sentinel


# -----------------------------------------------------------------------
# _build_auth_header
# -----------------------------------------------------------------------

class TestBuildAuthHeader:
    """Tests for auth header construction."""

    def test_builds_basic_auth(self):
        tracing = _load_tracing()
        import base64
        with patch.object(tracing, "LANGFUSE_PUBLIC_KEY", "pk-abc"), \
             patch.object(tracing, "LANGFUSE_SECRET_KEY", "sk-xyz"):
            header = tracing._build_auth_header()
            assert header.startswith("Basic ")
            decoded = base64.b64decode(header.split(" ")[1]).decode()
            assert decoded == "pk-abc:sk-xyz"


# -----------------------------------------------------------------------
# shutdown_tracing
# -----------------------------------------------------------------------

class TestShutdownTracing:
    """Tests for shutdown_tracing()."""

    def test_flushes_and_shuts_down_provider(self):
        tracing = _load_tracing()
        mock_provider = MagicMock()
        tracing._provider = mock_provider

        tracing.shutdown_tracing()

        mock_provider.force_flush.assert_called_once()
        mock_provider.shutdown.assert_called_once()
        assert tracing._provider is None

    def test_noop_when_no_provider(self):
        tracing = _load_tracing()
        tracing._provider = None
        tracing.shutdown_tracing()  # should not raise


# -----------------------------------------------------------------------
# record_triage_metadata
# -----------------------------------------------------------------------

class TestRecordTriageMetadata:
    """Tests for record_triage_metadata()."""

    def test_noop_when_span_is_none(self):
        """No error when span is None (tracing disabled)."""
        tracing = _load_tracing()
        # Should not raise
        tracing.record_triage_metadata(
            None,
            incident_id="inc-001",
            classification="bug",
            confidence=0.9,
            severity_assessment="P2 - High",
            source_type="userIntegration",
            reescalation=False,
            forced_escalation=False,
            duration_ms=1234,
        )

    def test_records_span_with_attributes(self):
        """Metadata is recorded as span attributes when span is available."""
        tracing = _load_tracing()
        mock_span = MagicMock()

        tracing.record_triage_metadata(
            mock_span,
            incident_id="inc-002",
            classification="non_incident",
            confidence=0.85,
            severity_assessment="P4 - Low",
            source_type="systemIntegration",
            reescalation=True,
            forced_escalation=True,
            duration_ms=5678,
        )

        calls = {c[0][0]: c[0][1] for c in mock_span.set_attribute.call_args_list}
        assert calls["incident_id"] == "inc-002"
        assert calls["classification"] == "non_incident"
        assert calls["confidence"] == 0.85
        assert calls["severity_assessment"] == "P4 - Low"
        assert calls["source_type"] == "systemIntegration"
        assert calls["reescalation"] is True
        assert calls["forced_escalation"] is True
        assert calls["duration_ms"] == 5678

    def test_truncates_long_severity_assessment(self):
        """severity_assessment is capped at 500 chars."""
        tracing = _load_tracing()
        mock_span = MagicMock()
        long_assessment = "X" * 1000

        tracing.record_triage_metadata(
            mock_span,
            incident_id="inc-trunc",
            classification="bug",
            confidence=0.5,
            severity_assessment=long_assessment,
            source_type="userIntegration",
            reescalation=False,
            forced_escalation=False,
            duration_ms=100,
        )

        calls = {c[0][0]: c[0][1] for c in mock_span.set_attribute.call_args_list}
        assert len(calls["severity_assessment"]) == 500

    def test_graceful_degradation_on_span_error(self):
        """Span recording failure does not raise."""
        tracing = _load_tracing()
        mock_span = MagicMock()
        mock_span.set_attribute.side_effect = Exception("span error")

        # Should not raise
        tracing.record_triage_metadata(
            mock_span,
            incident_id="inc-003",
            classification="bug",
            confidence=0.5,
            severity_assessment="P3",
            source_type="userIntegration",
            reescalation=False,
            forced_escalation=False,
            duration_ms=100,
        )


# -----------------------------------------------------------------------
# trace_triage_pipeline
# -----------------------------------------------------------------------

class TestTraceTriagePipeline:
    """Tests for trace_triage_pipeline context manager."""

    def test_yields_span_when_tracer_available(self):
        tracing = _load_tracing()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span
        tracing._tracer = mock_tracer

        with tracing.trace_triage_pipeline("inc-100") as span:
            assert span is mock_span

    def test_yields_none_when_tracer_disabled(self):
        tracing = _load_tracing()
        tracing._tracer = None

        with tracing.trace_triage_pipeline("inc-100") as span:
            assert span is None


# -----------------------------------------------------------------------
# run_pipeline metadata recording
# -----------------------------------------------------------------------

class TestRunPipelineMetadataRecording:
    """Tests that run_pipeline calls record_triage_metadata."""

    @pytest.mark.asyncio
    async def test_records_metadata_after_successful_pipeline(self):
        """Triage metadata is recorded when pipeline succeeds."""
        mock_result_output = MagicMock()
        mock_result_output.classification.value = "bug"
        mock_result_output.confidence = 0.92
        mock_result_output.severity_assessment = "P2 - High"

        mock_graph_result = MagicMock()
        mock_graph_result.output = mock_result_output

        mock_state = MagicMock()
        mock_state.incident_id = "inc-010"
        mock_state.event_id = "evt-010"
        mock_state.source_type = "userIntegration"
        mock_state.reescalation = False
        mock_state.forced_escalation = False
        mock_state.triage_started_at = 1000.0

        mock_deps = MagicMock()

        mock_span = MagicMock()

        with patch("src.graph.workflow.triage_graph") as mock_graph, \
             patch("src.main.record_triage_metadata") as mock_record, \
             patch("src.main.trace_triage_pipeline") as mock_trace_ctx, \
             patch("time.monotonic", return_value=1002.5):
            mock_graph.run = AsyncMock(return_value=mock_graph_result)
            mock_trace_ctx.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_trace_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from src.main import run_pipeline
            await run_pipeline(mock_state, mock_deps)

            mock_record.assert_called_once()
            args = mock_record.call_args
            assert args[0][0] is mock_span  # first positional arg is the span
            kwargs = args.kwargs
            assert kwargs["incident_id"] == "inc-010"
            assert kwargs["classification"] == "bug"
            assert kwargs["confidence"] == 0.92
            assert kwargs["severity_assessment"] == "P2 - High"
            assert kwargs["source_type"] == "userIntegration"
            assert kwargs["reescalation"] is False
            assert kwargs["forced_escalation"] is False
            assert kwargs["duration_ms"] == 2500

    @pytest.mark.asyncio
    async def test_no_metadata_when_pipeline_fails(self):
        """No metadata recorded when pipeline raises."""
        mock_state = MagicMock()
        mock_state.incident_id = "inc-011"
        mock_state.event_id = "evt-011"

        mock_deps = MagicMock()
        mock_deps.publisher = MagicMock()
        mock_deps.publisher.publish = AsyncMock()

        with patch("src.main.triage_graph") as mock_graph, \
             patch("src.main.record_triage_metadata") as mock_record, \
             patch("src.main.trace_triage_pipeline") as mock_trace_ctx:
            mock_graph.run = AsyncMock(side_effect=Exception("boom"))
            mock_trace_ctx.return_value.__enter__ = MagicMock(return_value=None)
            mock_trace_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from src.main import run_pipeline
            await run_pipeline(mock_state, mock_deps)

            mock_record.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_metadata_when_output_is_none(self):
        """No metadata recorded when triage produces no output."""
        mock_graph_result = MagicMock()
        mock_graph_result.output = None

        mock_state = MagicMock()
        mock_state.incident_id = "inc-012"
        mock_state.event_id = "evt-012"
        mock_state.triage_started_at = 1000.0

        mock_deps = MagicMock()

        with patch("src.main.triage_graph") as mock_graph, \
             patch("src.main.record_triage_metadata") as mock_record, \
             patch("src.main.trace_triage_pipeline") as mock_trace_ctx:
            mock_graph.run = AsyncMock(return_value=mock_graph_result)
            mock_trace_ctx.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_trace_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from src.main import run_pipeline
            await run_pipeline(mock_state, mock_deps)

            mock_record.assert_not_called()
