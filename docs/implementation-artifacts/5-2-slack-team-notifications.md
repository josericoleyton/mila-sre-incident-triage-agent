# Story 5.2: Slack Team Channel Notifications

> **Epic:** 5 — Notifications (Notification-Worker — Slack Only)
> **Status:** done
> **Priority:** 🔴 Critical — Core MVP path
> **Depends on:** Story 5.1 (Worker scaffold)
> **FRs:** FR19

## Story

**As an** SRE team lead,
**I want** the engineering team to receive a Slack channel notification when a new engineering ticket is created,
**So that** the team is alerted immediately and can assign the issue.

## Acceptance Criteria

**Given** the Notification-Worker consumes a `notification.send` event with `type: "team_alert"`
**When** the Slack adapter sends the message
**Then** a formatted message is posted to the configured Slack channel with:
- Severity indicator (emoji prefix: 🔴 P1, 🟠 P2, 🟡 P3, 🔵 P4)
- Incident title
- Affected component
- One-line root cause summary
- Confidence score
- Link to the engineering ticket in Linear
- Source indicator: "👤 User-reported" or "🤖 Proactive OTEL detection"

**Given** the Slack API is unreachable or returns an error
**When** the adapter encounters the failure
**Then** it retries once after 2 seconds
**And** if retry fails, logs a structured error (does not crash, does not block other notifications)

## Tasks / Subtasks

- [x] **1. Create SlackClient outbound adapter**
  - `adapters/outbound/slack_client.py`
  - Uses `slack-sdk` `WebhookClient` (adapted to Incoming Webhooks per user direction)
  - Methods: `send_team_alert(blocks, fallback_text)` — posts via webhook URL
  - Auth: `SLACK_WEBHOOK_URL` from config (replaces BOT_TOKEN + CHANNEL_ID)
  - Port interface: `TeamNotifier` in `ports/outbound.py` (ER8 compliance)

- [x] **2. Implement team alert handler**
  - `domain/services.py` — `handle_team_alert(notification, event_id)`
  - Extract: severity, title, component, root_cause, confidence, ticket_url, source_type
  - Build Slack Block Kit message via `build_team_alert_blocks()`

- [x] **3. Build Block Kit message format**
  - Header section: severity emoji + title
  - Fields section: component, confidence, source type
  - Text section: root cause summary
  - Action section: "View Ticket" button linking to Linear

- [x] **4. Implement retry logic**
  - One retry after 2 seconds on Slack API failure
  - On final failure: log structured error, continue

## Dev Notes

### Architecture Guardrails
- **slack-sdk:** Use the official `slack-sdk` Python package, not `slackclient` (deprecated).
- **Block Kit:** Use rich message formatting for visual clarity in the channel.
- **NFR10:** Slack API failures are logged and do NOT crash the pipeline.
- **ER3 — event_id correlation:** Include `event_id` in ALL log entries.
- **AR2 — Redis envelope:** Incoming `notification.send` events follow the mandatory envelope format — validate before processing.
- **ER8 — ports before adapters:** Define `TeamNotifier` port interface before implementing `SlackClient` adapter.

### Slack Block Kit Example
```python
blocks = [
    {
        "type": "header",
        "text": {"type": "plain_text", "text": "🔴 [P1] NullReferenceException in OrderController.cs"}
    },
    {
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": "*Component:* Ordering"},
            {"type": "mrkdwn", "text": "*Confidence:* 0.87"},
            {"type": "mrkdwn", "text": "*Source:* 👤 User-reported"},
        ]
    },
    {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "*Root Cause:* NullReferenceException when order items collection is empty"}
    },
    {
        "type": "actions",
        "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "View Ticket"}, "url": "https://linear.app/..."}
        ]
    }
]
```

### Key Reference Files
- Story 5.1: Worker scaffold and routing
- Story 4.2: Ticket-Service publishes the team_alert notification event

### Review Findings

- [x] [Review][Patch] Unused import `SlackApiError` — remove dead import [slack_client.py:5]
- [x] [Review][Patch] No warning when `SLACK_WEBHOOK_URL` is empty — add startup log.warning if URL is blank [slack_client.py:init]
- [x] [Review][Patch] Adapter retry/failure logs missing `event_id` — ER3 requires correlation in ALL log entries; pass event_id to `send_team_alert()` [slack_client.py:22-48]
- [x] [Review][Defer] `source_type` is free-form string, not an enum — deferred, pre-existing model pattern

## Dev Agent Record

### Implementation Plan
- **Architecture adaptation:** User requested Incoming Webhooks instead of Bot Token + Channel ID. Used `slack-sdk` `WebhookClient` with `SLACK_WEBHOOK_URL` env var. Block Kit formatting is fully supported via webhooks.
- **ER8 compliance:** Created `TeamNotifier` abstract port in `ports/outbound.py` before implementing `SlackClient` adapter.
- **Model extension:** Added `title` and `source_type` optional fields to `Notification` model for AC compliance.
- **Retry pattern:** 2-attempt loop (1 retry after 2s delay) using `asyncio.to_thread()` for sync `WebhookClient.send()` in async context.
- **ER3 compliance:** All log entries include `event_id` correlation.
- **NFR10 compliance:** Slack failures logged as errors, never crash the pipeline.

### Completion Notes
- ✅ All 4 tasks implemented and tested
- ✅ 33 new tests covering: model fields, Block Kit building (all severity levels, source types, edge cases), adapter retry logic, handler integration, port interface compliance
- ✅ 26 existing scaffold tests pass (zero regressions)
- ✅ Webhook URL configured via `SLACK_WEBHOOK_URL` env var

## File List

- `services/notification-worker/src/ports/outbound.py` — Added `TeamNotifier` abstract port
- `services/notification-worker/src/config.py` — Replaced `SLACK_BOT_TOKEN`/`SLACK_CHANNEL_ID` with `SLACK_WEBHOOK_URL`
- `services/notification-worker/src/domain/models.py` — Added `title` and `source_type` optional fields
- `services/notification-worker/src/adapters/outbound/slack_client.py` — Implemented `SlackClient` adapter with webhook + retry
- `services/notification-worker/src/domain/services.py` — Implemented `handle_team_alert` with Block Kit builder
- `tests/test_slack_team_notifications.py` — 33 tests for story 5.2
- `requirements-test.txt` — Added `slack-sdk`

## Change Log

- **2026-04-08:** Story 5.2 implemented — Slack team channel notifications via Incoming Webhooks with full Block Kit formatting, retry logic, and 33 unit tests.
- **2026-04-08:** Code review patches applied — removed dead import, added empty URL warning, threaded event_id through adapter for ER3 compliance. 2 new tests added (35 total).
