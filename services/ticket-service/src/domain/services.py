import logging
from typing import Optional

from pydantic import ValidationError

from src import config
from src.domain.models import TicketCommand, TicketResult
from src.ports.outbound import EventPublisher, TicketCreator
from src.ports.ticket_mapping import TicketMappingStore

logger = logging.getLogger(__name__)

SUPPORTED_ACTIONS = {"create_engineering_ticket"}

SEVERITY_TO_PRIORITY = {
    "P1": 1,
    "P2": 2,
    "P3": 3,
    "P4": 4,
}


async def _publish_error(publisher: EventPublisher, event_id: str, error: str, source_channel: str) -> None:
    try:
        await publisher.publish(
            "errors",
            "ticket.error",
            {"event_id": event_id, "error": error, "source_channel": source_channel},
        )
    except Exception:
        logger.exception("Failed to publish ticket.error for event_id=%s", event_id)


def _map_severity_to_priority(severity: str) -> int:
    normalized = severity.upper().strip()
    if normalized in SEVERITY_TO_PRIORITY:
        return SEVERITY_TO_PRIORITY[normalized]
    for key, value in SEVERITY_TO_PRIORITY.items():
        idx = normalized.find(key)
        if idx >= 0:
            end = idx + len(key)
            if end >= len(normalized) or not normalized[end].isdigit():
                return value
    logger.warning("Unknown severity '%s', defaulting to P3 (Medium)", severity)
    return 3


async def create_engineering_ticket(
    command: TicketCommand,
    ticket_creator: TicketCreator,
    publisher: EventPublisher,
    event_id: str,
    mapping_store: Optional[TicketMappingStore] = None,
) -> Optional[TicketResult]:
    priority = _map_severity_to_priority(command.severity)

    try:
        issue = await ticket_creator.create_issue(
            title=command.title,
            body=command.body,
            priority=priority,
            labels=command.labels,
            team_id=config.LINEAR_TEAM_ID,
        )
    except Exception as exc:
        logger.error(
            "Linear ticket creation failed for incident_id=%s (event_id=%s): %s",
            command.incident_id,
            event_id,
            exc,
        )
        await _publish_error(publisher, event_id, str(exc), "ticket-commands")
        return None

    result = TicketResult(
        ticket_id=issue["id"],
        identifier=issue["identifier"],
        url=issue["url"],
        incident_id=command.incident_id,
    )

    logger.info(
        "Ticket created: %s for incident_id=%s (event_id=%s)",
        result.identifier,
        result.incident_id,
        event_id,
    )

    # Persist ticket-incident mapping for resolution correlation (Story 4.3)
    if mapping_store is not None:
        try:
            await mapping_store.save_mapping(
                linear_ticket_id=result.ticket_id,
                incident_id=command.incident_id,
                reporter_slack_user_id=command.reporter_slack_user_id,
                identifier=result.identifier,
                url=result.url,
            )
        except Exception:
            logger.exception("Failed to save ticket mapping for event_id=%s", event_id)

    # Publish team notification
    try:
        await publisher.publish(
            "notifications",
            "notification.send",
            {
                "type": "team_alert",
                "ticket_url": result.url,
                "severity": command.severity,
                "component": command.labels[0] if command.labels else "unknown",
                "summary": command.title,
                "incident_id": command.incident_id,
                "reporter_slack_user_id": command.reporter_slack_user_id,
            },
        )
    except Exception:
        logger.exception("Failed to publish team_alert notification for event_id=%s", event_id)

    # Publish reporter notification if reporter exists
    if command.reporter_slack_user_id:
        try:
            await publisher.publish(
                "notifications",
                "notification.send",
                {
                    "type": "reporter_update",
                    "slack_user_id": command.reporter_slack_user_id,
                    "message": (
                        f"Your incident report has been received and escalated to the engineering team. "
                        f"Tracking ID: {command.incident_id}"
                    ),
                    "incident_id": command.incident_id,
                },
            )
        except Exception:
            logger.exception("Failed to publish reporter_update notification for event_id=%s", event_id)

    return result


async def handle_ticket_command(
    envelope: dict,
    publisher: EventPublisher,
    ticket_creator: Optional[TicketCreator] = None,
    mapping_store: Optional[TicketMappingStore] = None,
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

    if command.action == "create_engineering_ticket":
        if ticket_creator is None:
            logger.error("No ticket_creator configured for event_id=%s", event_id)
            await _publish_error(publisher, event_id, "ticket_creator not configured", "ticket-commands")
            return None
        result = await create_engineering_ticket(command, ticket_creator, publisher, event_id, mapping_store)
        if result is None:
            return None

    return command


RESOLVED_STATES = {"Done", "Resolved"}


async def handle_resolution_webhook(
    payload: dict,
    mapping_store: TicketMappingStore,
    publisher: EventPublisher,
    event_id: str,
) -> bool:
    """Process a Linear Issue update webhook for resolution lifecycle.

    Returns True if a reporter_resolved notification was published.
    """
    action = payload.get("action")
    webhook_type = payload.get("type")

    if webhook_type != "Issue" or action != "update":
        logger.info("Ignoring non-issue-update webhook: type=%s action=%s (event_id=%s)", webhook_type, action, event_id)
        return False

    data = payload.get("data", {})
    state_name = data.get("state", {}).get("name", "")

    if state_name not in RESOLVED_STATES:
        logger.info(
            "Ignoring non-resolution state change: state=%s (event_id=%s)",
            state_name,
            event_id,
        )
        return False

    linear_ticket_id = data.get("id", "")
    identifier = data.get("identifier", "unknown")
    title = data.get("title", "")
    ticket_url = data.get("url", "")

    if not linear_ticket_id:
        logger.warning("Resolution webhook missing data.id — skipping (event_id=%s)", event_id)
        return False

    logger.info(
        "Resolution detected for %s (linear_id=%s, event_id=%s)",
        identifier,
        linear_ticket_id,
        event_id,
    )

    # Correlate ticket to incident (before idempotency gate so we don't
    # burn the resolved flag for non-tracked tickets)
    mapping = await mapping_store.get_mapping(linear_ticket_id)
    if mapping is None:
        logger.info(
            "Non-tracked ticket %s — no mapping found, ignoring (event_id=%s)",
            identifier,
            event_id,
        )
        return False

    # Idempotency: check if already resolved
    is_new_resolution = await mapping_store.mark_resolved(linear_ticket_id)
    if not is_new_resolution:
        logger.info(
            "Duplicate resolution webhook for %s — skipping (event_id=%s)",
            identifier,
            event_id,
        )
        return False

    incident_id = mapping["incident_id"]
    reporter_slack_user_id = mapping.get("reporter_slack_user_id")

    # Skip notification for proactive incidents (no reporter)
    if not reporter_slack_user_id:
        logger.info(
            "No reporter for incident_id=%s (proactive incident) — skipping notification (event_id=%s)",
            incident_id,
            event_id,
        )
        return False

    # Publish reporter_resolved notification
    message = f"Your reported incident '{title}' has been resolved by the engineering team."
    try:
        await publisher.publish(
            "notifications",
            "notification.send",
            {
                "type": "reporter_resolved",
                "slack_user_id": reporter_slack_user_id,
                "message": message,
                "incident_id": incident_id,
                "ticket_url": ticket_url,
            },
        )
    except Exception:
        logger.exception(
            "Failed to publish reporter_resolved notification for incident_id=%s (event_id=%s)",
            incident_id,
            event_id,
        )
        return False

    logger.info(
        "Published reporter_resolved notification for incident_id=%s to %s (event_id=%s)",
        incident_id,
        reporter_slack_user_id,
        event_id,
    )
    return True
