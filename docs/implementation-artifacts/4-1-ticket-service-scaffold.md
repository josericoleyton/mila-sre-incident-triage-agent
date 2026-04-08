# Story 4.1: Ticket-Service Scaffold with Redis Consumer & Webhook Listener

> **Epic:** 4 — Ticket Lifecycle Management (Ticket-Service)
> **Status:** ready-for-dev
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

- [ ] **1. Wire dual inbound adapters in main.py**
  - Start both Redis consumer loop AND FastAPI webhook server concurrently using `asyncio`
  - Redis consumer listens on `ticket-commands` channel
  - FastAPI runs on port 8002 (internal only — proxied via nginx)

- [ ] **2. Implement Redis consumer**
  - `adapters/inbound/redis_consumer.py`
  - Subscribe to `ticket-commands` channel
  - Validate envelope, deserialize payload into `TicketCommand` domain model
  - Route by `action` field to appropriate handler

- [ ] **3. Implement webhook listener**
  - `adapters/inbound/webhook_listener.py` — FastAPI app
  - `POST /webhooks/linear` endpoint
  - Verify HMAC signature using `LINEAR_WEBHOOK_SECRET` from config
  - Parse webhook JSON payload
  - Return 401 if signature invalid, 200 if processed

- [ ] **4. HMAC signature verification**
  - Linear sends `X-Linear-Signature` header
  - Compute HMAC-SHA256 of request body using `LINEAR_WEBHOOK_SECRET`
  - Compare signatures (constant-time comparison to prevent timing attacks)

- [ ] **5. Error handling**
  - Malformed Redis events: log warning, skip, continue
  - Invalid webhook signature: 401 response, log warning
  - Unrecognized action: log warning, skip

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

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
