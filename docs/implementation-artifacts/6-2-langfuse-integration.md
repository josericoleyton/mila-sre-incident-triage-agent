# Story 6.2: Langfuse Integration for LLM Tracing

> **Epic:** 6 — Observability & Proactive Detection
> **Status:** ready-for-dev
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

- [ ] **1. Add Langfuse Python SDK dependency**
  - Add `langfuse` to `services/agent/requirements.txt`
  - Config: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` from `config.py`

- [ ] **2. Configure Langfuse integration with Pydantic AI**
  - Pydantic AI has native OpenTelemetry instrumentation
  - Option A: Use Langfuse's OTEL integration (Langfuse as OTEL backend)
  - Option B: Use Langfuse Python SDK decorators directly
  - Evaluate which approach captures tool calls and structured output best

- [ ] **3. Add trace metadata**
  - After triage completes, add metadata to the Langfuse trace:
    - `incident_id`, `classification`, `confidence`, `severity_assessment`
    - `source_type`, `reescalation`, `forced_escalation`
    - `duration_ms`
  - This enables filtering in the Langfuse dashboard

- [ ] **4. Graceful degradation**
  - Wrap Langfuse initialization in try/except
  - If Langfuse is unavailable: log warning, continue without tracing
  - Triage must NEVER fail because of Langfuse

- [ ] **5. Verify Langfuse Docker service**
  - Langfuse self-hosted Docker should be defined in docker-compose.yml (Story 1.1)
  - Verify it starts correctly and is accessible at `http://localhost:3000`
  - Default credentials for demo access

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

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
