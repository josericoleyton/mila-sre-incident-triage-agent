# Story 1.2: Redis Event Infrastructure & Shared Domain Models

> **Epic:** 1 — Project Foundation & Service Scaffolding
> **Status:** done
> **Priority:** 🔴 Critical Path — Blocks Epics 2-7
> **Depends on:** Story 1.1
> **FRs:** FR34, FR35

## Story

**As a** developer,
**I want** a consistent Redis pub/sub event infrastructure with shared message envelope format across all services,
**So that** every service can publish and consume events using the same contract without coordination.

## Acceptance Criteria

**Given** the Redis event envelope specification from the architecture
**When** a service publishes an event to any Redis channel
**Then** the message follows the mandatory envelope format:
```json
{
  "event_id": "uuid-v4",
  "event_type": "entity.action",
  "timestamp": "ISO-8601",
  "source": "service-name",
  "payload": {}
}
```
**And** each service has a `RedisPublisher` outbound adapter in `adapters/outbound/redis_publisher.py` that enforces the envelope format
**And** each consuming service has a `RedisConsumer` inbound adapter in `adapters/inbound/redis_consumer.py` that validates incoming envelopes
**And** the publisher automatically generates `event_id` (UUID v4) and `timestamp` (ISO 8601)
**And** the consumer logs a warning and skips malformed messages without crashing

**Given** the domain models specified in the architecture
**When** a developer inspects each service's `domain/models.py`
**Then** the following Pydantic models exist:
- **API service:** `IncidentReport` (title, description, component, severity, attachment_url, reporter_slack_user_id, source_type: "userIntegration" | "systemIntegration"), `IncidentEvent` (extends envelope payload)
- **Agent service:** `TriageState` (dataclass for graph state), `Classification` (enum: bug, non_incident), `TriageResult` (Pydantic BaseModel: classification, confidence, reasoning, file_refs, root_cause, suggested_fix, resolution_explanation, severity_assessment)
- **Ticket-Service:** `TicketCommand` (action, title, body, severity, labels, reporter_slack_user_id, incident_id), `TicketStatusEvent` (ticket_id, old_status, new_status)
- **Notification-Worker:** `Notification` (type: team_alert | reporter_update | reporter_resolved, slack_channel, slack_user_id, message, metadata)

**Given** a publisher in service A and a consumer in service B
**When** A publishes to a Redis channel
**Then** B receives and deserializes the event within 100ms in local Docker network

## Tasks / Subtasks

- [x] **1. Define port interfaces for each service**
  - `ports/outbound.py` — `EventPublisher` abstract class with `publish(channel, event_type, payload)` method
  - `ports/inbound.py` — `EventConsumer` abstract class with `subscribe(channel, handler)` method
  - Same pattern in every service — ports are per-service, not shared

- [x] **2. Implement RedisPublisher outbound adapter**
  - `adapters/outbound/redis_publisher.py` in each service
  - Auto-generates `event_id` (UUID v4) and `timestamp` (ISO 8601 UTC)
  - Accepts `channel`, `event_type`, `payload` dict
  - Wraps in envelope → serializes to JSON → publishes via `redis.asyncio`
  - Uses `config.REDIS_URL` for connection

- [x] **3. Implement RedisConsumer inbound adapter**
  - `adapters/inbound/redis_consumer.py` in each consuming service (agent, ticket-service, notification-worker)
  - Async listener loop using `redis.asyncio` pub/sub
  - Validates envelope structure (event_id, event_type, timestamp, source, payload)
  - Logs warning + skips malformed messages
  - Routes valid events to a registered handler callback

- [x] **4. Create domain models for API service**
  - `services/api/src/domain/models.py`:
    - `IncidentReport` — title (str, required), description (str, optional), component (str | None), severity (str | None), attachment_url (str | None), reporter_slack_user_id (str), source_type (Literal["userIntegration", "systemIntegration"])
    - `IncidentEvent` — incident_id (str), incident report fields flattened into payload

- [x] **5. Create domain models for Agent service**
  - `services/agent/src/domain/models.py`:
    - `Classification` — enum with `bug`, `non_incident`
    - `TriageResult` — Pydantic BaseModel: classification, confidence (float), reasoning (str), file_refs (list[str]), root_cause (str | None), suggested_fix (str | None), resolution_explanation (str | None), severity_assessment (str)
    - `TriageState` — dataclass: incident_id, source_type, incident (IncidentReport copy or dict), triage_result (TriageResult | None), reescalation (bool), prompt_injection_detected (bool)

- [x] **6. Create domain models for Ticket-Service**
  - `services/ticket-service/src/domain/models.py`:
    - `TicketCommand` — action (str), title (str), body (str), severity (str), labels (list[str]), reporter_slack_user_id (str | None), incident_id (str)
    - `TicketStatusEvent` — ticket_id (str), old_status (str), new_status (str), incident_id (str), reporter_slack_user_id (str | None)

- [x] **7. Create domain models for Notification-Worker**
  - `services/notification-worker/src/domain/models.py`:
    - `NotificationType` — enum: `team_alert`, `reporter_update`, `reporter_resolved`
    - `Notification` — type (NotificationType), slack_user_id (str | None), message (str), metadata (dict), allow_reescalation (bool), incident_id (str), confidence (float | None)

- [x] **8. Verify pub/sub round-trip**
  - Write a simple smoke test: API publisher → Redis → Agent consumer
  - Verify envelope format is correct
  - Verify deserialization works
  - Verify malformed message is skipped gracefully

## Dev Notes

### Architecture Guardrails
- **Hexagonal Boundary:** Port interfaces are abstract — domain layer imports ports only. Adapters implement ports. Domain has ZERO imports from `redis`, `httpx`, etc. (AR1, AR5).
- **Redis envelope is mandatory (AR2):** Every message on every channel must include `event_id`, `event_type`, `timestamp`, `source`, `payload`. No exceptions.
- **Config only (AR3):** `REDIS_URL` accessed via `config.py` — never `os.getenv()` inline.
- **Async Redis (AR4-adjacent):** Use `redis.asyncio` — not sync redis client.

### Redis Channels
| Channel | Publisher | Consumer | Event Types |
|---|---|---|---|
| `incidents` | API | Agent | `incident.created` |
| `ticket-commands` | Agent | Ticket-Service | `ticket.create` |
| `notifications` | Agent, Ticket-Service | Notification-Worker | `notification.send` |
| `errors` | Any | (logged) | `ticket.error` |
| `reescalations` | API | Agent | `incident.reescalate` |

### Event Types Inventory
- `incident.created` — new incident submitted (UI or OTEL)
- `triage.completed` — agent finished triage (observability only, no consumer)
- `ticket.create` — agent requests ticket creation
- `ticket.created` — ticket service confirms creation (future use)
- `notification.send` — request to send a notification
- `ticket.error` — error in ticket pipeline
- `incident.reescalate` — reporter requests re-escalation

### Key Pattern — Publisher Adapter
```python
# adapters/outbound/redis_publisher.py
import json
import uuid
from datetime import datetime, timezone
import redis.asyncio as aioredis
from src.config import settings

class RedisPublisher:
    def __init__(self):
        self._redis = aioredis.from_url(settings.REDIS_URL)

    async def publish(self, channel: str, event_type: str, payload: dict) -> str:
        event_id = str(uuid.uuid4())
        envelope = {
            "event_id": event_id,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "<service-name>",
            "payload": payload,
        }
        await self._redis.publish(channel, json.dumps(envelope))
        return event_id
```

### Cross-Service Event Payload Contracts

Story 1.2's domain models are the **single source of truth** for all event payload schemas. Downstream stories must match these exactly:

| Event Type | Channel | Payload Schema | Publisher → Consumer |
|---|---|---|---|
| `incident.created` | `incidents` | `{source_type, title, description, component, severity, attachment_url, reporter_slack_user_id, trace_data}` | API (2.2) → Agent (3.1) |
| `ticket.create` | `ticket-commands` | `{action, title, body, severity, labels, reporter_slack_user_id, incident_id}` | Agent (3.4) → Ticket-Service (4.2) |
| `notification.send` | `notifications` | `{type, slack_channel, slack_user_id, message, metadata, allow_reescalation, incident_id, confidence}` | Agent (3.6) / Ticket-Service (4.2, 4.3) → Notification-Worker (5.2, 5.3) |
| `incident.reescalate` | `reescalations` | `{incident_id, reporter_slack_user_id, feedback}` | API (2.2 /api/webhooks/slack) → Agent (3.8) |
| `triage.completed` | (logged) | `{incident_id, classification, confidence, severity, duration_ms, input_summary}` | Agent (3.4) → observability |
| `ticket.error` | `errors` | `{service, error, context, incident_id}` | Any → logging |

**Contract rule:** If a consuming story's expected payload doesn't match the schema above, the discrepancy must be resolved in Story 1.2's domain models, not in the downstream service.

### Key Reference Files
- Architecture doc: `docs/planning-artifacts/architecture.md` — Redis channels, event envelope format, domain models
- Epics doc: `docs/planning-artifacts/epics.md` — event type inventory, domain model specs

## Chat Command Log

**Implementation date:** 2026-04-08

**Decisions:**
- Port interfaces use `abc.ABC` with async abstract methods per hexagonal architecture
- RedisPublisher auto-generates UUID v4 `event_id` and ISO 8601 UTC `timestamp` per AR2
- RedisConsumer validates all 5 required envelope fields; logs warning + skips malformed messages
- Config accessed via `from src.config import REDIS_URL` — no inline `os.getenv()` (AR3)
- Uses `redis.asyncio` throughout (AR4)
- Domain models use Pydantic `BaseModel` except `TriageState` which is a `dataclass` per spec
- API service has publisher only (no consumer); agent, ticket-service, notification-worker have both

**Tests:** 18 unit tests in `tests/test_redis_pubsub.py` — all passing
- Envelope format: required fields, UUID v4, ISO 8601 timestamp, payload preservation
- Consumer validation: valid accepted, invalid JSON skipped, missing fields skipped
- All 4 service domain models: field defaults, enum values, type validation

**Files created/modified:**
- `services/api/src/ports/outbound.py` — EventPublisher ABC
- `services/api/src/ports/inbound.py` — EventConsumer ABC
- `services/api/src/adapters/outbound/redis_publisher.py` — RedisPublisher
- `services/api/src/domain/models.py` — IncidentReport, IncidentEvent
- `services/agent/src/ports/outbound.py` — EventPublisher ABC
- `services/agent/src/ports/inbound.py` — EventConsumer ABC
- `services/agent/src/adapters/outbound/redis_publisher.py` — RedisPublisher
- `services/agent/src/adapters/inbound/redis_consumer.py` — RedisConsumer
- `services/agent/src/domain/models.py` — Classification, TriageResult, TriageState
- `services/ticket-service/src/ports/outbound.py` — EventPublisher ABC
- `services/ticket-service/src/ports/inbound.py` — EventConsumer ABC
- `services/ticket-service/src/adapters/outbound/redis_publisher.py` — RedisPublisher
- `services/ticket-service/src/adapters/inbound/redis_consumer.py` — RedisConsumer
- `services/ticket-service/src/domain/models.py` — TicketCommand, TicketStatusEvent
- `services/notification-worker/src/ports/outbound.py` — EventPublisher ABC
- `services/notification-worker/src/ports/inbound.py` — EventConsumer ABC
- `services/notification-worker/src/adapters/outbound/redis_publisher.py` — RedisPublisher
- `services/notification-worker/src/adapters/inbound/redis_consumer.py` — RedisConsumer
- `services/notification-worker/src/domain/models.py` — NotificationType, Notification
- `tests/test_redis_pubsub.py` — 18 unit tests
