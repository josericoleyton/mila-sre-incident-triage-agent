# Story 3.1: Agent Service Scaffold with Redis Consumer

> **Epic:** 3 — AI Triage & Code Analysis (Agent)
> **Status:** ready-for-dev
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

- [ ] **1. Wire Redis consumer in main.py**
  - Start async listener loop on both `incidents` and `reescalations` channels
  - Use `redis.asyncio` pub/sub subscribe
  - Route incoming events to appropriate handler based on channel

- [ ] **2. Implement event deserialization and routing**
  - Validate envelope format (from Story 1.2 consumer pattern)
  - Deserialize `incident.created` payload into `IncidentReport` domain model
  - Deserialize `incident.reescalate` payload for re-escalation
  - On deserialization failure → log warning + publish `ticket.error` + skip

- [ ] **3. Initialize TriageState**
  - Create `TriageState` dataclass from deserialized incident
  - Set `reescalation = True` for re-escalation events, `False` for new incidents
  - Copy `prompt_injection_detected` flag from event payload

- [ ] **4. Initialize Pydantic AI Agent on startup**
  - Read `LLM_MODEL` from `config.py`
  - Create Pydantic AI `Agent` instance with configured model
  - Log: `"Agent initialized with model: {LLM_MODEL}"`
  - Handle startup failure gracefully (missing API keys, invalid model string)

- [ ] **5. Connect consumer to graph pipeline (stub)**
  - After TriageState is initialized, call the graph pipeline (Story 3.3a implements it)
  - For now, log: `"Triage pipeline triggered for incident {incident_id}"` and return

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

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
