import asyncio
import logging

from src.adapters.inbound.redis_consumer import RedisConsumer
from src.domain.services import route_notification

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"notification-worker","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)


async def on_notification(envelope: dict) -> None:
    """Callback invoked by the Redis consumer for each notification event."""
    event_id = envelope.get("event_id", "unknown")
    try:
        await route_notification(envelope, event_id)
    except Exception:
        logger.exception("Unhandled error processing notification (event_id=%s)", event_id)


async def main():
    logger.info("Service notification-worker started")

    consumer = RedisConsumer()

    try:
        await consumer.subscribe("notifications", on_notification)
    finally:
        await consumer.close()


if __name__ == "__main__":
    asyncio.run(main())
