import asyncio
import json
import logging
from typing import Callable, Awaitable, Optional

import redis.asyncio as aioredis

from src.config import REDIS_URL
from src.ports.inbound import EventConsumer
from src.ports.outbound import EventPublisher

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

    async def subscribe_multi(
        self,
        handlers: dict[str, Callable[[dict], Awaitable[None]]],
        error_publisher: Optional[EventPublisher] = None,
    ) -> None:
        self._pubsub = self._redis.pubsub()
        channels = list(handlers.keys())
        await self._pubsub.subscribe(*channels)
        logger.info("Subscribed to channels: %s", ", ".join(channels))
        try:
            async for message in self._pubsub.listen():
                if message["type"] != "message":
                    continue
                channel = (
                    message["channel"].decode()
                    if isinstance(message["channel"], bytes)
                    else message["channel"]
                )
                try:
                    envelope = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning("Malformed message on %s — not valid JSON: %s", channel, exc)
                    await self._publish_envelope_error(error_publisher, channel, str(exc))
                    continue

                if not isinstance(envelope, dict):
                    logger.warning("Malformed message on %s — expected dict, got %s", channel, type(envelope).__name__)
                    await self._publish_envelope_error(error_publisher, channel, f"expected dict, got {type(envelope).__name__}")
                    continue

                missing = REQUIRED_ENVELOPE_FIELDS - set(envelope.keys())
                if missing:
                    logger.warning("Malformed envelope on %s — missing fields: %s", channel, missing)
                    await self._publish_envelope_error(
                        error_publisher, channel, f"missing fields: {missing}",
                        event_id=envelope.get("event_id"),
                    )
                    continue

                handler = handlers.get(channel)
                if handler is None:
                    logger.warning("No handler registered for channel: %s", channel)
                    continue

                logger.info(
                    "Received %s on %s (event_id=%s)",
                    envelope["event_type"],
                    channel,
                    envelope["event_id"],
                )
                try:
                    await handler(envelope)
                except Exception:
                    logger.exception(
                        "Handler error on %s (event_id=%s)", channel, envelope.get("event_id")
                    )
        except asyncio.CancelledError:
            logger.info("Multi-channel consumer shutting down")
            raise

    @staticmethod
    async def _publish_envelope_error(
        publisher: Optional[EventPublisher],
        channel: str,
        error: str,
        event_id: Optional[str] = None,
    ) -> None:
        if publisher is None:
            return
        try:
            await publisher.publish(
                "errors",
                "ticket.error",
                {"event_id": event_id or "unknown", "error": error, "source_channel": channel},
            )
        except Exception:
            logger.exception("Failed to publish envelope error to errors channel")
