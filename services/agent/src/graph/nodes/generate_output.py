from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from pydantic_graph import BaseNode, End, GraphRunContext

from src.config import CONFIDENCE_THRESHOLD
from src.domain.models import Classification, TriageDeps, TriageResult, TriageState

logger = logging.getLogger(__name__)


def _map_severity(severity_assessment: str) -> str:
    """Map agent severity assessment text to P1-P4."""
    sa = severity_assessment.lower()
    if "critical" in sa:
        return "P1"
    elif "high" in sa:
        return "P2"
    elif "medium" in sa:
        return "P3"
    else:
        return "P4"


def _format_ticket_body(state: TriageState, result: TriageResult) -> str:
    """Build a markdown-formatted ticket body from triage result and incident data."""
    incident = state.incident
    sections: list[str] = []

    # Proactive detection banner for systemIntegration incidents
    if state.source_type == "systemIntegration":
        sections.append(
            "## 🤖 Proactive Detection — This incident was auto-detected from production telemetry (not user-reported)"
        )
        trace_data = incident.get("trace_data") or {}
        if not isinstance(trace_data, dict):
            trace_data = {}
        if trace_data:
            trace_lines = []
            if trace_data.get("service_name"):
                safe_name = str(trace_data["service_name"]).replace("`", "").replace("*", "").replace("_", "")
                trace_lines.append(f"- **Service:** {safe_name}")
            if trace_data.get("trace_id"):
                safe_trace = str(trace_data["trace_id"]).replace("`", "")
                trace_lines.append(f"- **Trace ID:** `{safe_trace}`")
            if trace_data.get("status_code") is not None:
                trace_lines.append(f"- **Status Code:** {trace_data['status_code']}")
            if trace_data.get("error_message"):
                # Sanitize to prevent markdown injection (strip triple backticks)
                safe_error = str(trace_data["error_message"]).replace("```", "'''")
                trace_lines.append(f"- **Error:** `{safe_error}`")
            if trace_lines:
                sections.append("## 📡 OTEL Trace Metadata\n" + "\n".join(trace_lines))

    # Affected files
    if result.file_refs:
        file_lines = "\n".join(f"- `{ref}`" for ref in result.file_refs)
        sections.append(f"## 📍 Affected Files\n{file_lines}")
    else:
        sections.append("## 📍 Affected Files\n- _No specific files identified_")

    # Root cause
    root_cause = result.root_cause or "Unable to determine root cause"
    sections.append(f"## 🔍 Root Cause\n{root_cause}")

    # Suggested fix
    suggested_fix = result.suggested_fix or "Further investigation required"
    sections.append(f"## 🛠️ Suggested Investigation\n{suggested_fix}")

    # Original report
    title = incident.get("title", "N/A")
    component = incident.get("component", "N/A")
    reporter_severity = incident.get("severity", "N/A")
    description = incident.get("description", "")
    report_lines = [
        f"**Title:** {title}",
        f"**Component:** {component}",
        f"**Reporter Severity:** {reporter_severity}",
    ]
    if description:
        # Fence user-supplied description to prevent markdown injection
        report_lines.append(f"\n```\n{description}\n```")
    sections.append("## 📋 Original Report\n" + "\n".join(report_lines))

    # Tracking ID
    sections.append(f"## 🔗 Tracking\nIncident ID: `{state.incident_id}`")

    # Attachments
    attachment_url = incident.get("attachment_url")
    if attachment_url:
        sections.append(f"## 📎 Attachments\n- {attachment_url}")
    elif state.multimodal_content:
        att_lines = "\n".join(f"- {att.get('filename', 'unknown')}" for att in state.multimodal_content)
        sections.append(f"## 📎 Attachments\n{att_lines}")
    else:
        sections.append("## 📎 Attachments\n- _None_")

    # Triage reasoning (metadata only — no raw user input per NFR5)
    sections.append(f"## 🧠 Triage Reasoning\n{result.reasoning}")

    # Assessment
    severity_label = _map_severity(result.severity_assessment)
    assessment_lines = [
        f"- **Confidence:** {result.confidence:.2f}",
        f"- **Severity:** {severity_label} — {result.severity_assessment}",
    ]
    if result.confidence < CONFIDENCE_THRESHOLD:
        assessment_lines.append("- 🟡 *Low confidence — review recommended*")
    sections.append("## 📊 Assessment\n" + "\n".join(assessment_lines))

    return "\n\n".join(sections)


def _build_ticket_command(state: TriageState, result: TriageResult) -> dict:
    """Build the ticket.create command payload."""
    incident = state.incident
    severity = _map_severity(result.severity_assessment)
    title = incident.get("title", "Untitled incident")

    labels = ["triaged-by-mila"]
    component = incident.get("component")
    if component:
        labels.append(component)
    classification_label = result.classification.value if hasattr(result.classification, "value") else str(result.classification)
    labels.append(classification_label)

    return {
        "action": "create_engineering_ticket",
        "title": f"[{severity}] {title}",
        "body": _format_ticket_body(state, result),
        "severity": severity,
        "labels": labels,
        "reporter_slack_user_id": incident.get("reporter_slack_user_id", ""),
        "incident_id": state.incident_id,
        "event_id": state.event_id,
    }


LOW_CONFIDENCE_CAVEAT = (
    "I'm less certain about this classification. "
    "If this doesn't match what you're seeing, please re-escalate."
)


FALLBACK_NON_INCIDENT_MESSAGE = (
    "We determined this is not an incident. If you disagree, please re-escalate."
)

FALLBACK_CLASSIFICATION_FAILED_MESSAGE = (
    "We couldn't fully analyze your report. Please contact an engineer for assistance."
)


def _build_notification_payload(state: TriageState, result: TriageResult) -> dict:
    """Build notification.send payload for non-incident dismissal (AR10: direct to notifications)."""
    message = result.resolution_explanation
    if not message:
        logger.warning(
            "Missing resolution_explanation for incident %s; falling back to reasoning (event_id=%s)",
            state.incident_id,
            state.event_id,
        )
        message = result.reasoning
    if not message:
        message = FALLBACK_NON_INCIDENT_MESSAGE
    if result.confidence < CONFIDENCE_THRESHOLD:
        message = f"{LOW_CONFIDENCE_CAVEAT}\n\n{message}"
    return {
        "type": "reporter_update",
        "slack_user_id": state.incident.get("reporter_slack_user_id", ""),
        "message": message,
        "incident_id": state.incident_id,
        "confidence": result.confidence,
        "allow_reescalation": True,
        "event_id": state.event_id,
    }


def _build_triage_completed_payload(state: TriageState, result: TriageResult, duration_ms: int) -> dict:
    """Build triage.completed event payload (metadata only — no raw user input per NFR5)."""
    classification = result.classification.value if hasattr(result.classification, "value") else str(result.classification)
    return {
        "incident_id": state.incident_id,
        "source_type": state.source_type,
        "classification": classification,
        "confidence": result.confidence,
        "reasoning_summary": result.reasoning[:500] if result.reasoning else "",
        "severity_assessment": result.severity_assessment,
        "forced_escalation": state.forced_escalation,
        "reescalation": state.reescalation,
        "event_id": state.event_id,
        "duration_ms": duration_ms,
    }


@dataclass
class GenerateOutputNode(BaseNode[TriageState, TriageDeps, TriageResult]):
    async def run(self, ctx: GraphRunContext[TriageState]) -> End[TriageResult]:
        state = ctx.state

        # Story 3.5: Set forced_escalation for proactive incidents even on fallback path
        if state.source_type == "systemIntegration":
            state.forced_escalation = True

        if state.triage_result is None:
            logger.error(
                "GenerateOutputNode: no triage_result available for incident %s (event_id=%s)",
                state.incident_id,
                state.event_id,
            )
            fallback = TriageResult(
                classification=Classification.bug if state.source_type == "systemIntegration" else Classification.non_incident,
                confidence=0.0,
                reasoning="Classification failed — no result produced.",
                severity_assessment="unknown — classification failed",
                resolution_explanation=FALLBACK_CLASSIFICATION_FAILED_MESSAGE if state.source_type == "userIntegration" else None,
            )
            if state.source_type == "userIntegration":
                await self._publish_notification(ctx, fallback)
            await self._publish_triage_completed(ctx, fallback)
            return End(fallback)

        result = state.triage_result

        # Story 3.5: Force bug classification for proactive (systemIntegration) incidents
        if state.source_type == "systemIntegration":
            original_classification = result.classification.value if hasattr(result.classification, "value") else str(result.classification)
            result.classification = Classification.bug
            logger.info(
                "Story 3.5: Forced classification from %s to bug for proactive incident %s (event_id=%s)",
                original_classification,
                state.incident_id,
                state.event_id,
            )

        logger.info(
            "GenerateOutputNode: classification=%s, confidence=%.2f, source_type=%s (event_id=%s)",
            result.classification.value if hasattr(result.classification, "value") else result.classification,
            result.confidence,
            state.source_type,
            state.event_id,
        )

        classification = result.classification.value if hasattr(result.classification, "value") else str(result.classification)

        if classification == "bug":
            await self._publish_ticket_create(ctx, result)
        elif state.source_type == "userIntegration":
            # Story 3.6: Non-incident dismissal — publish notification directly to notifications channel (AR10)
            await self._publish_notification(ctx, result)
        else:
            logger.warning(
                "Non-incident with unexpected source_type=%s for incident %s (event_id=%s) — no notification sent",
                state.source_type,
                state.incident_id,
                state.event_id,
            )

        await self._publish_triage_completed(ctx, result)

        return End(result)

    async def _publish_ticket_create(self, ctx: GraphRunContext[TriageState], result: TriageResult) -> None:
        """Publish ticket.create command to ticket-commands channel."""
        state = ctx.state
        command = _build_ticket_command(state, result)
        try:
            event_id = await ctx.deps.publisher.publish("ticket-commands", "ticket.create", command)
            logger.info(
                "Published ticket.create for incident %s to ticket-commands (event_id=%s, published_event_id=%s)",
                state.incident_id,
                state.event_id,
                event_id,
            )
        except Exception:
            logger.exception(
                "Failed to publish ticket.create for incident %s (event_id=%s)",
                state.incident_id,
                state.event_id,
            )

    async def _publish_notification(self, ctx: GraphRunContext[TriageState], result: TriageResult) -> None:
        """Publish notification.send directly to notifications channel (AR10: bypasses Ticket-Service)."""
        state = ctx.state
        payload = _build_notification_payload(state, result)
        has_explanation = bool(result.resolution_explanation)
        try:
            event_id = await ctx.deps.publisher.publish("notifications", "notification.send", payload)
            logger.info(
                "Published notification.send for non-incident %s to notifications "
                "(event_id=%s, published_event_id=%s, confidence=%.2f, has_explanation=%s)",
                state.incident_id,
                state.event_id,
                event_id,
                result.confidence,
                has_explanation,
            )
        except Exception:
            logger.exception(
                "Failed to publish notification.send for incident %s (event_id=%s)",
                state.incident_id,
                state.event_id,
            )

    async def _publish_triage_completed(self, ctx: GraphRunContext[TriageState], result: TriageResult) -> None:
        """Publish triage.completed observability event to incidents channel."""
        state = ctx.state
        duration_ms = 0
        if state.triage_started_at is not None:
            duration_ms = int((time.monotonic() - state.triage_started_at) * 1000)

        payload = _build_triage_completed_payload(state, result, duration_ms)
        try:
            event_id = await ctx.deps.publisher.publish("incidents", "triage.completed", payload)
            logger.info(
                "Published triage.completed for incident %s (event_id=%s, published_event_id=%s, duration_ms=%d)",
                state.incident_id,
                state.event_id,
                event_id,
                duration_ms,
            )
        except Exception:
            logger.exception(
                "Failed to publish triage.completed for incident %s (event_id=%s)",
                state.incident_id,
                state.event_id,
            )
