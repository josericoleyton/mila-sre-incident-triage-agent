# Story 3.5: Proactive Incident Processing (systemIntegration — Always Escalate)

> **Epic:** 3 — AI Triage & Code Analysis (Agent)
> **Status:** done
> **Priority:** 🟠 High — OTEL differentiator
> **Depends on:** Story 3.4 (Bug path publishing)
> **FRs:** FR25

## Story

**As a** system,
**I want** the Agent to always escalate proactive incidents from OTEL telemetry without the option to dismiss them,
**So that** telemetry-backed signals are never lost and always result in engineering tickets.

## Acceptance Criteria

**Given** the Agent is processing an incident with `source_type: "systemIntegration"`
**When** the triage pipeline runs
**Then** the classification step still performs full code analysis and reasoning (for triage quality)
**But** the final classification is always forced to `bug` regardless of the LLM's assessment
**And** the agent still produces confidence, reasoning, file_refs, root_cause, and suggested_fix normally
**And** a `ticket.create` command is published to `ticket-commands` with the full triage details
**And** the `triage.completed` event includes `"forced_escalation": true` and `source_type: "systemIntegration"`

**Given** a proactive incident from OTEL
**When** the agent formats the ticket body
**Then** the ticket includes a clear indicator: "🤖 Proactive Detection — This incident was auto-detected from production telemetry (not user-reported)"
**And** the OTEL trace metadata (service name, trace ID, status code, error message) is prominently displayed

## Tasks / Subtasks

- [ ] **1. Add source_type conditional in GenerateOutputNode**
  - In `graph/nodes/generate_output.py`
  - Check: if `state.source_type == "systemIntegration"` → force classification to `bug`
  - The LLM still runs its full analysis — only the final decision is overridden

- [ ] **2. Add forced_escalation indicator to ticket body**
  - Prepend "🤖 Proactive Detection" banner to the ticket body
  - Include OTEL metadata prominently: service_name, trace_id, status_code, error_message

- [ ] **3. Set forced_escalation in triage.completed event**
  - Add `forced_escalation: true` to the observability event payload
  - Add `source_type: "systemIntegration"` for filtering

- [ ] **4. Skip reporter notification for proactive incidents**
  - `reporter_slack_user_id` is null for systemIntegration events
  - Ensure the ticket command reflects this (Ticket-Service won't send reporter DM)

### Review Findings (2026-04-08)

- [x] [Review][Decision] **AC5 — Banner text deviates from spec** — resolved as hybrid: full spec text as heading
- [x] [Review][Patch] **Incomplete markdown sanitization of trace_data fields** [generate_output.py:43-50] — sanitized all fields; triple backticks replaced
- [x] [Review][Patch] **trace_data not validated as dict** [generate_output.py:39] — added isinstance check
- [x] [Review][Patch] **status_code=0 falsy edge case** [generate_output.py:46] — changed to `is not None` check
- [x] [Review][Patch] **Fallback path: forced_escalation not set for systemIntegration** [generate_output.py:172] — moved forced_escalation set before fallback; fallback classification also forced to bug
- [x] [Review][Patch] **Original LLM classification lost to observability** [generate_output.py:178] — now logs original before override
- [x] [Review][Patch] **Unicode escapes instead of literal emoji** [generate_output.py:36,51] — replaced with literal emoji
- [x] [Review][Defer] **"systemIntegration" string literal duplicated** — deferred, pre-existing pattern
- [x] [Review][Defer] **In-place state/result mutation in graph nodes** — deferred, pre-existing architecture

## Dev Notes

### Architecture Guardrails
- **Agent intelligence demo:** The agent still performs full analysis even when escalation is forced. This shows the agent adding value (root cause, file refs, suggested fix) even for auto-detected issues.
- **No reporter notification:** Proactive incidents have no reporter (`reporter_slack_user_id = null`). Only team Slack channel gets the alert.
- **AR10 compliance:** Agent only publishes commands — never calls Linear/Slack directly.
- **ER3 — event_id correlation:** Include `event_id` in ALL log entries.
- **AR2 — Redis envelope:** Published `ticket.create` events must follow the mandatory envelope format.
- **NFR5 — metadata-only logging:** Do NOT log raw incident text in observability traces. Only metadata (component, severity, title_length).

### Implementation Pattern
```python
# In generate_output.py
if state.source_type == "systemIntegration":
    # Force bug classification regardless of LLM output
    state.triage_result.classification = Classification.bug
    state.forced_escalation = True
    # Prepend proactive detection banner to ticket body
```

### Key Reference Files
- Story 3.4: Bug path publishing (this story adds the forced-escalation variant)
- Story 2.2: OTEL webhook endpoint that creates systemIntegration incidents
- Story 6.3: OTEL Collector configuration

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
