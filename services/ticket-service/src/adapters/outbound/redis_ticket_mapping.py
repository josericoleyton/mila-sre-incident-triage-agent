import logging
from typing import Optional

import redis.asyncio as aioredis

from src.config import REDIS_URL
from src.ports.ticket_mapping import TicketMappingStore

logger = logging.getLogger(__name__)

MAPPING_KEY_PREFIX = "ticket-mapping:"
RESOLVED_SET_KEY = "resolved-tickets"
MAPPING_TTL_SECONDS = 90 * 24 * 60 * 60  # 90 days


class RedisTicketMappingStore(TicketMappingStore):
    def __init__(self, redis_client: aioredis.Redis | None = None) -> None:
        self._redis = redis_client or aioredis.from_url(REDIS_URL)
        self._owns_client = redis_client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._redis.aclose()

    async def save_mapping(
        self,
        linear_ticket_id: str,
        incident_id: str,
        reporter_email: Optional[str],
        identifier: str,
        url: str,
    ) -> None:
        key = f"{MAPPING_KEY_PREFIX}{linear_ticket_id}"
        mapping = {
            "incident_id": incident_id,
            "reporter_email": reporter_email or "",
            "identifier": identifier,
            "url": url,
        }
        await self._redis.hset(key, mapping=mapping)
        await self._redis.expire(key, MAPPING_TTL_SECONDS)
        logger.info(
            "Saved ticket mapping: %s -> incident_id=%s",
            identifier,
            incident_id,
        )

    async def get_mapping(self, linear_ticket_id: str) -> Optional[dict]:
        key = f"{MAPPING_KEY_PREFIX}{linear_ticket_id}"
        data = await self._redis.hgetall(key)
        if not data:
            return None
        decoded = {k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in data.items()}
        if decoded.get("reporter_email") == "":
            decoded["reporter_email"] = None
        return decoded

    async def mark_resolved(self, linear_ticket_id: str) -> bool:
        added = await self._redis.sadd(RESOLVED_SET_KEY, linear_ticket_id)
        return added > 0
