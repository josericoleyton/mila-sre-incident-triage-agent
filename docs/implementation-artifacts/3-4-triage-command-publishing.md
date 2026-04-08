# Story 3.4: Triage Command Publishing — Bug Path

> **Epic:** 3 — AI Triage & Code Analysis (Agent)
> **Status:** ready-for-dev
> **Priority:** 🔴 Critical — Core MVP path
> **Depends on:** Story 3.3b (Classification pipeline + GenerateOutputNode)
> **FRs:** FR13, FR28

## Story

**As a** system,
**I want** the Agent to publish structured ticket creation commands to Redis when a bug is confirmed,
**So that** the Ticket-Service can create the engineering ticket without any LLM dependency.

## Acceptance Criteria

**Given** the triage pipeline classifies an incident as a **bug**
**When** the generate_output node completes
**Then** the Agent publishes a `ticket.create` event to the `ticket-commands` channel with payload:
- `action`: `"create_engineering_ticket"`
- `title`: generated engineering ticket title with severity prefix (e.g., "[P2] NullReferenceException in OrderController.cs")
- `body`: markdown-formatted ticket body containing:
  - 📍 Affected file(s) and line range(s) from triage
  - 🔍 Probable root cause (one sentence)
  - 🛠️ Suggested investigation/fix step
  - 📋 Original report (description + context)
  - 🔗 Incident tracking ID for correlation
  - 📎 Attachment references
  - 🧠 Triage reasoning chain-of-thought summary
  - 📊 Confidence score and severity assessment
- `severity`: mapped from agent's severity_assessment (P1-P4)
- `labels`: relevant labels (component, classification, `triaged-by-mila`)
- `reporter_slack_user_id`: from the incident data (for downstream notification)
- `incident_id`: correlation to original incident

**And** publishes a `triage.completed` event for observability

**Given** any triage completes
**When** the `triage.completed` event is published
**Then** the event payload includes: `incident_id`, `source_type`, `classification`, `confidence`, reasoning summary (metadata, not raw input), severity_assessment, and duration_ms

## Tasks / Subtasks

- [ ] **1. Implement bug path in GenerateOutputNode**
  - In `graph/nodes/generate_output.py`
  - Check: `triage_result.classification == Classification.bug`
  - Build `TicketCommand` payload from `TriageResult` fields

- [ ] **2. Format ticket body (markdown)**
  - Build a markdown string with all sections:
    - `📍 Affected Files:` file_refs with line ranges
    - `🔍 Root Cause:` root_cause field
    - `🛠️ Suggested Fix:` suggested_fix field
    - `📋 Original Report:` incident title + description + component
    - `🔗 Tracking ID:` incident_id
    - `📎 Attachments:` attachment references
    - `🧠 Triage Reasoning:` reasoning summary
    - `📊 Confidence:` confidence score + severity_assessment
  - Include low-confidence indicator if below threshold: `🟡 Low Confidence`

- [ ] **3. Publish ticket.create to ticket-commands channel**
  - Use RedisPublisher from Story 1.2
  - Channel: `ticket-commands`
  - Event type: `ticket.create`
  - Payload: full TicketCommand fields

- [ ] **4. Publish triage.completed observability event**
  - Channel: `incidents` (or a dedicated observability channel)
  - Event type: `triage.completed`
  - Payload: incident_id, source_type, classification, confidence, reasoning_summary (metadata only — no raw user input per NFR5), severity_assessment, forced_escalation (bool), reescalation (bool), duration_ms

- [ ] **5. Track triage duration**
  - Record start time in TriageState when consumer initializes it
  - Calculate `duration_ms` at the end of the pipeline
  - Include in `triage.completed` event

## Dev Notes

### Architecture Guardrails
- **Agent never calls Linear or Slack (AR10):** It ONLY publishes commands to Redis. Ticket-Service and Notification-Worker handle external API calls.
- **Redis envelope (AR2):** All published events follow the mandatory envelope format.
- **Metadata only in observability (NFR5, FR32):** `triage.completed` event must NOT include raw user input text. Only metadata: classification, confidence, severity, file refs, duration.
- **Hexagonal (AR1, AR5):** Publishing done via outbound adapter `redis_publisher.py`, called through port interface.
- **ER3 — event_id correlation:** Propagate the original `event_id` from the incident into ALL log entries and published events.

### Ticket Body Template
```markdown
## 📍 Affected Files
- `src/Ordering.API/Controllers/OrderController.cs` (lines 42-58)
- `src/Ordering.API/Services/OrderService.cs` (lines 110-125)

## 🔍 Root Cause
NullReferenceException when order items collection is empty — missing null check in OrderController.ProcessOrder()

## 🛠️ Suggested Investigation
Add null/empty check for `order.Items` before calling `CalculateTotal()` in OrderController.cs line 45

## 📋 Original Report
**Title:** Checkout 500 errors on empty cart
**Component:** Ordering
**Reporter Severity:** High

## 🔗 Tracking
Incident ID: `{incident_id}`

## 📎 Attachments
- screenshot.png (attached to incident)

## 🧠 Triage Reasoning
Searched for OrderController.cs and found ProcessOrder method. Traced execution path through OrderService.CalculateTotal(). The method assumes non-null Items collection but no guard clause exists. Stack trace in report matches this code path.

## 📊 Assessment
- **Confidence:** 0.87
- **Severity:** P2 — Affects checkout flow but only on edge case (empty cart)
- 🟡 *Low confidence indicator shown when below threshold*
```

### Key Reference Files
- Story 3.3b: Classification pipeline and TriageResult model
- Story 1.2: Redis publisher adapter
- Story 4.2: Ticket-Service consumes this command

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
