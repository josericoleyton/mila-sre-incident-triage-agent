import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"notification-worker","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Service notification-worker started")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
