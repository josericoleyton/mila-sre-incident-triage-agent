import asyncio
import logging

from slack_sdk.webhook import WebhookClient
from slack_sdk.web.async_client import AsyncWebClient

from src.config import SLACK_BOT_TOKEN, SLACK_WEBHOOK_URL
from src.ports.outbound import ReporterNotifier, TeamNotifier

logger = logging.getLogger(__name__)

RETRY_DELAY_SECONDS = 2
MAX_ATTEMPTS = 2


class SlackClient(TeamNotifier, ReporterNotifier):
    def __init__(self, webhook_url: str | None = None, bot_token: str | None = None) -> None:
        self._webhook_url = webhook_url or SLACK_WEBHOOK_URL
        self._bot_token = bot_token or SLACK_BOT_TOKEN
        if not self._webhook_url:
            logger.warning("SLACK_WEBHOOK_URL is not configured — Slack team notifications will fail")
        if not self._bot_token:
            logger.warning("SLACK_BOT_TOKEN is not configured — Slack DM notifications will fail")
        self._client = WebhookClient(url=self._webhook_url)
        self._web_client = AsyncWebClient(token=self._bot_token) if self._bot_token else None

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

    async def send_dm(self, reporter_email: str, blocks: list[dict], fallback_text: str, event_id: str = "unknown") -> bool:
        if not self._web_client:
            logger.error("SLACK_BOT_TOKEN not configured — cannot send DM (event_id=%s)", event_id)
            return False

        if not reporter_email:
            logger.warning("No reporter_email provided — cannot send DM (event_id=%s)", event_id)
            return False

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                # Look up Slack user by email
                user_resp = await self._web_client.users_lookupByEmail(email=reporter_email)
                user_id = user_resp["user"]["id"]

                # Open a DM channel
                conv_resp = await self._web_client.conversations_open(users=[user_id])
                channel_id = conv_resp["channel"]["id"]

                # Send the message
                await self._web_client.chat_postMessage(
                    channel=channel_id,
                    text=fallback_text,
                    blocks=blocks,
                )
                return True
            except Exception:
                logger.warning(
                    "Slack DM send failed for email=%s (attempt %d/%d, event_id=%s)",
                    reporter_email,
                    attempt,
                    MAX_ATTEMPTS,
                    event_id,
                    exc_info=True,
                )

            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

        logger.error("Slack DM failed after %d attempts — giving up (event_id=%s)", MAX_ATTEMPTS, event_id)
        return False