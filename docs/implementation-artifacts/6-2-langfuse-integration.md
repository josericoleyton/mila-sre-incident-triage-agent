# Story 6.2: Langfuse Integration for LLM Tracing

> **Epic:** 6 — Observability & Proactive Detection
> **Status:** done
> **Priority:** 🟡 Medium — Observability & demo quality
> **Depends on:** Story 3.3a (Agent pipeline exists)
> **FRs:** FR27

## Story

**As a** system,
**I want** all LLM calls, tool usage, and reasoning chains traced in Langfuse,
**So that** triage quality can be visualized, debugged, and demonstrated to hackathon judges.

## Acceptance Criteria

**Given** the Agent service has Langfuse configured
**When** the Pydantic AI agent makes LLM calls during triage
**Then** every call is traced in Langfuse with:
- Prompt content and model response
- Tool calls (search_code, read_file) with parameters and results
- Token usage per call
- Total trace duration
- Classification result, confidence, and severity_assessment as metadata
- Source type and reescalation flag as metadata

**Given** Langfuse is running (self-hosted Docker)
**When** a user navigates to `http://localhost:3000`
**Then** the Langfuse dashboard shows traces for each triage operation
**And** traces can be filtered by classification, confidence, source_type, and incident_id

**Given** Langfuse is unavailable
**When** the Agent attempts to trace
**Then** tracing fails silently (logged warning) and triage continues without interruption

## Tasks / Subtasks

- [x] **1. Add Langfuse Python SDK dependency**
  - Add `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-http` to `services/agent/requirements.txt`
  - Config: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` from `config.py` (already present)

- [x] **2. Configure Langfuse integration with Pydantic AI**
  - Selected Option A: OTEL-based (Pydantic AI → OpenTelemetry SDK → Langfuse OTEL endpoint)
  - `Agent.instrument_all()` auto-instruments all Pydantic AI agents globally
  - OTLP HTTP exporter sends traces to `{LANGFUSE_HOST}/api/public/otel/v1/traces`
  - Basic auth via base64-encoded `{public_key}:{secret_key}`

- [x] **3. Add trace metadata**
  - `record_triage_metadata()` creates a span with all required attributes after triage:
    - `incident_id`, `classification`, `confidence`, `severity_assessment`
    - `source_type`, `reescalation`, `forced_escalation`
    - `duration_ms`
  - Called from `run_pipeline()` after successful graph execution

- [x] **4. Graceful degradation**
  - `setup_tracing()` wrapped in try/except — logs warning on failure
  - Skips entirely when credentials missing (empty public/secret key)
  - `record_triage_metadata()` is a no-op when tracer is None
  - Span recording failures caught and logged as warnings
  - Triage NEVER fails because of Langfuse

- [x] **5. Verify Langfuse Docker service**
  - Confirmed `langfuse`, `langfuse-db`, and `otel-collector` in `docker-compose.yml`
  - Langfuse accessible at `http://localhost:3000`
  - `.env.example` has all Langfuse config variables documented

### Review Findings

- [x] [Review][Patch] Duplicate `init_agent()` definition — merge artifact [main.py:17]
- [x] [Review][Patch] Metadata span orphaned from LLM traces — wrap pipeline in parent span [main.py:45]
- [x] [Review][Patch] Test patches wrong target — should be `src.main.record_triage_metadata` [test_langfuse_integration.py:253]
- [x] [Review][Patch] `LANGFUSE_HOST` not validated — add `.rstrip('/')` and empty check [tracing.py:44]
- [x] [Review][Patch] Whitespace-only credentials pass guard — add `.strip()` calls [tracing.py:36]
- [x] [Review][Patch] `setup_tracing()` not idempotent — add early return if already initialised [tracing.py:30]
- [x] [Review][Patch] No `provider.shutdown()` on exit — add shutdown hook [main.py/tracing.py]
- [x] [Review][Patch] `set_tracer_provider` before `Agent.instrument_all()` — reorder to avoid orphaned provider [tracing.py:50]
- [x] [Review][Patch] `severity_assessment` uncapped — truncate before span attribute [tracing.py:97]
- [x] [Review][Defer] No version pins on OTEL deps — deferred, pre-existing pattern
- [x] [Review][Defer] Token usage per call untested — deferred, delegated to Pydantic AI OTEL
- [x] [Review][Defer] Runtime Langfuse export failures silent — deferred, BatchSpanProcessor limitation
- [x] [Review][Defer] Dual `duration_ms` computation sites — deferred, pre-existing architecture
- [x] [Review][Defer] No `depends_on: langfuse` in docker-compose — deferred, handled by graceful degradation

## Dev Notes

### Architecture Guardrails
- **Graceful degradation:** Langfuse is an observability tool, not a critical path service. If it's down, triage continues normally.
- **Config (AR3):** `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` from `config.py`.
- **Demo impact:** Langfuse traces are a key hackathon demo element — judges can see exactly how the agent reasons, which tools it calls, and how it reaches conclusions.

### Pydantic AI + Langfuse Integration Options
1. **OTEL-based:** Pydantic AI → OpenTelemetry SDK → Langfuse OTEL endpoint
   - Pro: automatic instrumentation, captures all calls
   - Con: more setup, OTEL Collector config needed
2. **SDK-based:** Langfuse Python SDK `@observe` decorator + manual trace management
   - Pro: simpler, direct control over trace metadata
   - Con: manual instrumentation of each step

### Langfuse Docker Config (from docker-compose.yml)
```yaml
langfuse:
  image: langfuse/langfuse:latest
  ports:
    - "3000:3000"
  environment:
    - DATABASE_URL=postgresql://langfuse:langfuse@langfuse-db:5432/langfuse
    - NEXTAUTH_SECRET=mysecret
    - SALT=mysalt
    - NEXTAUTH_URL=http://localhost:3000

langfuse-db:
  image: postgres:16-alpine
  environment:
    - POSTGRES_USER=langfuse
    - POSTGRES_PASSWORD=langfuse
    - POSTGRES_DB=langfuse
```

### Key Reference Files
- Architecture doc: `docs/planning-artifacts/architecture.md` — Langfuse configuration
- Story 3.3a/3.3b: Agent pipeline that produces the traces
- Story 1.1: Docker Compose with Langfuse service

## Dev Agent Record

### Implementation Plan
- **Approach:** OTEL-based integration (Option A from Dev Notes)
- Pydantic AI's `Agent.instrument_all()` auto-captures all LLM calls, tool usage, and structured outputs
- OTLP HTTP exporter sends traces directly to Langfuse's `/api/public/otel/v1/traces` endpoint
- No Langfuse Python SDK needed — pure OpenTelemetry integration
- Custom `record_triage_metadata()` adds triage-specific attributes as a span for dashboard filtering

### Debug Log
- All 11 new tests pass
- 9 pre-existing test failures unrelated to this story (channel name changes, model field issues, nginx config)
- No regressions introduced

### Completion Notes
- Created `src/tracing.py` — centralized tracing module with setup, graceful degradation, and metadata recording
- Modified `src/main.py` — calls `setup_tracing()` at startup, calls `record_triage_metadata()` after pipeline completion
- Added `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-http` to both `requirements.txt` and `requirements-test.txt`
- Created `tests/test_langfuse_integration.py` with 11 tests covering all ACs

## File List
- `services/agent/requirements.txt` (modified)
- `services/agent/src/tracing.py` (new)
- `services/agent/src/main.py` (modified)
- `requirements-test.txt` (modified)
- `tests/test_langfuse_integration.py` (new)

## Change Log
- 2026-04-08: Implemented Langfuse OTEL integration for LLM tracing (Story 6.2)
