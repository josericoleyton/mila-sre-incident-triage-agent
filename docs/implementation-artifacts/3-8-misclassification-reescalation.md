# Story 3.8: Misclassification Re-Escalation Handling

> **Epic:** 3 — AI Triage & Code Analysis (Agent)
> **Status:** ready-for-dev
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

- [ ] **1. Handle reescalation events in consumer**
  - Already wired in Story 3.1 (dual channel subscription)
  - Parse `incident.reescalate` payload: incident_id, original_incident_data, reporter_feedback

- [ ] **2. Re-initialize TriageState with reescalation context**
  - Set `TriageState.reescalation = true`
  - Include reporter feedback as additional context
  - Include original classification result for the LLM to reflect on

- [ ] **3. Force bug classification on re-escalation**
  - In `GenerateOutputNode`: if `state.reescalation == True` → force `Classification.bug`
  - The LLM still runs full analysis but the outcome is forced (trust the human)

- [ ] **4. Enhance ticket body for re-escalated incidents**
  - Add `🔄 Re-escalated` indicator
  - Include original classification and reasoning
  - Include reporter feedback
  - Include new analysis reasoning

- [ ] **5. Publish re-escalation confirmation notification**
  - After ticket.create is published, also publish `notification.send` with:
    - `type: "reporter_update"`
    - `message`: "Thanks for the feedback. I've re-analyzed your report and escalated it to the engineering team."
  - This is published to `notifications` channel for the Notification-Worker

- [ ] **6. Set reescalation flag in triage.completed**
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

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
