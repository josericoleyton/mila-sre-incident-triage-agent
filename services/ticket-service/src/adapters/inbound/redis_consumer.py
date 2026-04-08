import asyncio
import json
import logging
from typing import Callable, Awaitable

import redis.asyncio as aioredis

from src.config import REDIS_URL
from src.ports.inbound import EventConsumer

logger = logging.getLogger(__name__)

REQUIRED_ENVELOPE_FIELDS = {"event_id", "event_type", "timestamp", "source", "payload"}


class RedisConsumer(EventConsumer):
    def __init__(self) -> None:
        self._redis = aioredis.from_url(REDIS_URL)
        self._pubsub = None

    async def close(self) -> None:
        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.aclose()
        await self._redis.aclose()

    async def subscribe(self, channel: str, handler: Callable[[dict], Awaitable[None]]) -> None:
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(channel)
        logger.info("Subscribed to channel: %s", channel)
        try:
            async for message in self._pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    envelope = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning("Malformed message on %s — not valid JSON: %s", channel, exc)
                    continue

                missing = REQUIRED_ENVELOPE_FIELDS - set(envelope.keys())
                if missing:
                    logger.warning("Malformed envelope on %s — missing fields: %s", channel, missing)
                    continue

                logger.info(
                    "Received %s on %s (event_id=%s)",
                    envelope["event_type"],
                    channel,
                    envelope["event_id"],
                )
                await handler(envelope)
        except asyncio.CancelledError:
            logger.info("Consumer for %s shutting down", channel)
            raise
