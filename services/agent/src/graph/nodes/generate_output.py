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
    if not severity_assessment or not severity_assessment.strip():
        return "P4"
    sa = severity_assessment.lower()
    if "p1" in sa:
        return "P1"
    elif "p2" in sa:
        return "P2"
    elif "p3" in sa:
        return "P3"
    elif "p4" in sa:
        return "P4"
    if "critical" in sa:
        return "P1"
    elif "high" in sa:
        return "P2"
    elif "medium" in sa:
        return "P3"
    else:
        return "P4"


def _map_reporter_severity(reporter_severity: str) -> str:
    """Map free-text reporter severity to P1-P4 for structured comparison."""
    if not reporter_severity or not reporter_severity.strip():
        return "P4"
    rs = reporter_severity.strip().lower()
    if rs in ("p1", "critical", "urgent"):
        return "P1"
    elif rs in ("p2", "high"):
        return "P2"
    elif rs in ("p3", "medium", "moderate"):
        return "P3"
    elif rs in ("p4", "low", "cosmetic"):
        return "P4"
    if "critical" in rs or "urgent" in rs:
        return "P1"
    elif "high" in rs:
        return "P2"
    elif "medium" in rs or "moderate" in rs:
        return "P3"
    else:
        return "P4"


def _sanitize_markdown(text: str) -> str:
    """Strip markdown control characters from untrusted text for safe inline rendering."""
    for ch in ("```", "`", "**", "*", "__", "_", "#", "\n", "\r"):
        text = text.replace(ch, "")
    return text.strip()


def _extract_justification(severity_assessment: str) -> str:
    """Extract a single-sentence justification from the severity assessment text.

    Strips the P-level designation prefix (e.g. 'P2 (High) — ') and returns
    the first sentence of the remaining text.
    """
    text = severity_assessment or ""
    # Take text after the first em-dash or hyphen separator
    if " — " in text:
        text = text.split(" — ", 1)[1].strip()
    elif " - " in text:
        text = text.split(" - ", 1)[1].strip()
    # Take first sentence only
    for sep in (".", ";"):
        if sep in text:
            text = text.split(sep)[0].strip()
            break
    return text


def _format_ticket_body(state: TriageState, result: TriageResult) -> str:
    """Build a markdown-formatted ticket body from triage result and incident data."""
    incident = state.incident
    sections: list[str] = []

    # 1. Re-escalation banner
    if state.reescalation:
        sections.append("## 🔄 Re-escalated — Reporter disagreed with original non-incident classification")
        reesc_lines = []
        if state.original_classification:
            safe_classification = _sanitize_markdown(state.original_classification)
            reesc_lines.append(f"- **Original Classification:** {safe_classification}")
        if state.reporter_feedback:
            safe_feedback = _sanitize_markdown(state.reporter_feedback[:2000])
            reesc_lines.append(f"- **Reporter Feedback:** {safe_feedback}")
        reesc_lines.append("- **Action:** Human override accepted — escalated to engineering")
        sections.append("\n".join(reesc_lines))

    # 2. Proactive Detection banner
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
                safe_error = str(trace_data["error_message"]).replace("```", "'''")
                trace_lines.append(f"- **Error:** `{safe_error}`")
            if trace_lines:
                sections.append("## 📡 OTEL Trace Metadata\n" + "\n".join(trace_lines))

    # 3. Original Report
    title = incident.get("title", "N/A")
    component = incident.get("component", "N/A")
    reporter_severity_display = _sanitize_markdown(str(incident.get("severity", "N/A")))
    description = incident.get("description", "")
    report_lines = [
        f"**Title:** {title}",
        f"**Component:** {component}",
        f"**Reporter Severity:** {reporter_severity_display}",
    ]
    if description:
        report_lines.append(f"\n```\n{description}\n```")
    sections.append("## 📋 Original Report\n" + "\n".join(report_lines))

    # 4. Affected Files
    if result.file_refs:
        file_lines = "\n".join(f"- `{ref}`" for ref in result.file_refs)
        sections.append(f"## 📍 Affected Files\n{file_lines}")
    else:
        sections.append("## 📍 Affected Files\n- _No specific files identified_")

    # 5. Root Cause
    root_cause = result.root_cause or "Unable to determine root cause"
    sections.append(f"## 🔍 Root Cause\n{root_cause}")

    # 6. Suggested Investigation
    suggested_fix = result.suggested_fix or "Further investigation required"
    sections.append(f"## 🛠️ Suggested Investigation\n{suggested_fix}")

    # 7. Triage Reasoning
    sections.append(f"## 🧠 Triage Reasoning\n{result.reasoning}")

    # 8. Severity Assessment (simplified)
    severity_label = _map_severity(result.severity_assessment)
    reporter_severity_raw = incident.get("severity")
    justification = _extract_justification(result.severity_assessment)
    agent_line = f"- **Agent Severity:** {severity_label}"
    if justification:
        agent_line += f" — {justification}"
    severity_lines = [agent_line]
    if reporter_severity_raw and str(reporter_severity_raw).strip():
        safe_reporter = _sanitize_markdown(str(reporter_severity_raw))
        severity_lines.append(f"- **Reporter Indicated:** {safe_reporter}")
        reporter_p_level = _map_reporter_severity(str(reporter_severity_raw))
        if reporter_p_level != severity_label:
            severity_lines.append(
                f"- **Delta:** Agent assessed {severity_label}; reporter indicated {safe_reporter} (mapped to {reporter_p_level})."
            )
    else:
        severity_lines.append("- _No reporter severity provided — assessed purely from code analysis_")
    sections.append("## 📊 Severity Assessment\n" + "\n".join(severity_lines))


    sections.append(f"## 🔗 Tracking\nIncident ID: `{state.incident_id}`")


    attachment_url = incident.get("attachment_url")
    if attachment_url:
        sections.append(f"## 📎 Attachments\n- {attachment_url}")
    elif state.multimodal_content:
        att_lines = "\n".join(f"- {att.get('filename', 'unknown')}" for att in state.multimodal_content)
        sections.append(f"## 📎 Attachments\n{att_lines}")
    else:
        sections.append("## 📎 Attachments\n- _None_")

    return "\n\n".join(sections)


def _generate_ticket_title(result: TriageResult, incident: dict) -> str:
    """Generate a descriptive technical title from triage analysis.

    Format: [Component]: [root cause summary up to 50 chars]
    Truncates at the nearest word boundary to avoid cutting words.
    Falls back to result.reasoning[:50] when root_cause is absent.
    Component is omitted when not available.
    """
    root_cause = result.root_cause
    if root_cause:
        summary = _truncate_at_word_boundary(root_cause, 50)
    elif result.reasoning:
        summary = _truncate_at_word_boundary(result.reasoning, 50)
    else:
        summary = "Untitled incident"
    component = incident.get("component", "")
    if component:
        return f"{component}: {summary}"
    return summary


def _truncate_at_word_boundary(text: str, max_len: int) -> str:
    """Truncate text at a word boundary without exceeding max_len."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    # Cut at last space to avoid splitting a word
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated


def _build_ticket_command(state: TriageState, result: TriageResult) -> dict:
    """Build the ticket.create command payload."""
    incident = state.incident
    severity = _map_severity(result.severity_assessment)
    title = _generate_ticket_title(result, incident)

    labels = ["triaged-by-mila"]
    if state.reescalation:
        labels.append("reescalated")
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
        "reporter_email": incident.get("reporter_email", ""),
        "incident_id": state.incident_id,
        "event_id": state.event_id,
        "component": incident.get("component", ""),
        "source_type": state.source_type,
        "root_cause_summary": (result.root_cause or "")[:300],
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
        "reporter_email": state.incident.get("reporter_email", ""),
        "message": message,
        "incident_id": state.incident_id,
        "allow_reescalation": True,
        "event_id": state.event_id,
    }


def _build_input_summary(state: TriageState) -> dict:
    """Build metadata-only input summary — NO raw user text per NFR5."""
    incident = state.incident
    title = str(incident.get("title", "")) if incident.get("title") is not None else ""
    description = incident.get("description") or ""
    return {
        "title_length": len(title),
        "has_description": bool(description),
        "component": incident.get("component"),
        "severity": incident.get("severity"),
        "has_attachment": bool(incident.get("attachment_url")),
        "source_type": state.source_type,
    }


def _build_triage_completed_payload(state: TriageState, result: TriageResult, duration_ms: int) -> dict:
    """Build triage.completed event payload (metadata only — no raw user input per NFR5)."""
    classification = result.classification.value if hasattr(result.classification, "value") else str(result.classification)
    return {
        "incident_id": state.incident_id,
        "source_type": state.source_type,
        "input_summary": _build_input_summary(state),
        "classification": classification,
        "confidence": result.confidence,
        "reasoning_length": len(result.reasoning) if result.reasoning else 0,
        "reasoning_mentions_files": bool(result.file_refs and result.reasoning and any(ref.split()[0] in result.reasoning for ref in result.file_refs)) if result.reasoning else False,
        "files_examined": list(result.file_refs) if result.file_refs else [],
        "severity_assessment": result.severity_assessment,
        "forced_escalation": state.forced_escalation,
        "reescalation": state.reescalation,
        "event_id": state.event_id,
        "duration_ms": duration_ms,
    }


REESCALATION_CONFIRMATION_MESSAGE = (
    "Thanks for the feedback. I've re-analyzed your report and "
    "escalated it to the engineering team."
)

REESCALATION_FALLBACK_MESSAGE = (
    "Thanks for the feedback. We couldn't fully re-analyze your report, "
    "but we've escalated it to the engineering team."
)


def _build_reescalation_notification_payload(state: TriageState, message: str | None = None) -> dict:
    """Build notification.send payload for re-escalation confirmation to reporter (Story 3.8)."""
    return {
        "type": "reporter_update",
        "reporter_email": state.incident.get("reporter_email", ""),
        "message": message or REESCALATION_CONFIRMATION_MESSAGE,
        "incident_id": state.incident_id,
        "reescalation": True,
        "allow_reescalation": False,
        "event_id": state.event_id,
    }


@dataclass
class GenerateOutputNode(BaseNode[TriageState, TriageDeps, TriageResult]):
    async def run(self, ctx: GraphRunContext[TriageState]) -> End[TriageResult]:
        state = ctx.state
        
        if state.source_type == "systemIntegration":
            state.forced_escalation = True

        if state.triage_result is None:
            logger.error(
                "GenerateOutputNode: no triage_result available for incident %s (event_id=%s)",
                state.incident_id,
                state.event_id,
            )
            
            fallback_classification = Classification.bug if (
                state.source_type == "systemIntegration" or state.reescalation
            ) else Classification.non_incident
            if state.reescalation and not state.original_classification:
                state.original_classification = "unknown \u2014 classification failed"
            fallback = TriageResult(
                classification=fallback_classification,
                confidence=0.0,
                reasoning="Classification failed — no result produced.",
                severity_assessment="unknown — classification failed",
                resolution_explanation=FALLBACK_CLASSIFICATION_FAILED_MESSAGE if (
                    state.source_type == "userIntegration" and not state.reescalation
                ) else None,
            )
            if fallback_classification == Classification.bug:
                await self._publish_ticket_create(ctx, fallback)
                if state.reescalation:
                    await self._publish_reescalation_notification(ctx, message=REESCALATION_FALLBACK_MESSAGE)
            elif state.source_type == "userIntegration":
                await self._publish_notification(ctx, fallback)
            await self._publish_triage_completed(ctx, fallback)
            return End(fallback)

        result = state.triage_result
        
        llm_classification = result.classification.value if hasattr(result.classification, "value") else str(result.classification)
        llm_confidence = result.confidence
        
        if state.source_type == "systemIntegration":
            result.classification = Classification.bug
            logger.info(
                "Story 3.5: Forced classification from %s to bug for proactive incident %s (event_id=%s)",
                llm_classification,
                state.incident_id,
                state.event_id,
            )
            
        if state.reescalation:
            display_classification = llm_classification.replace("_", "-")
            if not state.original_classification:
                state.original_classification = f"{display_classification} (confidence: {llm_confidence:.2f})"
            result.classification = Classification.bug
            reesc_prefix = (
                f"Initial classification was {display_classification} with confidence {llm_confidence:.2f}. "
                f"Reporter disagreed — re-analyzing with escalation bias. "
            )
            
            max_original = 3000 - len(reesc_prefix)
            original_reasoning = result.reasoning[:max_original] if len(result.reasoning) > max_original else result.reasoning
            result.reasoning = reesc_prefix + original_reasoning
            logger.info(
                "Story 3.8: Forced classification from %s to bug for re-escalated incident %s (event_id=%s)",
                llm_classification,
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
            
            if state.reescalation:
                await self._publish_reescalation_notification(ctx)
        elif state.source_type == "userIntegration":
            
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

    async def _publish_reescalation_notification(self, ctx: GraphRunContext[TriageState], message: str | None = None) -> None:
        """Publish re-escalation confirmation notification to reporter (Story 3.8)."""
        state = ctx.state
        payload = _build_reescalation_notification_payload(state, message=message)
        try:
            event_id = await ctx.deps.publisher.publish("notifications", "notification.send", payload)
            logger.info(
                "Published reescalation confirmation for incident %s to notifications "
                "(event_id=%s, published_event_id=%s)",
                state.incident_id,
                state.event_id,
                event_id,
            )
        except Exception:
            logger.exception(
                "Failed to publish reescalation notification for incident %s (event_id=%s)",
                state.incident_id,
                state.event_id,
            )

    async def _publish_triage_completed(self, ctx: GraphRunContext[TriageState], result: TriageResult) -> None:
        """Publish triage.completed observability event to observability channel."""
        state = ctx.state
        duration_ms = 0
        if state.triage_started_at is not None:
            duration_ms = int((time.monotonic() - state.triage_started_at) * 1000)

        payload = _build_triage_completed_payload(state, result, duration_ms)
        try:
            event_id = await ctx.deps.publisher.publish("observability", "triage.completed", payload)
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
