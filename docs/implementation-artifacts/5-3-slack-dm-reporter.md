# Story 5.3: Slack Direct Message to Reporter

> **Epic:** 5 — Notifications (Notification-Worker — Slack Only)
> **Status:** done
> **Priority:** 🟠 High — Reporter experience
> **Depends on:** Story 5.1 (Worker scaffold), Story 5.2 (Slack client)
> **FRs:** FR22, FR24

## Story

**As a** reporter,
**I want** to receive personalized Slack DMs for every lifecycle event related to my incident,
**So that** I'm always informed without checking any external system.

## Acceptance Criteria

**Given** the Notification-Worker consumes a `notification.send` event with `type: "reporter_update"`
**When** the Slack adapter sends the DM
**Then** the configured reporter receives a Slack DM with the appropriate message:
- **Non-incident resolution:** The technical explanation from the Agent + confidence level
- **Escalation confirmation:** "Your incident has been escalated to engineering. Tracking ID: {incident_id}"
- **Re-escalation confirmation:** "Thanks for the feedback. I've re-analyzed your report and escalated it. Ticket: {link}."

**Given** the notification has `allow_reescalation: true`
**When** the Slack DM is sent for a non-incident resolution
**Then** the message includes a Slack interactive button: "❌ This didn't help — Re-escalate"
**And** when the reporter clicks the button, Slack sends an interaction payload to a configured callback URL

**Given** the Slack interaction callback fires (reporter clicks "This didn't help")
**When** the API receives the Slack interaction webhook at `/api/webhooks/slack`
**Then** the API publishes an `incident.reescalate` event to the `reescalations` Redis channel with the original `incident_id` and reporter feedback
**And** the Slack message is updated to show "🔄 Re-escalation in progress..."

**Given** the Notification-Worker consumes a `notification.send` event with `type: "reporter_resolved"`
**When** the Slack adapter sends the DM
**Then** the reporter receives: "Your reported incident '{title}' has been resolved by the engineering team. 🎉"
**And** the Linear ticket link is included

**Given** the Slack API fails to send a DM
**When** the adapter encounters the error
**Then** it logs a structured error and continues processing other notifications

## Tasks / Subtasks

- [x] **1. Implement reporter_update DM handler**
  - `domain/services.py` — `handle_reporter_update(notification)`
  - Build Slack DM content based on notification message
  - If `allow_reescalation: true`: add interactive "This didn't help" button
  - Send via SlackClient.send_dm(blocks, fallback_text)

- [x] **2. Implement reporter_resolved DM handler**
  - `domain/services.py` — `handle_reporter_resolved(notification)`
  - Build message: "Your reported incident '{title}' has been resolved. 🎉"
  - Include Linear ticket link
  - Send via SlackClient.send_dm(blocks, fallback_text)

- [x] **3. Build Slack interactive button for re-escalation**
  - Block Kit button: "❌ This didn't help — Re-escalate"
  - Button `action_id`: `reescalate_{incident_id}`
  - Slack requires an Interactivity Request URL pointed at the API's `/api/webhooks/slack` endpoint
  - The `incident_id` must be encoded in the button's `value` field

- [x] **4. Handle Slack interaction webhook (API side — Story 2.2)**
  - Updated `POST /api/webhooks/slack` to parse real Slack interactive payloads (form-encoded `payload` field)
  - Parse: extract `incident_id` from button action_id/value
  - Publish `incident.reescalate` event to `reescalations` channel
  - Return HTTP 200 immediately (Slack requires fast response)
  - Responds with `response_url` to update original message to "🔄 Re-escalation in progress..."
  - JSON fallback preserved for testing/internal calls

- [x] **5. DM to reporter uses webhook integration**
  - `SLACK_DM_WEBHOOK_URL` from config (webhook approach, not Bot Token)
  - Separate webhook client for DMs vs team alerts

## Dev Notes

> **Scope note:** This story covers 3 DM types (reporter_update, reporter_resolved, escalation confirmation) plus the interactive re-escalation button. If velocity is constrained, implement reporter_update + button first (core loop), then add reporter_resolved and escalation confirmation as fast-follows.

### Architecture Guardrails
- **Slack DMs via user_id:** `chat.postMessage` with `channel=SLACK_REPORTER_USER_ID` sends a DM. No conversation.open needed for first DM if bot has the right scopes.
- **Interactive messages:** Require Slack app with Interactivity enabled. Request URL must point to the API's webhook endpoint.
- **Re-escalation flow spans multiple services:** Slack button → Slack servers → API `/api/webhooks/slack` → Redis `reescalations` → Agent (Story 3.8).
- **NFR10:** Slack failures logged, not fatal.
- **ER3 — event_id correlation:** Include `event_id` in ALL log entries.
- **AR2 — Redis envelope:** Any published events (e.g., `incident.reescalate` via API) must follow the mandatory envelope format.

### Re-Escalation Button Block Kit
```python
{
    "type": "actions",
    "elements": [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "❌ This didn't help — Re-escalate"},
            "style": "danger",
            "action_id": f"reescalate_{incident_id}",
            "value": incident_id,
        }
    ]
}
```

### Slack App Scopes Required
- `chat:write` — post messages and DMs
- `im:write` — open DM conversations

### Key Reference Files
- Story 5.1: Worker scaffold and routing
- Story 5.2: Slack client adapter (reused here for DMs)
- Story 3.6: Agent publishes non-incident reporter_update notifications
- Story 3.8: Agent handles re-escalation events
- Story 2.2: API /api/webhooks/slack endpoint
- Story 4.3: Ticket-Service publishes reporter_resolved notifications

## File List

- `services/notification-worker/src/config.py` — Added `SLACK_DM_WEBHOOK_URL`
- `services/notification-worker/src/domain/models.py` — Added `allow_reescalation` field
- `services/notification-worker/src/domain/services.py` — Implemented `handle_reporter_update`, `handle_reporter_resolved`, `build_reporter_update_blocks`, `build_reporter_resolved_blocks`
- `services/notification-worker/src/ports/outbound.py` — Added `ReporterNotifier` abstract port
- `services/notification-worker/src/adapters/outbound/slack_client.py` — Added `send_dm()` method with DM webhook client, retry logic
- `services/api/src/adapters/inbound/fastapi_routes.py` — Updated `/api/webhooks/slack` to parse Slack interactive payloads + response_url update
- `tests/test_slack_dm_reporter.py` — 43 tests covering all ACs
- `tests/test_slack_team_notifications.py` — Fixed 1 test for backwards compat (warning assertion)

## Change Log

- 2026-04-08: Implemented all 5 tasks. 43 new tests, 104 total pass. Webhook-based DM approach (`SLACK_DM_WEBHOOK_URL`) instead of Bot Token per user decision.

## Chat Command Log

- Decision: Use `SLACK_DM_WEBHOOK_URL` (Incoming Webhook) for DMs instead of Bot Token `chat.postMessage` — user requested webhook integration approach.
- API webhook endpoint now handles both Slack form-encoded interactive payloads AND JSON fallback for testing.
- `response_url` message update implemented for re-escalation button click feedback.
