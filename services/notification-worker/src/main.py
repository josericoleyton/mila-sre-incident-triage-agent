import asyncio
import logging

from src.json_logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


async def main():
    logger.info("Service notification-worker started")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
