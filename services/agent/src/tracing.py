"""Langfuse tracing via OpenTelemetry for the Agent service.

Instruments all Pydantic AI agents with OTEL spans exported to Langfuse's
OTEL endpoint.  If Langfuse is unavailable or misconfigured, tracing is
silently disabled and triage continues without interruption.
"""

import atexit
import base64
import logging
from contextlib import contextmanager
from typing import Optional

from opentelemetry import trace as otel_trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.config import LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY

logger = logging.getLogger(__name__)

_tracer: Optional[otel_trace.Tracer] = None
_provider: Optional[TracerProvider] = None


def _build_auth_header() -> str:
    """Build Basic-auth header value from Langfuse credentials."""
    return f"Basic {base64.b64encode(f'{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}'.encode()).decode()}"


def setup_tracing() -> None:
    """Configure OpenTelemetry to export Pydantic AI traces to Langfuse.

    Fails silently when Langfuse credentials are missing or the OTEL
    exporter cannot be created — triage must never fail because of tracing.
    """
    global _tracer, _provider

    if _tracer is not None:
        return  # already initialised

    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_PUBLIC_KEY.strip() \
       or not LANGFUSE_SECRET_KEY or not LANGFUSE_SECRET_KEY.strip():
        logger.warning("Langfuse credentials not configured — tracing disabled")
        return

    host = LANGFUSE_HOST.rstrip("/") if LANGFUSE_HOST else ""
    if not host:
        logger.warning("LANGFUSE_HOST not configured — tracing disabled")
        return

    try:
        endpoint = f"{host}/api/public/otel/v1/traces"
        auth_header = _build_auth_header()

        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers={"Authorization": auth_header},
            timeout=30,
        )
        provider = TracerProvider(
            resource=Resource({"service.name": "mila-agent"}),
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        
        from pydantic_ai import Agent
        Agent.instrument_all()
        
        otel_trace.set_tracer_provider(provider)
        _provider = provider
        _tracer = provider.get_tracer("mila-agent")

        atexit.register(shutdown_tracing)

        logger.info("Langfuse tracing enabled (endpoint=%s)", endpoint)
    except Exception:
        logger.warning("Failed to initialise Langfuse tracing — continuing without tracing", exc_info=True)
        _tracer = None
        _provider = None


def shutdown_tracing() -> None:
    """Flush and shut down the tracer provider to avoid dropping buffered spans."""
    global _provider
    if _provider is not None:
        try:
            _provider.force_flush()
            _provider.shutdown()
        except Exception:
            logger.warning("Error shutting down tracer provider", exc_info=True)
        finally:
            _provider = None


def get_tracer() -> Optional[otel_trace.Tracer]:
    """Return the configured tracer, or None if tracing is disabled."""
    return _tracer


@contextmanager
def trace_triage_pipeline(incident_id: str):
    """Context manager that wraps the triage pipeline in a parent span.

    Yields the span so metadata can be attached. If tracing is disabled,
    yields None and acts as a no-op.
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span("triage_pipeline") as span:
        span.set_attribute("incident_id", incident_id)
        yield span


def record_triage_metadata(
    span,
    *,
    incident_id: str,
    classification: str,
    confidence: float,
    severity_assessment: str,
    source_type: str,
    reescalation: bool,
    forced_escalation: bool,
    duration_ms: int,
) -> None:
    """Record triage result metadata on the active pipeline span.

    If tracing is disabled (span is None) this is a no-op.
    """
    if span is None:
        return

    try:
        span.set_attribute("incident_id", incident_id)
        span.set_attribute("classification", classification)
        span.set_attribute("confidence", confidence)
        span.set_attribute("severity_assessment", severity_assessment[:500])
        span.set_attribute("source_type", source_type)
        span.set_attribute("reescalation", reescalation)
        span.set_attribute("forced_escalation", forced_escalation)
        span.set_attribute("duration_ms", duration_ms)
    except Exception:
        logger.warning("Failed to record triage metadata span", exc_info=True)
