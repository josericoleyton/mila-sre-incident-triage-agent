# Story 4.1: Ticket-Service Scaffold with Redis Consumer & Webhook Listener

> **Epic:** 4 — Ticket Lifecycle Management (Ticket-Service)
> **Status:** done
> **Priority:** 🔴 Critical — Core MVP path
> **Depends on:** Story 1.2 (Redis infrastructure)
> **FRs:** FR5

## Story

**As a** system,
**I want** the Ticket-Service to consume ticket commands from Redis and receive webhook events from Linear,
**So that** it can act as the single owner of all Linear ticket operations.

## Acceptance Criteria

**Given** the Ticket-Service is running
**When** a `ticket.create` event is published to the `ticket-commands` channel
**Then** the service consumes it within 5 seconds
**And** deserializes the payload into a `TicketCommand` domain model
**And** routes to the appropriate handler based on `action` field (`create_engineering_ticket`)

**Given** the Ticket-Service receives a webhook POST to `/webhooks/linear`
**When** the webhook contains a Linear signature header
**Then** the service verifies the HMAC signature using `LINEAR_WEBHOOK_SECRET`
**And** processes the webhook payload if valid
**And** returns HTTP 401 if signature verification fails

**Given** a malformed Redis event or webhook
**When** processing fails
**Then** the service logs a structured error and continues (no crash)

## Tasks / Subtasks

- [x] **1. Wire dual inbound adapters in main.py**
  - Start both Redis consumer loop AND FastAPI webhook server concurrently using `asyncio`
  - Redis consumer listens on `ticket-commands` channel
  - FastAPI runs on port 8002 (internal only — proxied via nginx)

- [x] **2. Implement Redis consumer**
  - `adapters/inbound/redis_consumer.py`
  - Subscribe to `ticket-commands` channel
  - Validate envelope, deserialize payload into `TicketCommand` domain model
  - Route by `action` field to appropriate handler

- [x] **3. Implement webhook listener**
  - `adapters/inbound/webhook_listener.py` — FastAPI app
  - `POST /webhooks/linear` endpoint
  - Verify HMAC signature using `LINEAR_WEBHOOK_SECRET` from config
  - Parse webhook JSON payload
  - Return 401 if signature invalid, 200 if processed

- [x] **4. HMAC signature verification**
  - Linear sends `X-Linear-Signature` header
  - Compute HMAC-SHA256 of request body using `LINEAR_WEBHOOK_SECRET`
  - Compare signatures (constant-time comparison to prevent timing attacks)

- [x] **5. Error handling**
  - Malformed Redis events: log warning, skip, continue
  - Invalid webhook signature: 401 response, log warning
  - Unrecognized action: log warning, skip

### Review Findings

- [x] [Review][Patch] Non-dict JSON webhook payload crashes `.get()` call [webhook_listener.py:35-36] — added `isinstance(payload, dict)` guard, returns 400
- [x] [Review][Patch] Init error in `main.py` finally block causes NameError [main.py:38-47] — defensive `consumer = publisher = None` + conditional close
- [x] [Review][Patch] ER3 violation: webhook logs missing correlation ID [webhook_listener.py:38] — added `id` field extraction to log line
- [x] [Review][Patch] Missing trailing newline at end of file [webhook_listener.py, services.py] — added
- [x] [Review][Patch] No startup warning when LINEAR_WEBHOOK_SECRET is empty [main.py / config.py] — added startup warning log
- [x] [Review][Defer] asyncio.gather doesn't restart on single-task failure [main.py:40-43] — deferred, pre-existing pattern shared by agent service
- [x] [Review][Defer] No request size limit on webhook endpoint [webhook_listener.py] — deferred, nginx proxy handles upstream
- [x] [Review][Defer] No rate limiting on webhook endpoint [webhook_listener.py] — deferred, nginx proxy handles upstream
- [x] [Review][Defer] Handler exception crashes redis consumer loop [redis_consumer.py:52] — deferred, pre-existing code not changed by this story

## Dev Notes

### Architecture Guardrails
- **Dual inbound adapters:** This is the only service with both Redis consumer AND HTTP listener. `main.py` runs both concurrently.
- **Hexagonal (AR1, AR5):** Redis consumer and webhook listener are inbound adapters. Domain logic in `domain/services.py`. Adapters never contain business logic.
- **Config only (AR3):** `LINEAR_API_KEY`, `LINEAR_TEAM_ID`, `LINEAR_WEBHOOK_SECRET`, `REDIS_URL` from `config.py`.
- **Security:** HMAC signature verification is mandatory — never process unverified webhooks.
- **ER3 — event_id correlation:** Extract `event_id` from incoming Redis envelope and include it in ALL log entries.

### Concurrent Startup Pattern
```python
import asyncio
from src.adapters.inbound.redis_consumer import start_consumer
from src.adapters.inbound.webhook_listener import create_app

async def main():
    app = create_app()
    # Run both concurrently
    await asyncio.gather(
        start_consumer(),
        run_uvicorn(app, port=8002),
    )
```

### Linear Webhook Signature Verification
```python
import hmac
import hashlib

def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### Key Reference Files
- Architecture doc: `docs/planning-artifacts/architecture.md` — ticket-service definition
- Story 1.2: Redis consumer adapter pattern
- Story 4.2: Ticket creation handler (this story's consumer routes to it)
- Story 4.3: Resolution webhook handler

## File List

- `services/ticket-service/src/main.py` — Modified: wired dual inbound adapters (Redis consumer + FastAPI) with asyncio.gather
- `services/ticket-service/src/domain/services.py` — Implemented: handle_ticket_command with deserialization, action routing, error publishing
- `services/ticket-service/src/adapters/inbound/webhook_listener.py` — Implemented: FastAPI app with POST /webhooks/linear, HMAC verification, health endpoint
- `tests/test_ticket_service_scaffold.py` — Created: 22 tests covering all ACs

## Change Log

- 2026-04-08: Story 4.1 implemented — ticket-service scaffold with Redis consumer, webhook listener, HMAC verification, and error handling

## Chat Command Log

### Implementation Decisions
- `main.py` uses `asyncio.gather()` to run Redis consumer and uvicorn server concurrently, with proper cleanup in `finally` block
- `webhook_listener.py` imports `config` module (not individual names) so `LINEAR_WEBHOOK_SECRET` is read at request time — enables testability
- `domain/services.py` follows agent service pattern: extract event_id, validate with Pydantic, route by action, publish errors to `errors` channel
- HMAC verification uses `hmac.compare_digest()` for constant-time comparison (prevents timing attacks)
- `SUPPORTED_ACTIONS` set in services.py allows easy extension for Story 4.2 handlers
- Redis consumer (pre-existing from Story 1.2) already handles envelope validation and malformed JSON gracefully
- 22 tests: 3 model, 5 domain service, 5 HMAC, 4 webhook endpoint (via Starlette TestClient), 4 main.py wiring, 1 status event model
