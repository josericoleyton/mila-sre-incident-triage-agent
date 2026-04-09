import asyncio
import logging

from pydantic_ai import Agent

from src.adapters.inbound.redis_consumer import RedisConsumer
from src.adapters.outbound.github_client import GitHubClient
from src.adapters.outbound.redis_publisher import RedisPublisher
from src.config import LLM_MODEL
from src.domain.models import TriageDeps, TriageState
from src.domain.triage_handler import handle_incident_event, handle_reescalation_event
from src.graph.nodes.analyze_input import AnalyzeInputNode
from src.graph.workflow import triage_graph
from src.json_logging import setup_logging

setup_logging()
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


async def run_pipeline(state: TriageState, deps: TriageDeps) -> None:
    """Run the triage graph pipeline for an incident."""
    logger.info("Triage pipeline started for incident %s (event_id=%s)", state.incident_id, state.event_id)
    try:
        result = await triage_graph.run(AnalyzeInputNode(), state=state, deps=deps)
        logger.info(
            "Triage pipeline completed for incident %s: classification=%s (event_id=%s)",
            state.incident_id,
            result.output.classification.value if result.output else "none",
            state.event_id,
        )
    except Exception:
        logger.exception("Triage pipeline failed for incident %s (event_id=%s)", state.incident_id, state.event_id)
        try:
            await deps.publisher.publish(
                "errors",
                "ticket.error",
                {
                    "event_id": state.event_id,
                    "incident_id": state.incident_id,
                    "error": "Triage pipeline crashed",
                    "source_channel": "agent",
                },
            )
        except Exception:
            logger.exception("Failed to publish pipeline error for event_id=%s", state.event_id)


async def main():
    logger.info("Service agent started")

    agent = init_agent()

    publisher = RedisPublisher()
    consumer = RedisConsumer()
    github_client = GitHubClient()
    deps = TriageDeps(github_client=github_client, publisher=publisher)

    async def pipeline(state: TriageState) -> None:
        await run_pipeline(state, deps)

    async def on_incident(envelope: dict) -> None:
        await handle_incident_event(envelope, publisher, pipeline)

    async def on_reescalation(envelope: dict) -> None:
        await handle_reescalation_event(envelope, publisher, pipeline)

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
            try:
                await github_client.close()
            finally:
                await publisher.close()


if __name__ == "__main__":
    asyncio.run(main())
