import asyncio
import logging

import uvicorn

from src import config
from src.adapters.inbound.redis_consumer import RedisConsumer
from src.adapters.inbound.webhook_listener import create_app
from src.adapters.outbound.linear_client import LinearClient
from src.adapters.outbound.redis_publisher import RedisPublisher
from src.adapters.outbound.redis_ticket_mapping import RedisTicketMappingStore
from src.domain.services import handle_ticket_command
from src.json_logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


async def start_consumer(
    consumer: RedisConsumer,
    publisher: RedisPublisher,
    linear_client: LinearClient,
    mapping_store: RedisTicketMappingStore,
) -> None:
    async def on_ticket_command(envelope: dict) -> None:
        await handle_ticket_command(envelope, publisher, ticket_creator=linear_client, mapping_store=mapping_store)

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
    linear_client: LinearClient | None = None
    mapping_store: RedisTicketMappingStore | None = None
    app = None

    try:
        consumer = RedisConsumer()
        publisher = RedisPublisher()
        linear_client = LinearClient()
        mapping_store = RedisTicketMappingStore()
        app = create_app(mapping_store=mapping_store, publisher=publisher)
        await asyncio.gather(
            start_consumer(consumer, publisher, linear_client, mapping_store),
            run_uvicorn(app, port=8002),
        )
    finally:
        if linear_client:
            await linear_client.close()
        if consumer:
            await consumer.close()
        if publisher:
            await publisher.close()
        if mapping_store:
            await mapping_store.close()
        logger.info("Service ticket-service stopped")


if __name__ == "__main__":
    asyncio.run(main())
