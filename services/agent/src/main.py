import asyncio
import logging

from pydantic_ai import Agent

from src.adapters.inbound.redis_consumer import RedisConsumer
from src.adapters.outbound.redis_publisher import RedisPublisher
from src.config import LLM_MODEL
from src.domain.models import TriageState
from src.domain.triage_handler import handle_incident_event, handle_reescalation_event

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"agent","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)


def init_agent() -> Agent:
    """Initialize the Pydantic AI Agent with the configured LLM model."""
    try:
        agent = Agent(LLM_MODEL)
        logger.info("Agent initialized with model: %s", LLM_MODEL)
        return agent
    except Exception as exc:
        logger.error("Failed to initialize agent with model %s: %s", LLM_MODEL, exc)
        raise


async def run_pipeline(state: TriageState) -> None:
    """Stub: will be replaced by the graph pipeline in Story 3.3a."""
    logger.info("Triage pipeline triggered for incident %s (event_id=%s)", state.incident_id, state.event_id)


async def main():
    logger.info("Service agent started")

    agent = init_agent()

    publisher = RedisPublisher()
    consumer = RedisConsumer()

    async def on_incident(envelope: dict) -> None:
        await handle_incident_event(envelope, publisher, run_pipeline)

    async def on_reescalation(envelope: dict) -> None:
        await handle_reescalation_event(envelope, publisher, run_pipeline)

    try:
        await consumer.subscribe_multi(
            {
                "incidents": on_incident,
                "reescalations": on_reescalation,
            },
            error_publisher=publisher,
        )
    finally:
        try:
            await consumer.close()
        finally:
            await publisher.close()


if __name__ == "__main__":
    asyncio.run(main())
