import logging

from pydantic import ValidationError

from src.adapters.outbound.slack_client import SlackClient
from src.domain.models import Notification, NotificationType

logger = logging.getLogger(__name__)

_SEVERITY_MAP = {
    "critical": ("🔴", "P1"),
    "high": ("🟠", "P2"),
    "medium": ("🟡", "P3"),
    "low": ("🔵", "P4"),
    "P1": ("🔴", "P1"),
    "P2": ("🟠", "P2"),
    "P3": ("🟡", "P3"),
    "P4": ("🔵", "P4"),
}

_slack_client = SlackClient()


def _resolve_severity(raw: str | None) -> tuple[str, str]:
    """Return (emoji, label) for a severity string."""
    return _SEVERITY_MAP.get(raw or "", ("⚪", "P4"))


def build_team_alert_blocks(notification: Notification) -> list[dict]:
    emoji, severity_label = _resolve_severity(notification.severity)
    component = notification.component or "Unknown"
    short_title = notification.title or notification.incident_id

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} [{severity_label}] {component}: {short_title}",
            },
        },
    ]

    # Reporter / Source line
    if notification.source_type == "systemIntegration":
        reporter_line = "🤖 Detected by Mila via OpenTelemetry"
    else:
        reporter_line = f"Reporter: {notification.reporter_email or 'Unknown'}"

    fields = [{"type": "mrkdwn", "text": reporter_line}]

    blocks.append({
        "type": "section",
        "fields": fields,
    })

    # Root Cause: truncated to 300 chars
    summary = notification.summary or "No summary available"
    if len(summary) > 300:
        summary = summary[:300] + "..."

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*Root Cause:* {summary}",
        },
    })

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
    emoji, severity_label = _resolve_severity(notification.severity)
    component = notification.component or "Unknown"
    title = notification.title or notification.incident_id
    fallback_text = f"{emoji} [{severity_label}] {component}: {title}"

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


def build_reporter_update_blocks(notification: Notification) -> list[dict]:
    """Build Block Kit blocks for a reporter_update DM."""
    message = notification.message or "Your incident report has been analyzed."

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📋 Incident Update",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": message,
            },
        },
    ]

    # Context: show incident title when available (escalation DMs),
    # otherwise fall back to confidence + incident_id (non-incident DMs)
    if notification.title:
        context_text = f"*Incident:* {notification.title}"
    else:
        context_text = f"*Incident:* {notification.incident_id}"

    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": context_text,
            },
        ],
    })

    if notification.allow_reescalation:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ This didn't help — Re-escalate"},
                        "style": "danger",
                        "action_id": f"reescalate_{notification.incident_id}",
                        "value": notification.incident_id,
                    }
                ],
            }
        )

    return blocks


def build_reporter_resolved_blocks(notification: Notification) -> list[dict]:
    """Build Block Kit blocks for a reporter_resolved DM."""
    title = notification.title or notification.incident_id

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🎉 Incident Resolved",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Your reported incident *'{title}'* has been resolved "
                    "by the engineering team. You can view the details in the "
                    "ticket below."
                ),
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


async def handle_reporter_update(notification: Notification, event_id: str) -> None:
    """Send a Slack DM to the reporter with the triage update."""
    logger.info(
        "Building reporter DM (type=%s) for incident=%s (event_id=%s)",
        notification.type.value,
        notification.incident_id,
        event_id,
    )
    blocks = build_reporter_update_blocks(notification)
    fallback_text = notification.message or "Your incident report has been analyzed."

    success = await _slack_client.send_dm(notification.reporter_email or "", blocks, fallback_text, event_id=event_id)
    if success:
        logger.info(
            "Reporter DM sent for incident=%s (event_id=%s)",
            notification.incident_id,
            event_id,
        )
    else:
        logger.error(
            "Failed to send reporter DM for incident=%s (event_id=%s)",
            notification.incident_id,
            event_id,
        )


async def handle_reporter_resolved(notification: Notification, event_id: str) -> None:
    """Send a Slack DM to the reporter confirming resolution."""
    logger.info(
        "Building resolved DM for incident=%s (event_id=%s)",
        notification.incident_id,
        event_id,
    )
    blocks = build_reporter_resolved_blocks(notification)
    title = notification.title or notification.incident_id
    fallback_text = f"Your reported incident '{title}' has been resolved by the engineering team."

    success = await _slack_client.send_dm(notification.reporter_email or "", blocks, fallback_text, event_id=event_id)
    if success:
        logger.info(
            "Resolved DM sent for incident=%s (event_id=%s)",
            notification.incident_id,
            event_id,
        )
    else:
        logger.error(
            "Failed to send resolved DM for incident=%s (event_id=%s)",
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
