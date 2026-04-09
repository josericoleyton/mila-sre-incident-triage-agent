import asyncio
import logging

from slack_sdk.webhook import WebhookClient

from src.config import SLACK_DM_WEBHOOK_URL, SLACK_WEBHOOK_URL
from src.ports.outbound import ReporterNotifier, TeamNotifier

logger = logging.getLogger(__name__)

RETRY_DELAY_SECONDS = 2
MAX_ATTEMPTS = 2


class SlackClient(TeamNotifier, ReporterNotifier):
    def __init__(self, webhook_url: str | None = None, dm_webhook_url: str | None = None) -> None:
        self._webhook_url = webhook_url or SLACK_WEBHOOK_URL
        self._dm_webhook_url = dm_webhook_url or SLACK_DM_WEBHOOK_URL
        if not self._webhook_url:
            logger.warning("SLACK_WEBHOOK_URL is not configured — Slack team notifications will fail")
        if not self._dm_webhook_url:
            logger.warning("SLACK_DM_WEBHOOK_URL is not configured — Slack DM notifications will fail")
        self._client = WebhookClient(url=self._webhook_url)
        self._dm_client = WebhookClient(url=self._dm_webhook_url) if self._dm_webhook_url else None

    async def send_team_alert(self, blocks: list[dict], fallback_text: str, event_id: str = "unknown") -> bool:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await asyncio.to_thread(
                    self._client.send, text=fallback_text, blocks=blocks
                )
                if response.status_code == 200:
                    return True
                logger.warning(
                    "Slack webhook returned status=%d body=%s (attempt %d/%d, event_id=%s)",
                    response.status_code,
                    response.body,
                    attempt,
                    MAX_ATTEMPTS,
                    event_id,
                )
            except Exception:
                logger.warning(
                    "Slack webhook request failed (attempt %d/%d, event_id=%s)",
                    attempt,
                    MAX_ATTEMPTS,
                    event_id,
                    exc_info=True,
                )

            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

        logger.error("Slack webhook failed after %d attempts — giving up (event_id=%s)", MAX_ATTEMPTS, event_id)
        return False

    async def send_dm(self, blocks: list[dict], fallback_text: str, event_id: str = "unknown") -> bool:
        if not self._dm_client:
            logger.error("SLACK_DM_WEBHOOK_URL not configured — cannot send DM (event_id=%s)", event_id)
            return False

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await asyncio.to_thread(
                    self._dm_client.send, text=fallback_text, blocks=blocks
                )
                if response.status_code == 200:
                    return True
                logger.warning(
                    "Slack DM webhook returned status=%d body=%s (attempt %d/%d, event_id=%s)",
                    response.status_code,
                    response.body,
                    attempt,
                    MAX_ATTEMPTS,
                    event_id,
                )
            except Exception:
                logger.warning(
                    "Slack DM webhook request failed (attempt %d/%d, event_id=%s)",
                    attempt,
                    MAX_ATTEMPTS,
                    event_id,
                    exc_info=True,
                )

            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

        logger.error("Slack DM webhook failed after %d attempts — giving up (event_id=%s)", MAX_ATTEMPTS, event_id)
        return False