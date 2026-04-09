import asyncio
import logging
import time

from src.adapters.inbound.redis_consumer import RedisConsumer
from src.adapters.outbound.github_client import GitHubClient
from src.adapters.outbound.redis_publisher import RedisPublisher
from src.domain.models import TriageDeps, TriageState
from src.domain.triage_handler import handle_incident_event, handle_reescalation_event
from src.graph.nodes.analyze_input import AnalyzeInputNode
from src.graph.workflow import triage_graph
from src.json_logging import setup_logging
from src.tracing import record_triage_metadata, setup_tracing, shutdown_tracing, trace_triage_pipeline

setup_logging()
logger = logging.getLogger(__name__)


async def run_pipeline(state: TriageState, deps: TriageDeps) -> None:
    """Run the triage graph pipeline for an incident."""
    logger.info("Triage pipeline started for incident %s (event_id=%s)", state.incident_id, state.event_id)
    with trace_triage_pipeline(state.incident_id) as span:
        try:
            result = await triage_graph.run(AnalyzeInputNode(), state=state, deps=deps)
            logger.info(
                "Triage pipeline completed for incident %s: classification=%s (event_id=%s)",
                state.incident_id,
                result.output.classification.value if result.output else "none",
                state.event_id,
            )
            
            if result.output and state.triage_started_at is not None:
                duration_ms = int((time.monotonic() - state.triage_started_at) * 1000)
                classification = result.output.classification.value if hasattr(result.output.classification, "value") else str(result.output.classification)
                record_triage_metadata(
                    span,
                    incident_id=state.incident_id,
                    classification=classification,
                    confidence=result.output.confidence,
                    severity_assessment=result.output.severity_assessment,
                    source_type=state.source_type,
                    reescalation=state.reescalation,
                    forced_escalation=state.forced_escalation,
                    duration_ms=duration_ms,
                )
            elif span is not None:
                span.set_attribute("status", "no_output")
                logger.warning("Triage pipeline produced no output for incident %s (event_id=%s)", state.incident_id, state.event_id)
        except Exception:
            if span is not None:
                span.set_attribute("status", "error")
            logger.exception("Triage pipeline failed for incident %s (event_id=%s)", state.incident_id, state.event_id)
            try:
                await deps.publisher.publish(
                    "errors",
                    "ticket.error",
                    {
                        "event_id": state.event_id,
                        "incident_id": state.incident_id,
                        "error": "Triage pipeline crashed",
                        "source_channel": "agent",
                    },
                )
            except Exception:
                logger.exception("Failed to publish pipeline error for event_id=%s", state.event_id)


async def main():
    logger.info("Service agent started")

    setup_tracing()

    publisher = RedisPublisher()
    consumer = RedisConsumer()
    github_client = GitHubClient()
    deps = TriageDeps(github_client=github_client, publisher=publisher)

    async def pipeline(state: TriageState) -> None:
        await run_pipeline(state, deps)

    async def on_incident(envelope: dict) -> None:
        await handle_incident_event(envelope, publisher, pipeline)

    async def on_reescalation(envelope: dict) -> None:
        await handle_reescalation_event(envelope, publisher, pipeline)

    try:
        await consumer.subscribe_multi(
            {
                "incidents": on_incident,
                "reescalations": on_reescalation,
            },
            error_publisher=publisher,
        )
    finally:
        try:
            await consumer.close()
        finally:
            try:
                await github_client.close()
            finally:
                try:
                    await publisher.close()
                finally:
                    shutdown_tracing()


if __name__ == "__main__":
    asyncio.run(main())
