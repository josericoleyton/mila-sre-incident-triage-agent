# Story 3.6: Non-Incident Dismissal with Reporter Notification (userIntegration Only)

> **Epic:** 3 — AI Triage & Code Analysis (Agent)
> **Status:** done
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

- [x] **1. Implement non-incident path in GenerateOutputNode**
  - Check: `triage_result.classification == Classification.non_incident`
  - AND `source_type == "userIntegration"` → publish notification directly
  - AND `source_type == "systemIntegration"` → force bug classification (Story 3.5 logic)

- [x] **2. Build notification payload**
  - `type: "reporter_update"`
  - `slack_user_id`: from incident's `reporter_slack_user_id`
  - `message`: `triage_result.resolution_explanation`
  - `incident_id`: from state
  - `confidence`: from `triage_result.confidence`
  - `allow_reescalation: true`

- [x] **3. Add low-confidence caveat**
  - Read `CONFIDENCE_THRESHOLD` from config (default: 0.75)
  - If confidence < threshold, prepend caveat to message
  - Ensure `allow_reescalation` is always `true` for non-incidents

- [x] **4. Publish directly to notifications channel**
  - **Key difference from bug path:** Agent publishes DIRECTLY to `notifications` channel
  - Bug path: Agent → ticket-commands → Ticket-Service → notifications
  - Non-incident path: Agent → notifications (bypasses Ticket-Service)
  - This is AR10 compliance

- [x] **5. Publish triage.completed observability event**
  - Same pattern as Story 3.4 but with `classification: "non_incident"`

### Review Findings

- [x] [Review][Decision] **D1: CONFIDENCE_THRESHOLD default 0.7 vs spec's 0.75** — Fixed: changed config.py default to 0.75 to align with spec [config.py:8]
- [x] [Review][Decision] **D2: Fallback path (triage_result=None) for userIntegration sends no notification** — Fixed: fallback now publishes notification.send with generic message for userIntegration [generate_output.py:~195-210]
- [x] [Review][Decision] **D3: Message falls back to reasoning when resolution_explanation is absent** — Fixed: kept reasoning fallback but added warning log when falling back [generate_output.py:~160-168]
- [x] [Review][Patch] **P1: Empty message when both resolution_explanation and reasoning are falsy** — Fixed: added fallback message "We determined this is not an incident. If you disagree, please re-escalate." [generate_output.py:~169-170]
- [x] [Review][Patch] **P2: No explicit source_type=="userIntegration" guard before _publish_notification** — Fixed: changed else→elif userIntegration with warning log for unknown source_types [generate_output.py:252-261]
- [x] [Review][Defer] **W1: Fallback + systemIntegration → no ticket.create published** — pre-existing from fallback block design
- [x] [Review][Defer] **W2: Empty slack_user_id propagated to notification** — pre-existing pattern from Story 3.4 _build_ticket_command
- [x] [Review][Defer] **W3: In-place mutation of state.triage_result.classification** — pre-existing from Story 3.5 forced-bug override
- [x] [Review][Defer] **W4: description triple-backtick injection in _format_ticket_body** — pre-existing from Story 3.4
- [x] [Review][Defer] **W5: attachment_url markdown injection** — pre-existing, no sanitization on URL interpolation
- [x] [Review][Defer] **W6: Negative duration_ms if monotonic clock state is stale** — pre-existing edge case

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

## File List

- `services/agent/src/graph/nodes/generate_output.py` — Modified: added `_build_notification_payload()`, `LOW_CONFIDENCE_CAVEAT`, `_publish_notification()` method; replaced Story 3.6 placeholder with actual notification publishing logic
- `tests/test_triage_command_publishing.py` — Modified: added 20 Story 3.6 tests (TestBuildNotificationPayload, TestNonIncidentDismissalPath, TestNonIncidentNotificationResilience, TestNonIncidentTriageCompleted, TestNonIncidentNFR5Compliance)

## Change Log

- 2026-04-08: Implemented Story 3.6 — Non-incident dismissal with reporter notification. Added `_build_notification_payload()` for `notification.send` events, `_publish_notification()` for direct-to-notifications publishing (AR10), low-confidence caveat logic (CONFIDENCE_THRESHOLD), and 20 comprehensive tests covering payload structure, routing, error resilience, NFR5 compliance, and edge cases.
- 2026-04-08: Code review fixes — D1: changed CONFIDENCE_THRESHOLD default to 0.75 (spec alignment). D2: fallback path now sends generic notification for userIntegration. D3: added warning log when falling back to reasoning. P1: empty message guard with fallback text. P2: explicit source_type=="userIntegration" guard with warning for unknown types. Added 13 review fix tests (total: 106 in file).

## Chat Command Log

### Implementation Decisions
- Used existing `CONFIDENCE_THRESHOLD` from config.py (default 0.7) — story mentioned 0.75 but config already had 0.7
- Fallback message uses `result.reasoning` when `resolution_explanation` is None or empty
- `_publish_notification` logs metadata only (confidence, has_explanation) per NFR5 — no raw incident/resolution text in logs
- Non-incident notification published before triage.completed (same ordering as bug path: action first, then observability)
- systemIntegration non-incidents are still handled by Story 3.5 (forced to bug) — no notification published for those
