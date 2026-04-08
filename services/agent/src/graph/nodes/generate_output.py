from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic_graph import BaseNode, End, GraphRunContext

from src.domain.models import TriageDeps, TriageResult, TriageState

logger = logging.getLogger(__name__)


@dataclass
class GenerateOutputNode(BaseNode[TriageState, TriageDeps, TriageResult]):
    async def run(self, ctx: GraphRunContext[TriageState]) -> End[TriageResult]:
        state = ctx.state

        if state.triage_result is None:
            logger.error(
                "GenerateOutputNode: no triage_result available for incident %s (event_id=%s)",
                state.incident_id,
                state.event_id,
            )
            return End(
                TriageResult(
                    classification="non_incident",
                    confidence=0.0,
                    reasoning="Classification failed — no result produced.",
                    severity_assessment="unknown — classification failed",
                )
            )

        result = state.triage_result

        logger.info(
            "GenerateOutputNode: classification=%s, confidence=%.2f, source_type=%s (event_id=%s)",
            result.classification.value if hasattr(result.classification, "value") else result.classification,
            result.confidence,
            state.source_type,
            state.event_id,
        )

        # Routing stubs — Stories 3.4, 3.5, 3.6 implement specific output paths:
        # - bug + userIntegration → ticket-commands + team notification
        # - bug + systemIntegration → ticket-commands + team notification
        # - non_incident → reporter DM (Story 3.6)
        # For now, just log the routing decision.

        classification = result.classification.value if hasattr(result.classification, "value") else str(result.classification)

        if classification == "bug":
            logger.info(
                "Routing: BUG path for incident %s, source_type=%s (event_id=%s) — ticket creation pending Story 3.4",
                state.incident_id,
                state.source_type,
                state.event_id,
            )
        else:
            logger.info(
                "Routing: NON-INCIDENT path for incident %s, source_type=%s (event_id=%s) — dismissal pending Story 3.6",
                state.incident_id,
                state.source_type,
                state.event_id,
            )

        return End(result)
