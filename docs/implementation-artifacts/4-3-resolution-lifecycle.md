# Story 4.3: Resolution Lifecycle — Linear Webhook to Reporter Notification

> **Epic:** 4 — Ticket Lifecycle Management (Ticket-Service)
> **Status:** done
> **Priority:** 🟡 Medium — Resolution notification path
> **Depends on:** Story 4.1 (Webhook listener), Story 4.2 (Ticket-incident mapping)
> **FRs:** FR23, FR24

## Story

**As a** reporter,
**I want** to be automatically notified via Slack when an engineer resolves the bug I reported,
**So that** I know my issue is fixed without checking ticket status.

## Acceptance Criteria

**Given** an engineer marks an engineering ticket as "Done" or "Resolved" in Linear
**When** Linear fires a webhook to `POST /webhooks/linear` on the Ticket-Service
**Then** the Ticket-Service:
1. Verifies the webhook HMAC signature
2. Extracts the incident_id from the ticket body or metadata
3. Publishes a `notification.send` event with `type: "reporter_resolved"` containing:
   - `slack_user_id`: the reporter's Slack user ID (extracted from ticket metadata)
   - `message`: "Your reported incident '{title}' has been resolved by the engineering team."
   - `incident_id`: for correlation
   - `ticket_url`: link to the resolved Linear ticket

**Given** the webhook arrives for a non-tracked ticket or a duplicate resolution
**When** the Ticket-Service processes it
**Then** it ignores the webhook and logs an informational entry (no duplicate notifications)

## Tasks / Subtasks

- [x] **1. Implement resolution webhook handler**
  - In `adapters/inbound/webhook_listener.py`
  - Parse Linear webhook payload for issue state changes
  - Detect "Done" or "Resolved" status transitions
  - Linear webhook type: `Issue` with `action: "update"` and `data.state.name` change

- [x] **2. Correlate ticket to incident**
  - Look up incident_id and reporter_slack_user_id from the ticket-incident mapping (Story 4.2)
  - Options: parse from Linear ticket body (embedded in markdown), or Redis hash lookup
  - If no mapping found → log info and skip (non-tracked ticket)

- [x] **3. Publish reporter_resolved notification**
  - `notification.send` event to `notifications` channel
  - `type: "reporter_resolved"`
  - Include: slack_user_id, message, incident_id, ticket_url
  - Only if reporter_slack_user_id is not null (proactive incidents have no reporter)

- [x] **4. Handle edge cases**
  - Duplicate resolution webhooks (Linear may fire multiple times): idempotency check
  - Non-tracked tickets (created outside mila): ignore gracefully
  - Missing reporter (proactive incidents): skip notification, log info

## Dev Notes

### Architecture Guardrails
- **No Agent involvement:** This is a deterministic pipeline — no LLM needed. Linear webhook → Ticket-Service → Notification.
- **HMAC verification:** Already implemented in Story 4.1. Resolution handler reuses the verified webhook flow.
- **No polling (real-time):** Linear webhooks provide real-time notification. Never poll Linear API.
- **Hexagonal (AR1, AR5):** Webhook parsing in inbound adapter, business logic in domain, notification publishing via outbound adapter.
- **ER3 — event_id correlation:** Generate a new `event_id` for the resolution flow and include it in ALL log entries.
- **AR2 — Redis envelope:** Published `notification.send` events must follow the mandatory envelope format.

### Linear Webhook Payload (Issue Update)
```json
{
  "action": "update",
  "type": "Issue",
  "data": {
    "id": "issue-uuid",
    "identifier": "ENG-42",
    "title": "[P2] NullReferenceException in OrderController.cs",
    "state": { "name": "Done", "type": "completed" },
    "url": "https://linear.app/team/issue/ENG-42",
    "description": "...markdown body with incident_id embedded..."
  },
  "updatedFrom": {
    "state": { "name": "In Progress", "type": "started" }
  }
}
```

### Key Reference Files
- Story 4.1: Webhook listener scaffold and HMAC verification
- Story 4.2: Ticket-incident mapping (needed to correlate back)
- Story 5.3: Notification-Worker delivers the Slack DM for reporter_resolved

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*

### Implementation Decisions

- **Ticket-incident correlation via Redis hashes**: Added `TicketMappingStore` port and `RedisTicketMappingStore` adapter using Redis hashes (`ticket-mapping:{linear_ticket_id}`) for O(1) lookup during resolution webhooks.
- **Idempotency via Redis set**: `resolved-tickets` set tracks already-resolved ticket IDs. `mark_resolved` returns False on duplicates, preventing duplicate notifications.
- **Backward-compatible `create_app()`**: `mapping_store` and `publisher` are optional parameters. Existing tests and callers without these deps still work.
- **`create_engineering_ticket` stores mapping**: The mapping store is called during ticket creation (optional param, backward-compatible with Story 4.2 tests).
- **Empty reporter string treated as no reporter**: Consistent with Redis hash storage where None is stored as empty string.

### File List

| Action   | File                                                    |
|----------|---------------------------------------------------------|
| Created  | services/ticket-service/src/ports/ticket_mapping.py     |
| Created  | services/ticket-service/src/adapters/outbound/redis_ticket_mapping.py |
| Created  | tests/test_resolution_lifecycle.py                      |
| Modified | services/ticket-service/src/domain/services.py          |
| Modified | services/ticket-service/src/adapters/inbound/webhook_listener.py |
| Modified | services/ticket-service/src/main.py                     |

### Change Log

- 2026-04-08: Story 4.3 implemented — resolution lifecycle with webhook handler, ticket-incident correlation, reporter notification, idempotency, and edge case handling. 20 tests added, all passing. No regressions in ticket-service tests (69/69 pass).
