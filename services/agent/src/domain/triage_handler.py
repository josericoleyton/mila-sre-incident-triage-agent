import logging
import time
from typing import Awaitable, Callable, Optional

from pydantic import ValidationError

from src.domain.models import IncidentEvent, TriageState
from src.ports.outbound import EventPublisher

logger = logging.getLogger(__name__)


async def _publish_error(publisher: EventPublisher, event_id: str, error: str, source_channel: str) -> None:
    try:
        await publisher.publish(
            "errors",
            "ticket.error",
            {"event_id": event_id, "error": error, "source_channel": source_channel},
        )
    except Exception:
        logger.exception("Failed to publish ticket.error for event_id=%s", event_id)


async def handle_incident_event(
    envelope: dict,
    publisher: EventPublisher,
    run_pipeline: Callable[[TriageState], Awaitable[None]],
) -> Optional[TriageState]:
    """Handle an incident.created event from the incidents channel."""
    event_id = envelope.get("event_id", "unknown")

    try:
        incident = IncidentEvent.model_validate(envelope["payload"])
    except (ValidationError, KeyError) as exc:
        logger.warning(
            "Deserialization failed for event_id=%s: %s", event_id, exc
        )
        await _publish_error(publisher, event_id, str(exc), "incidents")
        return None

    state = TriageState(
        incident_id=incident.incident_id,
        source_type=incident.source_type,
        event_id=event_id,
        incident=incident.model_dump(),
        reescalation=False,
        prompt_injection_detected=incident.prompt_injection_detected,
        triage_started_at=time.monotonic(),
    )

    logger.info(
        "Triage started for incident %s, source: %s (event_id=%s)",
        state.incident_id,
        state.source_type,
        event_id,
    )

    await run_pipeline(state)
    return state


async def handle_reescalation_event(
    envelope: dict,
    publisher: EventPublisher,
    run_pipeline: Callable[[TriageState], Awaitable[None]],
) -> Optional[TriageState]:
    """Handle an incident.reescalate event from the reescalations channel."""
    event_id = envelope.get("event_id", "unknown")

    try:
        incident = IncidentEvent.model_validate(envelope["payload"])
    except (ValidationError, KeyError) as exc:
        logger.warning(
            "Deserialization failed for reescalation event_id=%s: %s", event_id, exc
        )
        await _publish_error(publisher, event_id, str(exc), "reescalations")
        return None

    reporter_feedback = incident.reporter_feedback or ""
    original_classification = incident.original_classification or ""

    state = TriageState(
        incident_id=incident.incident_id,
        source_type=incident.source_type,
        event_id=event_id,
        incident=incident.model_dump(),
        reescalation=True,
        reporter_feedback=reporter_feedback,
        original_classification=original_classification,
        prompt_injection_detected=incident.prompt_injection_detected,
        triage_started_at=time.monotonic(),
    )

    logger.info(
        "Triage started for incident %s, source: %s, reescalation: True, has_feedback: %s (event_id=%s)",
        state.incident_id,
        state.source_type,
        bool(reporter_feedback),
        event_id,
    )

    await run_pipeline(state)
    return state
