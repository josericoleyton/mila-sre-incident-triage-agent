import asyncio
import logging

from slack_sdk.web.async_client import AsyncWebClient

from src.config import SLACK_BOT_TOKEN, SLACK_CHANNEL_ID
from src.ports.outbound import ReporterNotifier, TeamNotifier

logger = logging.getLogger(__name__)

RETRY_DELAY_SECONDS = 2
MAX_ATTEMPTS = 2


class SlackClient(TeamNotifier, ReporterNotifier):
    def __init__(self, bot_token: str | None = None, channel_id: str | None = None) -> None:
        self._bot_token = bot_token or SLACK_BOT_TOKEN
        self._channel_id = channel_id or SLACK_CHANNEL_ID
        if not self._bot_token:
            logger.warning("SLACK_BOT_TOKEN is not configured — Slack notifications will fail")
        if not self._channel_id:
            logger.warning("SLACK_CHANNEL_ID is not configured — Slack team alerts will fail")
        self._web_client = AsyncWebClient(token=self._bot_token) if self._bot_token else None

    async def send_team_alert(self, blocks: list[dict], fallback_text: str, event_id: str = "unknown") -> bool:
        if not self._web_client:
            logger.error("SLACK_BOT_TOKEN not configured — cannot send team alert (event_id=%s)", event_id)
            return False
        if not self._channel_id:
            logger.error("SLACK_CHANNEL_ID not configured — cannot send team alert (event_id=%s)", event_id)
            return False

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                await self._web_client.chat_postMessage(
                    channel=self._channel_id,
                    text=fallback_text,
                    blocks=blocks,
                )
                return True
            except Exception:
                logger.warning(
                    "Slack team alert failed (attempt %d/%d, event_id=%s)",
                    attempt,
                    MAX_ATTEMPTS,
                    event_id,
                    exc_info=True,
                )

            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

        logger.error("Slack team alert failed after %d attempts — giving up (event_id=%s)", MAX_ATTEMPTS, event_id)
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
                user_resp = await self._web_client.users_lookupByEmail(email=reporter_email)
                user_id = user_resp["user"]["id"]

                conv_resp = await self._web_client.conversations_open(users=[user_id])
                channel_id = conv_resp["channel"]["id"]

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