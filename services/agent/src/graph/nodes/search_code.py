from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic_ai import Agent, UsageLimits
from pydantic_ai.settings import ModelSettings
from pydantic_graph import BaseNode, GraphRunContext

from src.domain.models import TriageDeps, TriageResult, TriageState
from src.graph.tools.read_file import read_file
from src.graph.tools.search_code import search_code
from src.llm_circuit_breaker import breaker

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 5 

SEARCH_SYSTEM_PROMPT = """\
You are a code analysis assistant investigating an incident in the eShop (.NET) codebase.
Your goal: find source files relevant to the reported incident.

Strategy:
1. Start by searching for terms from the error messages, component names, or file references.
2. Read promising files to understand the code.
3. Refine your search based on what you learn — search again with better queries.
4. Stop when you have enough code context to understand the probable root cause.

IMPORTANT:
- Make at most 5 search_code calls. After that, summarize what you found and stop.
- If a tool returns an authentication error, STOP immediately — do not retry.
- If searches return no useful results, proceed with what you have.

Return a summary of the relevant code you found, including file paths and key snippets.
"""

def _create_search_agent() -> Agent:
    return Agent(
        breaker.model,
        deps_type=TriageDeps,
        instructions=SEARCH_SYSTEM_PROMPT,
        tools=[search_code, read_file],
    )


def _build_search_prompt(state: TriageState) -> str:
    """Build a prompt for the search agent from extracted signals."""
    parts = [f"**Incident:** {state.signals.get('title', state.incident.get('title', 'Unknown'))}"]

    desc = state.signals.get("description") or state.incident.get("description")
    if desc:
        parts.append(f"**Description:** {desc}")

    component = state.signals.get("component") or state.incident.get("component")
    if component:
        parts.append(f"**Component:** {component}")

    severity = state.signals.get("severity") or state.incident.get("severity")
    if severity:
        parts.append(f"**Severity:** {severity}")

    errors = state.signals.get("error_messages", [])
    if errors:
        parts.append(f"**Error signals:** {', '.join(errors)}")

    traces = state.signals.get("stack_traces", [])
    if traces:
        parts.append(f"**Stack traces:** {'; '.join(traces[:5])}")

    file_refs = state.signals.get("file_references", [])
    if file_refs:
        parts.append(f"**File references:** {', '.join(file_refs[:10])}")

    for att in state.multimodal_content:
        if att["type"] == "text":
            parts.append(f"**Attachment ({att['filename']}):**\n```\n{att['content'][:2000]}\n```")

    parts.append(
        "\nSearch the eShop codebase to find relevant source files. "
        "Use search_code and read_file tools iteratively until you have enough context."
    )

    return "\n\n".join(parts)


@dataclass
class SearchCodeNode(BaseNode[TriageState, TriageDeps, TriageResult]):
    async def run(self, ctx: GraphRunContext[TriageState]) -> ClassifyNode:
        state = ctx.state
        logger.info(
            "SearchCodeNode started for incident %s (event_id=%s)",
            state.incident_id,
            state.event_id,
        )

        prompt = _build_search_prompt(state)
        agent = _create_search_agent()
        try:
            result = await agent.run(
                prompt,
                deps=ctx.deps,
                model_settings=ModelSettings(max_tokens=2048),
                usage_limits=UsageLimits(request_limit=MAX_TOOL_CALLS),
            )
            state.code_context = result.output
            breaker.record_success()
        except Exception:
            breaker.record_failure()
            logger.exception(
                "SearchCodeNode agent run failed for incident %s (event_id=%s); proceeding without code context",
                state.incident_id,
                state.event_id,
            )
            state.code_context = "Code search unavailable — proceeding with incident description only."

        logger.info(
            "SearchCodeNode completed: %d chars of code context (event_id=%s)",
            len(state.code_context),
            state.event_id,
        )

        from src.graph.nodes.classify import ClassifyNode

        return ClassifyNode()
