import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"ticket-service","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Service ticket-service started")
    # Will start both Redis consumer and FastAPI webhook server in future stories
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
