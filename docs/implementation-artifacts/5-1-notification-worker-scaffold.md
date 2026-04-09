# Story 5.1: Notification-Worker Scaffold with Redis Consumer

> **Epic:** 5 — Notifications (Notification-Worker — Slack Only)
> **Status:** done
> **Priority:** 🔴 Critical — Core MVP path
> **Depends on:** Story 1.2 (Redis infrastructure)
> **FRs:** FR19, FR22, FR24

## Story

**As a** system,
**I want** the Notification-Worker to consume notification events from Redis and route them to the appropriate Slack delivery method,
**So that** all outbound messaging flows through a single service.

## Acceptance Criteria

**Given** the Notification-Worker is running and connected to Redis
**When** a `notification.send` event is published to the `notifications` channel
**Then** the worker consumes it within 5 seconds
**And** deserializes the payload into a `Notification` domain model
**And** routes to the correct handler based on notification `type`:
- `team_alert` → Slack channel message
- `reporter_update` → Slack DM to reporter (non-incident, escalation confirmation)
- `reporter_resolved` → Slack DM to reporter (bug fixed)

**Given** the worker receives a notification with an unknown type
**When** routing fails
**Then** it logs a structured warning and skips the notification (no crash)

## Tasks / Subtasks

- [x] **1. Wire Redis consumer in main.py**
  - Start async listener loop on `notifications` channel
  - Use `redis.asyncio` pub/sub
  - On each message: validate envelope → deserialize → route to handler

- [x] **2. Implement notification routing**
  - `domain/services.py` — route by `notification.type`:
    - `team_alert` → call team channel handler
    - `reporter_update` → call DM handler
    - `reporter_resolved` → call DM handler
  - Unknown types → log warning, skip

- [x] **3. Create handler stubs**
  - `handle_team_alert(notification)` — Story 5.2 implements
  - `handle_reporter_update(notification)` — Story 5.3 implements
  - `handle_reporter_resolved(notification)` — Story 5.3 implements
  - For now, log: "Notification type={type} for incident={incident_id} — handler not yet implemented"

- [x] **4. Error handling**
  - Malformed events: log warning, skip, continue
  - Handler errors: log error, continue (never crash the consumer loop)

## Dev Notes

### Architecture Guardrails
- **Single notification channel:** All notification types flow through `notifications` Redis channel to this single worker.
- **Hexagonal (AR1, AR5):** Redis consumer in `adapters/inbound/redis_consumer.py`. Domain routing in `domain/services.py`. Slack client in `adapters/outbound/slack_client.py`.
- **Config only (AR3):** `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `REDIS_URL` from `config.py`.
- **No email/Resend anywhere.** Slack is the only notification mechanism.
- **ER3 — event_id correlation:** Extract `event_id` from incoming Redis envelope and include it in ALL log entries.

### Notification Types
| Type | Source | Destination | Content |
|---|---|---|---|
| `team_alert` | Ticket-Service | Slack channel | New ticket alert + link |
| `reporter_update` | Agent (non-incident) or Ticket-Service (escalation) | Slack DM | Resolution/confirmation |
| `reporter_resolved` | Ticket-Service (Linear webhook) | Slack DM | Bug resolved notification |

### Key Reference Files
- Story 1.2: Redis consumer adapter pattern
- Story 5.2: Team channel notification implementation
- Story 5.3: DM implementation

## File List

- `services/notification-worker/src/main.py` — Modified: wired Redis consumer, on_notification callback
- `services/notification-worker/src/domain/models.py` — Modified: updated Notification model for all notification types
- `services/notification-worker/src/domain/services.py` — New: route_notification + handler stubs
- `tests/test_notification_worker_scaffold.py` — New: 26 tests covering model, routing, stubs, wiring, error handling

## Change Log

- 2026-04-08: Story 5.1 implemented — notification-worker scaffold with Redis consumer, domain routing, handler stubs, and comprehensive error handling

## Dev Agent Record

### Implementation Plan
- Followed hexagonal architecture pattern from agent and ticket-service
- Reused existing RedisConsumer adapter (single-channel subscribe) already scaffolded
- Implemented domain routing in `services.py` using `_HANDLERS` dict keyed by NotificationType enum
- Updated `Notification` model to accept all fields from ticket-service published payloads (team_alert has ticket_url/severity/component/summary; reporter types have message/slack_user_id)
- All handler stubs log "not yet implemented" per story spec
- Error handling: missing payload, malformed payload (ValidationError), unknown types, and handler exceptions all caught and logged without crashing the consumer loop
- event_id correlation: extracted from envelope in main.py and passed through to route_notification for all log entries

### Completion Notes
- ✅ All 4 tasks/subtasks complete
- ✅ 26 tests passing (model validation, routing dispatch, error resilience, main.py wiring, callback integration)
- ✅ No regressions introduced (pre-existing test failures unrelated to this story)
- ✅ All acceptance criteria satisfied
