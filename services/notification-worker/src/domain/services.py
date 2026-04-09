import logging

from pydantic import ValidationError

from src.adapters.outbound.slack_client import SlackClient
from src.domain.models import Notification, NotificationType

logger = logging.getLogger(__name__)

_SEVERITY_EMOJI = {
    "critical": "🔴 [P1]",
    "high": "🟠 [P2]",
    "medium": "🟡 [P3]",
    "low": "🔵 [P4]",
}

_slack_client = SlackClient()


def _build_source_label(source_type: str | None) -> str:
    if source_type == "proactive":
        return "🤖 Proactive OTEL detection"
    return "👤 User-reported"


def build_team_alert_blocks(notification: Notification) -> list[dict]:
    severity_label = _SEVERITY_EMOJI.get(notification.severity or "", "⚪")
    title = notification.title or notification.incident_id
    source_label = _build_source_label(notification.source_type)
    confidence = notification.confidence if notification.confidence is not None else "N/A"

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{severity_label} {title}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Component:* {notification.component or 'Unknown'}"},
                {"type": "mrkdwn", "text": f"*Confidence:* {confidence}"},
                {"type": "mrkdwn", "text": f"*Source:* {source_label}"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Root Cause:* {notification.summary or 'No summary available'}",
            },
        },
    ]

    if notification.ticket_url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Ticket"},
                        "url": notification.ticket_url,
                    }
                ],
            }
        )

    return blocks


async def handle_team_alert(notification: Notification, event_id: str) -> None:
    logger.info(
        "Building team alert for incident=%s (event_id=%s)",
        notification.incident_id,
        event_id,
    )
    blocks = build_team_alert_blocks(notification)
    severity_label = _SEVERITY_EMOJI.get(notification.severity or "", "⚪")
    title = notification.title or notification.incident_id
    fallback_text = f"{severity_label} {title}"

    success = await _slack_client.send_team_alert(blocks, fallback_text, event_id=event_id)
    if success:
        logger.info(
            "Team alert sent for incident=%s (event_id=%s)",
            notification.incident_id,
            event_id,
        )
    else:
        logger.error(
            "Failed to send team alert for incident=%s (event_id=%s)",
            notification.incident_id,
            event_id,
        )


async def handle_reporter_update(notification: Notification, event_id: str) -> None:
    """Stub: Story 5.3 implements Slack DM to reporter."""
    logger.info(
        "Notification type=%s for incident=%s — handler not yet implemented (event_id=%s)",
        notification.type.value,
        notification.incident_id,
        event_id,
    )


async def handle_reporter_resolved(notification: Notification, event_id: str) -> None:
    """Stub: Story 5.3 implements Slack DM to reporter."""
    logger.info(
        "Notification type=%s for incident=%s — handler not yet implemented (event_id=%s)",
        notification.type.value,
        notification.incident_id,
        event_id,
    )


_HANDLERS = {
    NotificationType.team_alert: handle_team_alert,
    NotificationType.reporter_update: handle_reporter_update,
    NotificationType.reporter_resolved: handle_reporter_resolved,
}


async def route_notification(envelope: dict, event_id: str) -> None:
    """Deserialize notification payload and route to the correct handler."""
    try:
        payload = envelope["payload"]
    except (KeyError, TypeError):
        logger.warning("Missing payload in notification envelope (event_id=%s)", event_id)
        return

    try:
        notification = Notification.model_validate(payload)
    except ValidationError as exc:
        logger.warning(
            "Invalid notification payload (event_id=%s): %s",
            event_id,
            exc,
        )
        return

    handler = _HANDLERS.get(notification.type)
    if handler is None:
        logger.warning(
            "Unknown notification type=%s — skipping (event_id=%s)",
            notification.type,
            event_id,
        )
        return

    logger.info(
        "Routing notification type=%s for incident=%s (event_id=%s)",
        notification.type.value,
        notification.incident_id,
        event_id,
    )

    try:
        await handler(notification, event_id)
    except Exception:
        logger.exception(
            "Handler error for notification type=%s incident=%s (event_id=%s)",
            notification.type.value,
            notification.incident_id,
            event_id,
        )
