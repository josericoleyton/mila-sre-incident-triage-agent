import logging

from pydantic import ValidationError

from src.domain.models import Notification, NotificationType

logger = logging.getLogger(__name__)


async def handle_team_alert(notification: Notification, event_id: str) -> None:
    """Stub: Story 5.2 implements Slack channel message."""
    logger.info(
        "Notification type=%s for incident=%s — handler not yet implemented (event_id=%s)",
        notification.type.value,
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
