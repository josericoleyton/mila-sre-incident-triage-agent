# Story 3.6: Non-Incident Dismissal with Reporter Notification (userIntegration Only)

> **Epic:** 3 — AI Triage & Code Analysis (Agent)
> **Status:** ready-for-dev
> **Priority:** 🟡 Medium — Edge case handling
> **Depends on:** Story 3.3b (Classification pipeline + GenerateOutputNode)
> **FRs:** FR20, FR21

## Story

**As a** reporter,
**I want** to receive a specific technical explanation via Slack when Mila determines my report is not an incident,
**So that** I understand why without needing to chase anyone.

## Acceptance Criteria

**Given** the triage pipeline classifies an incident as a **non-incident**
**And** the `source_type` is `"userIntegration"`
**When** the generate_output node completes
**Then** the Agent publishes a `notification.send` event directly to the `notifications` channel (NOT through Ticket Service) with:
- `type`: `"reporter_update"`
- `slack_user_id`: from the incident's `reporter_slack_user_id`
- `message`: the specific technical resolution explanation from TriageResult (e.g., "This is expected behavior during the scheduled cache rebuild. Latency normalizes within 10 minutes. See `CatalogApi/Startup.cs` cache configuration.")
- `incident_id`: for correlation
- `confidence`: included so the notification can display the agent's certainty level
- `allow_reescalation`: `true` (enables the "This didn't help" mechanism in the Slack message)

**Given** the agent classifies a non-incident with low confidence (below threshold)
**When** the notification is constructed
**Then** the message includes a caveat: "I'm less certain about this classification. If this doesn't match what you're seeing, please re-escalate."
**And** `allow_reescalation` is set to `true`

**Given** `source_type` is `"systemIntegration"`
**When** classification results in non-incident
**Then** the agent ignores the non-incident classification and forces escalation per Story 3.5

## Tasks / Subtasks

- [ ] **1. Implement non-incident path in GenerateOutputNode**
  - Check: `triage_result.classification == Classification.non_incident`
  - AND `source_type == "userIntegration"` → publish notification directly
  - AND `source_type == "systemIntegration"` → force bug classification (Story 3.5 logic)

- [ ] **2. Build notification payload**
  - `type: "reporter_update"`
  - `slack_user_id`: from incident's `reporter_slack_user_id`
  - `message`: `triage_result.resolution_explanation`
  - `incident_id`: from state
  - `confidence`: from `triage_result.confidence`
  - `allow_reescalation: true`

- [ ] **3. Add low-confidence caveat**
  - Read `CONFIDENCE_THRESHOLD` from config (default: 0.75)
  - If confidence < threshold, prepend caveat to message
  - Ensure `allow_reescalation` is always `true` for non-incidents

- [ ] **4. Publish directly to notifications channel**
  - **Key difference from bug path:** Agent publishes DIRECTLY to `notifications` channel
  - Bug path: Agent → ticket-commands → Ticket-Service → notifications
  - Non-incident path: Agent → notifications (bypasses Ticket-Service)
  - This is AR10 compliance

- [ ] **5. Publish triage.completed observability event**
  - Same pattern as Story 3.4 but with `classification: "non_incident"`

## Dev Notes

### Architecture Guardrails
- **AR10 — Critical routing difference:**
  - Bug path: Agent → `ticket-commands` channel → Ticket-Service creates ticket → Ticket-Service publishes to `notifications`
  - Non-incident path: Agent → `notifications` channel DIRECTLY (bypasses Ticket-Service entirely)
  - No Linear ticket for non-incidents.
- **Agent never calls Slack directly:** It publishes a `notification.send` event — Notification-Worker handles Slack delivery.
- **Confidence threshold (config):** `CONFIDENCE_THRESHOLD` env var, default 0.75. Low confidence adds caveat text.
- **ER3 — event_id correlation:** Include `event_id` in ALL log entries.
- **AR2 — Redis envelope:** Published `notification.send` events must follow the mandatory envelope format.
- **NFR5 — metadata-only logging:** Do NOT log raw incident/resolution text. Log only metadata (classification, confidence, has_explanation).

### Key Reference Files
- Story 3.3b: Classification pipeline producing TriageResult
- Story 3.5: systemIntegration override (forces bug even if LLM says non-incident)
- Story 5.3: Notification-Worker delivers the Slack DM + re-escalation button
- Story 3.8: Re-escalation handling when reporter disagrees

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
