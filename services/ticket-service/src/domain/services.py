import logging
from typing import Optional

from pydantic import ValidationError

from src.domain.models import TicketCommand
from src.ports.outbound import EventPublisher

logger = logging.getLogger(__name__)

SUPPORTED_ACTIONS = {"create_engineering_ticket"}


async def _publish_error(publisher: EventPublisher, event_id: str, error: str, source_channel: str) -> None:
    try:
        await publisher.publish(
            "errors",
            "ticket.error",
            {"event_id": event_id, "error": error, "source_channel": source_channel},
        )
    except Exception:
        logger.exception("Failed to publish ticket.error for event_id=%s", event_id)


async def handle_ticket_command(
    envelope: dict,
    publisher: EventPublisher,
) -> Optional[TicketCommand]:
    event_id = envelope.get("event_id", "unknown")

    try:
        command = TicketCommand.model_validate(envelope["payload"])
    except (ValidationError, KeyError) as exc:
        logger.warning("Deserialization failed for event_id=%s: %s", event_id, exc)
        await _publish_error(publisher, event_id, str(exc), "ticket-commands")
        return None

    if command.action not in SUPPORTED_ACTIONS:
        logger.warning(
            "Unrecognized action '%s' for event_id=%s — skipping",
            command.action,
            event_id,
        )
        return None

    logger.info(
        "Routing ticket command action=%s incident_id=%s (event_id=%s)",
        command.action,
        command.incident_id,
        event_id,
    )

    # Stub: actual handler implementations are added in Story 4.2
    if command.action == "create_engineering_ticket":
        logger.info("create_engineering_ticket routed for incident_id=%s (event_id=%s)", command.incident_id, event_id)

    return command
