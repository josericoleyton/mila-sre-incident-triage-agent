# Story 3.8: Misclassification Re-Escalation Handling

> **Epic:** 3 — AI Triage & Code Analysis (Agent)
> **Status:** review
> **Priority:** 🟢 Low — Agent intelligence polish (demo impact)
> **Depends on:** Story 3.3b (Classification pipeline), Story 3.4 (Bug path)
> **FRs:** Journey 4 (Lucia — misclassification recovery)

## Story

**As a** reporter,
**I want** to signal that Mila's non-incident classification was wrong so the issue gets re-evaluated and escalated to engineering,
**So that** the system corrects its mistakes transparently and doesn't dead-end my report.

## Acceptance Criteria

**Given** the Agent receives an `incident.reescalate` event on the `reescalations` channel
**When** the event contains the original `incident_id` and reporter feedback
**Then** the Agent:
1. Loads the original incident data from the event payload
2. Re-initializes the triage pipeline with `TriageState.reescalation = true`
3. Includes the reporter's feedback ("This didn't help") as additional context for the LLM
4. Forces the second-pass classification to `bug` (if the reporter says it's wrong, trust the human)
5. Produces a full triage with enhanced reasoning: "Initial classification was non-incident with confidence {X}. Reporter disagreed — re-analyzing with escalation bias."

**Given** the re-escalation triage completes
**When** the Agent publishes commands
**Then** it publishes a `ticket.create` command with:
- Standard bug ticket fields (file refs, root cause, suggested fix)
- A `🔄 Re-escalated` indicator in the ticket body
- Both the original classification reasoning and the re-escalation context
- Reporter's feedback included

**And** publishes `triage.completed` with `reescalation: true` metadata

**Given** the Slack DM to the reporter
**When** the re-escalation is processed
**Then** the reporter receives a follow-up Slack DM: "Thanks for the feedback. I've re-analyzed your report and escalated it to the engineering team. Ticket: {link}."

## Tasks / Subtasks

- [x] **1. Handle reescalation events in consumer**
  - Already wired in Story 3.1 (dual channel subscription)
  - Parse `incident.reescalate` payload: incident_id, original_incident_data, reporter_feedback

- [x] **2. Re-initialize TriageState with reescalation context**
  - Set `TriageState.reescalation = true`
  - Include reporter feedback as additional context
  - Include original classification result for the LLM to reflect on

- [x] **3. Force bug classification on re-escalation**
  - In `GenerateOutputNode`: if `state.reescalation == True` → force `Classification.bug`
  - The LLM still runs full analysis but the outcome is forced (trust the human)

- [x] **4. Enhance ticket body for re-escalated incidents**
  - Add `🔄 Re-escalated` indicator
  - Include original classification and reasoning
  - Include reporter feedback
  - Include new analysis reasoning

- [x] **5. Publish re-escalation confirmation notification**
  - After ticket.create is published, also publish `notification.send` with:
    - `type: "reporter_update"`
    - `message`: "Thanks for the feedback. I've re-analyzed your report and escalated it to the engineering team."
  - This is published to `notifications` channel for the Notification-Worker

- [x] **6. Set reescalation flag in triage.completed**
  - `reescalation: true` in the observability event payload

## Dev Notes

### Architecture Guardrails
- **Re-escalation = human override:** When the reporter says the classification was wrong, the agent ALWAYS creates a ticket. No second dismissal.
- **Full pipeline still runs:** The LLM re-analyzes with the new context. This adds value (better reasoning, file refs for the re-escalated ticket).
- **AR10 routing:** Re-escalation follows the bug path: Agent → ticket-commands → Ticket-Service → notifications. Plus an additional reporter confirmation notification.
- **Demo impact:** Shows self-correcting agent behavior, human-in-the-loop design, transparent reasoning.
- **ER3 — event_id correlation:** Include `event_id` in ALL log entries.
- **AR2 — Redis envelope:** All published events (`ticket.create`, `notification.send`) must follow the mandatory envelope format.
- **NFR5 — metadata-only logging:** Do NOT log raw re-escalation feedback text. Only metadata.

### Re-Escalation Event Flow
```
1. Reporter clicks "This didn't help" in Slack DM (Story 5.3)
2. Slack sends interaction webhook → API /api/webhooks/slack (Story 2.2)
3. API publishes incident.reescalate to reescalations channel
4. Agent consumes reescalation event (Story 3.1)
5. Agent re-runs triage with forced bug classification (this story)
6. Agent publishes ticket.create + notification.send
7. Ticket-Service creates ticket + Notification-Worker sends confirmation
```

### Key Reference Files
- Story 3.1: Dual channel subscription (incidents + reescalations)
- Story 3.4: Bug path publishing (re-escalation follows same path with extra context)
- Story 5.3: Slack re-escalation button and interaction callback
- Story 2.2: API /api/webhooks/slack endpoint

### Review Findings

#### Decision Needed (Resolved)
- [x] [Review][Decision] **D1 — Slack DM missing `Ticket: {link}` per spec AC3** — Resolved: `incident_id` already in payload; Notification-Worker enriches downstream.
- [x] [Review][Decision] **D2 — 1000-char reasoning cap vs "full triage" language** — Resolved: increased cap to 3000.
- [x] [Review][Decision] **D3 — `original_classification` always "" at classify time** — Resolved: added `original_classification` to IncidentEvent + extracted in handler.

#### Patches (Applied)
- [x] [Review][Patch] **P1 — Newline injection in reporter_feedback prompt** — Fixed: strip `\n` and `\r` in `_build_reescalation_context`. [classify.py:28]
- [x] [Review][Patch] **P2 — systemIntegration + reescalation: original_classification recorded as "bug"** — Fixed: capture LLM classification before any force overrides. [generate_output.py:330]
- [x] [Review][Patch] **P3 — Fallback path: `original_classification` stays ""** — Fixed: set to "unknown — classification failed" when not already populated. [generate_output.py:308]
- [x] [Review][Patch] **P4 — `original_classification` not sanitized in ticket body** — Fixed: apply `_sanitize_markdown` before rendering. [generate_output.py:84]
- [x] [Review][Patch] **P5 — reporter_feedback unbounded in ticket body** — Fixed: truncate to 2000 chars before sanitize. [generate_output.py:87]
- [x] [Review][Patch] **P6 — Reasoning prefix uses underscore `non_incident` vs spec's `non-incident`** — Fixed: `replace("_", "-")` on display classification. [generate_output.py:348]
- [x] [Review][Patch] **P7 — Fallback reescalation sends success notification despite no analysis** — Fixed: separate fallback message "couldn't fully re-analyze". [generate_output.py:320]

#### Deferred
- [x] [Review][Defer] **W1 — Empty `slack_user_id` fallback on notification** [blind] — deferred, pre-existing

## Chat Command Log

### Dev Agent Record — Implementation (2026-04-08)

**Implementation Plan:**
- Added `reporter_feedback` optional field to `IncidentEvent` model
- Added `reporter_feedback` and `original_classification` fields to `TriageState`
- Updated `handle_reescalation_event` to extract and propagate reporter feedback
- Enhanced `_build_classify_prompt` to include reporter feedback, original classification, and escalation bias instruction for re-escalation context
- Added forced bug classification in `GenerateOutputNode.run()` for re-escalated incidents (mirrors Story 3.5 pattern for systemIntegration)
- Enhanced `_format_ticket_body` with re-escalation banner showing original classification, reporter feedback, and human override action
- Added `_build_reescalation_notification_payload` function and `_publish_reescalation_notification` method
- Updated routing logic: re-escalation publishes 3 events (ticket.create → notification.send → triage.completed)
- Fallback path also forces bug and publishes all 3 events for re-escalation

**Completion Notes:**
- 37 new tests in `test_misclassification_reescalation.py` — all passing
- 341/342 total tests pass (1 pre-existing failure in test_ui_nginx.py unrelated to this story)
- All 6 acceptance criteria satisfied
- NFR5 respected: reporter feedback sanitized via `_sanitize_markdown` before rendering in ticket body
- AR2: All published events use the Redis envelope format via `RedisPublisher.publish()`
- ER3: All log entries include `event_id`

**File List:**
- `services/agent/src/domain/models.py` — added `reporter_feedback` to IncidentEvent, `reporter_feedback` + `original_classification` to TriageState
- `services/agent/src/domain/triage_handler.py` — updated `handle_reescalation_event` to extract reporter_feedback
- `services/agent/src/graph/nodes/classify.py` — enhanced `_build_classify_prompt` with reescalation context
- `services/agent/src/graph/nodes/generate_output.py` — forced bug classification, re-escalation ticket body, re-escalation notification, fallback path
- `tests/test_misclassification_reescalation.py` — 37 new tests covering all 6 tasks

**Change Log:**
- Story 3.8 implemented: Misclassification re-escalation handling (Date: 2026-04-08)
