from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic_ai import Agent, ModelHTTPError
from pydantic_ai.settings import ModelSettings
from pydantic_graph import BaseNode, GraphRunContext

from src.domain.context.context_loader import load_eshop_context
from src.domain.models import TriageDeps, TriageResult, TriageState
from src.graph.tools.read_file import read_file, read_file_section
from src.graph.tools.search_code import search_code
from src.llm_circuit_breaker import breaker

logger = logging.getLogger(__name__)

SEARCH_SYSTEM_PROMPT = """\
You are an expert .NET SRE code investigator. Your job is to find and read the EXACT source files
in the eShop codebase that are relevant to a reported incident, then produce a precise code analysis.

{eshop_context}

## Investigation Strategy

Follow this disciplined approach — do NOT skip steps:

### Step 1: Identify Target Files from the Codebase Map
Use the Component-to-File Quick Reference table above. Map the incident's component, error messages,
and stack traces to specific file paths. This is your starting point — NOT a blind search.

### Step 2: Read the Primary Files Directly
If you already know the file path from the codebase map (e.g., the incident says "Catalog" →
read `src/Catalog.API/Apis/CatalogApi.cs`), use read_file FIRST. Only search if you don't know
which file to look at.

### Step 3: Search for Specific Symbols
When searching, use PRECISE terms — class names, method names, exception types, or error message
fragments. Good searches:
- `NullReferenceException CatalogBrand` (specific exception + context)
- `Task.Delay BasketService` (suspicious pattern + file)
- `AddAndSaveEventAsync OrderStarted` (specific method + event)
- `ValidateOrAddBuyerAggregate` (exact handler class name)
Bad searches:
- `error` (too generic)
- `bug in catalog` (natural language, won't match code)
- `order processing issue` (not how code is written)

### Step 4: Read Related Files
After reading the primary file, follow the dependency chain:
- If a handler calls `_orderingIntegrationEventService.AddAndSaveEventAsync()`, check how that's wired
- If an API endpoint calls a repository, check the repository implementation
- If a domain event is raised, check its handler in `DomainEventHandlers/`

### Step 5: Produce a Structured Analysis

IMPORTANT CONSTRAINTS:
- Make at most 5 search_code calls and at most 5 read_file calls.
- If a tool returns an authentication error, STOP immediately — do not retry.
- If you already know the file path, use read_file directly instead of searching.
- Focus on finding the ROOT CAUSE, not just any related code.

## Required Output Format

Your output MUST follow this exact structure:

### Files Analyzed
- `<file_path>`: <one-line description of what this file does>

### Relevant Code Findings
For each finding, include:
1. **File**: exact path
2. **Location**: class/method name
3. **Code snippet**: the relevant lines (keep to ~20 lines max)
4. **Observation**: what this code does and why it's relevant to the incident

### Suspected Root Cause
Based on the code you read, what is the most likely technical root cause?
Include the specific file, method, and line-level detail.

### Impact Assessment
What downstream effects does this code issue have on the system?
"""


def _create_search_agent() -> Agent:
    eshop_context = load_eshop_context()
    prompt = SEARCH_SYSTEM_PROMPT.format(eshop_context=eshop_context)
    return Agent(
        breaker.model,
        deps_type=TriageDeps,
        instructions=prompt,
        tools=[search_code, read_file, read_file_section],
    )


def _build_search_prompt(state: TriageState) -> str:
    """Build a structured investigation prompt from extracted signals."""
    parts = ["## Incident Under Investigation"]
    parts.append(f"**Title:** {state.signals.get('title', state.incident.get('title', 'Unknown'))}")

    desc = state.signals.get("description") or state.incident.get("description")
    if desc:
        parts.append(f"**Description:** {desc}")

    component = state.signals.get("component") or state.incident.get("component")
    if component:
        parts.append(f"**Component:** {component}")
        parts.append(f"\n> Hint: Use the Component-to-File Quick Reference table in your instructions to identify which files to read FIRST for '{component}'.")

    severity = state.signals.get("severity") or state.incident.get("severity")
    if severity:
        parts.append(f"**Severity:** {severity}")

    errors = state.signals.get("error_messages", [])
    if errors:
        parts.append("**Error messages (search for these exact strings):**")
        for err in errors:
            parts.append(f"  - `{err}`")

    traces = state.signals.get("stack_traces", [])
    if traces:
        parts.append("**Stack traces (extract class/method names for search):**")
        for trace in traces[:5]:
            parts.append(f"  ```\n  {trace}\n  ```")

    file_refs = state.signals.get("file_references", [])
    if file_refs:
        parts.append("**File references (read these directly with read_file):**")
        for ref in file_refs[:10]:
            parts.append(f"  - `{ref}`")

    for att in state.multimodal_content:
        if att["type"] == "text":
            parts.append(f"**Attachment ({att['filename']}):**\n```\n{att['content'][:2000]}\n```")

    parts.append("\n## Your Task")
    parts.append("Investigate this incident using the strategy in your instructions. "
                 "Start by mapping the component to specific files, read them, and produce your structured analysis.")

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
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                result = await agent.run(
                    prompt,
                    deps=ctx.deps,
                    model_settings=ModelSettings(max_tokens=4096),
                )
                state.code_context = result.output
                breaker.record_success()
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                is_rate_limit = isinstance(exc, ModelHTTPError) and exc.status_code == 429
                if is_rate_limit and attempt < 2:
                    delay = 2 ** attempt
                    logger.warning(
                        "SearchCodeNode attempt %d/3 rate-limited (429), retrying in %ds (event_id=%s)",
                        attempt + 1,
                        delay,
                        state.event_id,
                    )
                    await __import__("asyncio").sleep(delay)
                else:
                    if not is_rate_limit:
                        breaker.record_failure()
                    logger.exception(
                        "SearchCodeNode agent run failed for incident %s (event_id=%s); proceeding without code context",
                        state.incident_id,
                        state.event_id,
                    )
                    break

        if last_error is not None:
            state.code_context = "Code search unavailable — proceeding with incident description only."

        logger.info(
            "SearchCodeNode completed: %d chars of code context (event_id=%s)",
            len(state.code_context),
            state.event_id,
        )

        from src.graph.nodes.classify import ClassifyNode

        return ClassifyNode()
