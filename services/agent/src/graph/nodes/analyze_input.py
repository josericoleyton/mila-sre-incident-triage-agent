from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

from pydantic_graph import BaseNode, GraphRunContext

from src.domain.models import TriageDeps, TriageResult, TriageState

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
TEXT_EXTENSIONS = (".log", ".txt", ".csv", ".json", ".xml", ".yaml", ".yml")

ERROR_PATTERN = re.compile(
    r"(exception|error|traceback|fail|panic|crash|fatal|timeout|refused|denied)",
    re.IGNORECASE,
)
STACK_TRACE_PATTERN = re.compile(
    r"(at\s+[\w.]+\(.*?\)|File\s+\".*?\",\s+line\s+\d+|System\.\w+Exception)",
    re.IGNORECASE,
)
FILE_REF_PATTERN = re.compile(
    r"[\w/\\]+\.\w{1,5}(?::\d+)?",
)


def _extract_signals(incident: dict, attachments: list[dict] | None = None) -> dict:
    """Extract key signals from incident data: error messages, stack traces, file refs.

    Also extracts signals from any processed text attachments (e.g. log files) so that
    precise technical terms in attached logs contribute to the code search.
    """
    text_parts: list[str] = []
    for key in ("title", "description"):
        val = incident.get(key)
        if val:
            text_parts.append(str(val))

    combined = "\n".join(text_parts)

    error_msgs = ERROR_PATTERN.findall(combined)
    stack_traces = STACK_TRACE_PATTERN.findall(combined)
    file_refs = FILE_REF_PATTERN.findall(combined)

    trace_data = incident.get("trace_data") or {}
    if trace_data:
        trace_text = str(trace_data)
        error_msgs.extend(ERROR_PATTERN.findall(trace_text))
        stack_traces.extend(STACK_TRACE_PATTERN.findall(trace_text))
        file_refs.extend(FILE_REF_PATTERN.findall(trace_text))

    if attachments:
        for att in attachments:
            if att.get("type") == "text" and att.get("content"):
                att_text = att["content"]
                error_msgs.extend(ERROR_PATTERN.findall(att_text))
                stack_traces.extend(STACK_TRACE_PATTERN.findall(att_text))
                file_refs.extend(FILE_REF_PATTERN.findall(att_text))

    return {
        "title": incident.get("title", ""),
        "description": incident.get("description", ""),
        "component": incident.get("component", ""),
        "severity": incident.get("severity", ""),
        "error_messages": list(set(error_msgs)),
        "stack_traces": list(set(stack_traces)),
        "file_references": list(set(file_refs)),
    }


MAX_ATTACHMENT_BYTES = 5_000_000 
MAX_TOTAL_BYTES = 20_000_000 


def _process_attachments(incident_id: str, attachment_url: str | None, event_id: str = "") -> list[dict]:
    """Process attachments: images → multimodal input, logs/text → text content."""
    multimodal: list[dict] = []

    root = os.path.realpath("/shared/attachments")
    attachments_dir = os.path.realpath(os.path.join(root, incident_id))
    if not attachments_dir.startswith(root + os.sep):
        logger.warning("Rejected suspicious incident_id for attachments: %s (event_id=%s)", incident_id, event_id)
        return multimodal

    if not os.path.isdir(attachments_dir):
        return multimodal

    total_bytes = 0

    for filename in os.listdir(attachments_dir):
        filepath = os.path.join(attachments_dir, filename)
        if not os.path.isfile(filepath):
            continue

        file_size = os.path.getsize(filepath)
        if file_size > MAX_ATTACHMENT_BYTES:
            logger.warning(
                "Skipping oversized attachment %s (%d bytes, limit %d) (event_id=%s)",
                filename, file_size, MAX_ATTACHMENT_BYTES, event_id,
            )
            continue
        if total_bytes + file_size > MAX_TOTAL_BYTES:
            logger.warning(
                "Reached total attachment size limit (%d bytes), skipping remaining files (event_id=%s)",
                MAX_TOTAL_BYTES, event_id,
            )
            break

        ext = os.path.splitext(filename)[1].lower()

        if ext in IMAGE_EXTENSIONS:
            try:
                import base64

                with open(filepath, "rb") as f:
                    data = base64.b64encode(f.read()).decode("utf-8")
                total_bytes += file_size
                mime = f"image/{ext.lstrip('.')}"
                if ext == ".jpg":
                    mime = "image/jpeg"
                multimodal.append({"type": "image", "mime": mime, "data": data, "filename": filename})
                logger.info("Processed image attachment: %s (event_id=%s)", filename, event_id)
            except Exception:
                logger.exception("Failed to read image attachment %s (event_id=%s)", filename, event_id)
        elif ext in TEXT_EXTENSIONS:
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                total_bytes += file_size
                multimodal.append({"type": "text", "content": content, "filename": filename})
                logger.info("Processed text attachment: %s (event_id=%s)", filename, event_id)
            except Exception:
                logger.exception("Failed to read text attachment %s (event_id=%s)", filename, event_id)

    return multimodal


@dataclass
class AnalyzeInputNode(BaseNode[TriageState, TriageDeps, TriageResult]):
    async def run(self, ctx: GraphRunContext[TriageState]) -> SearchCodeNode:
        state = ctx.state
        logger.info(
            "AnalyzeInputNode started for incident %s (event_id=%s)",
            state.incident_id,
            state.event_id,
        )

        state.multimodal_content = _process_attachments(
            state.incident_id,
            state.incident.get("attachment_url"),
            event_id=state.event_id,
        )

        state.signals = _extract_signals(state.incident, attachments=state.multimodal_content)

        logger.info(
            "AnalyzeInputNode completed: %d error_msgs, %d stack_traces, %d file_refs, %d attachments (event_id=%s)",
            len(state.signals.get("error_messages", [])),
            len(state.signals.get("stack_traces", [])),
            len(state.signals.get("file_references", [])),
            len(state.multimodal_content),
            state.event_id,
        )

        from src.graph.nodes.search_code import SearchCodeNode

        return SearchCodeNode()
