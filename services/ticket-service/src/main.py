import asyncio
import logging

import uvicorn

from src import config
from src.adapters.inbound.redis_consumer import RedisConsumer
from src.adapters.inbound.webhook_listener import create_app
from src.adapters.outbound.redis_publisher import RedisPublisher
from src.domain.services import handle_ticket_command

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"ticket-service","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)


async def start_consumer(consumer: RedisConsumer, publisher: RedisPublisher) -> None:
    async def on_ticket_command(envelope: dict) -> None:
        await handle_ticket_command(envelope, publisher)

    await consumer.subscribe("ticket-commands", on_ticket_command)


async def run_uvicorn(app, port: int = 8002) -> None:
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    logger.info("Service ticket-service started")

    if not getattr(config, 'LINEAR_WEBHOOK_SECRET', None):
        logger.warning("LINEAR_WEBHOOK_SECRET is not set — webhook signature verification will reject all requests")

    consumer: RedisConsumer | None = None
    publisher: RedisPublisher | None = None
    app = create_app()

    try:
        consumer = RedisConsumer()
        publisher = RedisPublisher()
        await asyncio.gather(
            start_consumer(consumer, publisher),
            run_uvicorn(app, port=8002),
        )
    finally:
        if consumer:
            await consumer.close()
        if publisher:
            await publisher.close()
        logger.info("Service ticket-service stopped")


if __name__ == "__main__":
    asyncio.run(main())
