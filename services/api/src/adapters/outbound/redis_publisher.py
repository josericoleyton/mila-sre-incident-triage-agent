import json
import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis

from src.config import REDIS_URL
from src.ports.outbound import EventPublisher

logger = logging.getLogger(__name__)


class RedisPublisher(EventPublisher):
    def __init__(self) -> None:
        self._redis = aioredis.from_url(REDIS_URL)

    async def close(self) -> None:
        await self._redis.aclose()

    async def publish(self, channel: str, event_type: str, payload: dict) -> str:
        event_id = str(uuid.uuid4())
        envelope = {
            "event_id": event_id,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "api",
            "payload": payload,
        }
        await self._redis.publish(channel, json.dumps(envelope))
        logger.info("Published %s to %s (event_id=%s)", event_type, channel, event_id)
        return event_id
