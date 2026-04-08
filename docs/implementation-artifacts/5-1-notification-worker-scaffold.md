# Story 5.1: Notification-Worker Scaffold with Redis Consumer

> **Epic:** 5 — Notifications (Notification-Worker — Slack Only)
> **Status:** ready-for-dev
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

- [ ] **1. Wire Redis consumer in main.py**
  - Start async listener loop on `notifications` channel
  - Use `redis.asyncio` pub/sub
  - On each message: validate envelope → deserialize → route to handler

- [ ] **2. Implement notification routing**
  - `domain/services.py` — route by `notification.type`:
    - `team_alert` → call team channel handler
    - `reporter_update` → call DM handler
    - `reporter_resolved` → call DM handler
  - Unknown types → log warning, skip

- [ ] **3. Create handler stubs**
  - `handle_team_alert(notification)` — Story 5.2 implements
  - `handle_reporter_update(notification)` — Story 5.3 implements
  - `handle_reporter_resolved(notification)` — Story 5.3 implements
  - For now, log: "Notification type={type} for incident={incident_id} — handler not yet implemented"

- [ ] **4. Error handling**
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

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
