# Story 3.1: Agent Service Scaffold with Redis Consumer

> **Epic:** 3 — AI Triage & Code Analysis (Agent)
> **Status:** done
> **Priority:** 🔴 Critical — Core MVP path
> **Depends on:** Story 1.2 (Redis infrastructure)
> **FRs:** FR7

## Story

**As a** system,
**I want** the Agent service to continuously consume incident events from the Redis `incidents` channel and initialize processing,
**So that** every submitted incident is automatically picked up for triage.

## Acceptance Criteria

**Given** the Agent service is running and connected to Redis
**When** an `incident.created` event is published to the `incidents` channel
**Then** the Agent consumes the event within 5 seconds
**And** deserializes it into the `IncidentReport` domain model
**And** identifies the `source_type` (`userIntegration` or `systemIntegration`)
**And** logs a structured entry: `"Triage started for incident {incident_id}, source: {source_type}"`
**And** initializes a `TriageState` dataclass with the incident data for the graph pipeline

**Given** the Agent receives a malformed event
**When** deserialization fails
**Then** it logs a structured warning with the event_id and error details
**And** publishes a `ticket.error` event to the `errors` channel
**And** continues consuming the next event (does not crash)

**Given** the LLM provider is configured via `LLM_MODEL` env var
**When** the Agent service starts
**Then** it initializes the Pydantic AI Agent with the configured model string (e.g., `openrouter:google/gemma-4`, `anthropic:claude-sonnet-4-20250514`)
**And** logs the active LLM provider on startup

**Given** the Agent also listens on the `reescalations` channel
**When** an `incident.reescalate` event is published
**Then** the Agent consumes it and re-initializes triage for the referenced incident with `reescalation: true` flag

## Tasks / Subtasks

- [x] **1. Wire Redis consumer in main.py**
  - Start async listener loop on both `incidents` and `reescalations` channels
  - Use `redis.asyncio` pub/sub subscribe
  - Route incoming events to appropriate handler based on channel

- [x] **2. Implement event deserialization and routing**
  - Validate envelope format (from Story 1.2 consumer pattern)
  - Deserialize `incident.created` payload into `IncidentReport` domain model
  - Deserialize `incident.reescalate` payload for re-escalation
  - On deserialization failure → log warning + publish `ticket.error` + skip

- [x] **3. Initialize TriageState**
  - Create `TriageState` dataclass from deserialized incident
  - Set `reescalation = True` for re-escalation events, `False` for new incidents
  - Copy `prompt_injection_detected` flag from event payload

- [x] **4. Initialize Pydantic AI Agent on startup**
  - Read `LLM_MODEL` from `config.py`
  - Create Pydantic AI `Agent` instance with configured model
  - Log: `"Agent initialized with model: {LLM_MODEL}"`
  - Handle startup failure gracefully (missing API keys, invalid model string)

- [x] **5. Connect consumer to graph pipeline (stub)**
  - After TriageState is initialized, call the graph pipeline (Story 3.3a implements it)
  - For now, log: `"Triage pipeline triggered for incident {incident_id}"` and return

### Review Findings

- [x] [Review][Decision] **AC1 model name: `IncidentEvent` vs `IncidentReport`** — Dismissed: `IncidentEvent` correctly matches the wire format; AC text is imprecise.
- [x] [Review][Patch] **Handler exceptions crash the multi-channel listener** — Fixed: try/except wraps handler call in subscribe_multi.
- [x] [Review][Patch] **`callable` (lowercase) type hint** — Fixed: `Callable[[TriageState], Awaitable[None]]`.
- [x] [Review][Patch] **AC2: Envelope-level malformed events bypass `ticket.error`** — Fixed: subscribe_multi accepts `error_publisher` and publishes ticket.error for adapter-level failures.
- [x] [Review][Patch] **ER3: `event_id` not in TriageState or pipeline logs** — Fixed: `event_id` field added to TriageState; pipeline stub logs it.
- [x] [Review][Patch] **Message data not validated as dict** — Fixed: `isinstance(envelope, dict)` guard added.
- [x] [Review][Patch] **Publisher error during error reporting crashes handler** — Fixed: `_publish_error` helper wraps publish in try/except.
- [x] [Review][Patch] **`consumer.close()` failure skips `publisher.close()`** — Fixed: nested try/finally in main.
- [x] [Review][Defer] **Agent initialized but never wired** — `init_agent()` result unused. By design — Story 3.3a will wire it. — deferred, pre-existing
- [x] [Review][Defer] **Code duplication in handlers** — Two near-identical handlers. Refactor candidate. — deferred, pre-existing
- [x] [Review][Defer] **Sequential handler blocks consumer loop** — MVP design; concurrency deferred. — deferred, pre-existing

## Dev Notes

### Architecture Guardrails
- **Hexagonal pattern:** Redis consumer in `adapters/inbound/redis_consumer.py`. Domain logic in `domain/`. Never import redis in domain (AR1, AR5).
- **Config only (AR3):** `LLM_MODEL`, `REDIS_URL`, `GITHUB_TOKEN` from `config.py`.
- **Async everything:** Use `redis.asyncio`, `asyncio` event loop. Never blocking IO.
- **LLM provider (AR7):** Configurable via `LLM_MODEL` env var — Pydantic AI native model strings (e.g., `openrouter:google/gemma-4`, `anthropic:...`).
- **ER3 — event_id correlation:** Extract `event_id` from incoming Redis envelope and include it in ALL log entries throughout the triage pipeline.

### Dual Channel Subscription
```python
# The consumer listens on two channels simultaneously
pubsub = redis_client.pubsub()
await pubsub.subscribe("incidents", "reescalations")
async for message in pubsub.listen():
    if message["type"] == "message":
        channel = message["channel"].decode()
        if channel == "incidents":
            await handle_incident(message["data"])
        elif channel == "reescalations":
            await handle_reescalation(message["data"])
```

### Key Reference Files
- Story 1.2: Redis consumer/publisher adapters, domain models
- Architecture doc: `docs/planning-artifacts/architecture.md` — agent service definition, Redis channels
- Story 3.3a: Graph pipeline that this story feeds into

## File List

- `services/agent/src/main.py` — modified: wired dual-channel Redis consumer, Pydantic AI Agent init, pipeline stub
- `services/agent/src/ports/inbound.py` — modified: added `subscribe_multi` and `close` abstract methods
- `services/agent/src/adapters/inbound/redis_consumer.py` — modified: implemented `subscribe_multi` for dual-channel routing
- `services/agent/src/domain/models.py` — modified: added `IncidentEvent` Pydantic model for payload deserialization
- `services/agent/src/domain/triage_handler.py` — new: event handlers for incident.created and incident.reescalate
- `tests/test_agent_scaffold.py` — new: 22 tests covering all ACs

## Change Log

- 2026-04-08: Implemented Story 3.1 — Agent service scaffold with dual-channel Redis consumer, event deserialization, TriageState initialization, Pydantic AI Agent startup, and graph pipeline stub.
- 2026-04-08: Addressed code review findings — 7 patches applied, 1 decision dismissed, 3 deferred.

## Dev Agent Record

### Implementation Notes
- Hexagonal architecture preserved: domain layer (`triage_handler.py`) uses ports only, no redis imports
- `subscribe_multi` added to `EventConsumer` port and `RedisConsumer` adapter for dual-channel listening on `incidents` + `reescalations`
- `IncidentEvent` Pydantic model added to agent domain for strict payload validation
- Malformed events publish `ticket.error` to `errors` channel with `event_id` correlation
- `event_id` from envelope included in all structured log entries
- Pydantic AI `Agent` initialized with `LLM_MODEL` from config; startup failures logged and raised
- Pipeline stub logs `"Triage pipeline triggered for incident {incident_id}"` — Story 3.3a will replace it
- 22 tests added, 40 total pass with zero regressions
