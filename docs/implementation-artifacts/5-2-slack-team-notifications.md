# Story 5.2: Slack Team Channel Notifications

> **Epic:** 5 — Notifications (Notification-Worker — Slack Only)
> **Status:** ready-for-dev
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

- [ ] **1. Create SlackClient outbound adapter**
  - `adapters/outbound/slack_client.py`
  - Uses `slack-sdk` Python package
  - Methods: `post_channel_message(blocks)`, `post_dm(user_id, blocks)`
  - Auth: `SLACK_BOT_TOKEN` from config
  - Channel: `SLACK_CHANNEL_ID` from config

- [ ] **2. Implement team alert handler**
  - `domain/services.py` — `handle_team_alert(notification)`
  - Extract: severity, title, component, root_cause, confidence, ticket_url, source_type
  - Build Slack Block Kit message

- [ ] **3. Build Block Kit message format**
  - Header section: severity emoji + title
  - Fields section: component, confidence, source type
  - Text section: root cause summary
  - Action section: "View Ticket" button linking to Linear

- [ ] **4. Implement retry logic**
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

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
