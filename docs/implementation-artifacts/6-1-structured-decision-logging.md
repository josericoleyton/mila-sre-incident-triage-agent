# Story 6.1: Structured Decision Logging Across Pipeline

> **Epic:** 6 — Observability & Proactive Detection
> **Status:** done
> **Priority:** 🟡 Medium — Observability & demo quality
> **Depends on:** Story 1.1 (logging standardization applies to all services); Story 3.4 (triage.completed event enhancement)
> **FRs:** FR26, FR32

## Story

**As a** team lead (Diego),
**I want** every triage decision logged with structured metadata — classification, confidence, reasoning, and timing — without raw user input,
**So that** I can review triage quality and spot low-confidence decisions.

## Acceptance Criteria

**Given** any triage completes (bug or non-incident)
**When** the `triage.completed` event is published
**Then** the structured log entry contains:
- `timestamp` (ISO 8601)
- `incident_id` (correlation)
- `source_type` (`userIntegration` or `systemIntegration`)
- `input_summary` (metadata only: component, severity, title length — NO raw text, NO attachment content)
- `classification` (bug or non_incident)
- `confidence` (float 0.0-1.0)
- `reasoning_length` (int — length of reasoning text, NO raw content per NFR5)
- `reasoning_mentions_files` (bool — whether reasoning references examined files)
- `files_examined` (list of file paths the agent searched/read)
- `severity_assessment` (agent's independent severity with justification)
- `forced_escalation` (boolean — true for systemIntegration)
- `reescalation` (boolean — true if this was a re-escalation)
- `duration_ms` (total triage time)

**Given** any pipeline stage (API intake, Agent triage, Ticket creation, Notification delivery)
**When** the stage processes an event
**Then** it produces at least one structured JSON log entry with: `timestamp`, `level`, `service`, `event_id`, `message`

**Given** the observability logging
**When** a reviewer inspects the logs
**Then** no raw user input text or attachment content appears — only metadata

## Tasks / Subtasks

- [x] **1. Standardize structured logging format across all services**
  - JSON log format: `{"timestamp": "ISO-8601", "level": "INFO", "service": "<name>", "event_id": "<corr>", "message": "..."}`
  - Use Python `logging` with JSON formatter
  - Each service already has this from Story 1.1 — verify consistency

- [x] **2. Enhance triage.completed event payload in Agent**
  - Ensure all fields from ACs are present in the event published by Story 3.4
  - Add `input_summary` (metadata only — title length, component, severity, attachment present?)
  - Verify NO raw user text in the event payload

- [x] **3. Add structured log entries at each pipeline stage**
  - API: log on incident received, on publish success/failure
  - Agent: log on triage start, on classification complete, on command published
  - Ticket-Service: log on command consumed, on Linear API call, on success/failure
  - Notification-Worker: log on notification consumed, on Slack send, on success/failure

- [x] **4. Verify metadata-only logging (NFR5)**
  - Audit all log statements and Redis events
  - Ensure NO raw title, description, or attachment content appears in logs or observability events
  - Only metadata: lengths, types, classifications, scores

## Dev Notes

### Architecture Guardrails
- **NFR5, FR32 — CRITICAL:** No raw user input in observability traces. Only metadata (component, severity, title_length, file types). This is a security and privacy requirement.
- **NFR13:** Every pipeline stage produces at least one log entry. Correlation via `event_id` from Redis envelope.
- **Structured JSON to stdout:** Docker Compose collects stdout logs. No separate log files.

### Input Summary Pattern (metadata only)
```python
input_summary = {
    "title_length": len(incident.title),
    "has_description": bool(incident.description),
    "component": incident.component,
    "severity": incident.severity,
    "has_attachment": bool(incident.attachment_url),
    "source_type": incident.source_type,
}
# NEVER: input_summary["title"] = incident.title  ← FORBIDDEN
```

### Key Reference Files
- Story 3.4: triage.completed event publishing
- Architecture doc: `docs/planning-artifacts/architecture.md` — logging format, NFR5

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*

### Implementation Notes (2026-04-08)

**Task 1 — Structured JSON Formatter:**
- Created `json_logging.py` module in each service (`api`, `agent`, `ticket-service`, `notification-worker`)
- `StructuredJsonFormatter` class outputs proper JSON via `json.dumps()` (replaces string-interpolated format that wasn't truly JSON-safe)
- Each log line: `{"timestamp": "ISO-8601", "level": "INFO", "service": "<name>", "event_id": "<corr>", "message": "..."}`
- `event_id` pulled from log record attribute when available (via `extra=` kwargs)
- `error` field appended on exception records
- `setup_logging()` wires the formatter to root logger, clearing any previous handlers
- Replaced `logging.basicConfig()` in all 4 service `main.py` files with `setup_logging()`

**Task 2 — Enhanced triage.completed Payload:**
- Added `_build_input_summary(state)` → metadata-only dict: `title_length`, `has_description`, `component`, `severity`, `has_attachment`, `source_type`
- Added `input_summary` and `files_examined` fields to `_build_triage_completed_payload()`
- `files_examined` uses `result.file_refs` (list of code paths the agent analyzed)
- Zero raw user text in payload — verified by test assertions

**Task 3 — Pipeline Stage Logging:**
- API: added "Incident received" log with metadata (`incident_id`, `component`, `severity`, `has_attachment`, `source_type`) for both user and OTEL paths
- Agent: already had comprehensive logging from Stories 3.x (triage start, classification, command published)
- Ticket-Service: added "Ticket command consumed", "Creating Linear ticket" with priority, and "Published team_alert notification" success logs
- Notification-Worker: scaffold has startup logging; structured formatter now applies

**Task 4 — NFR5 Compliance Audit:**
- Fixed `search_code` tool: replaced `logger.info("query: %s", query)` with `logger.info("query_length=%d", len(query))` — raw LLM-generated query could echo user input
- `read_file` tool: logs file_path (repository path, not user input) — safe
- All other log statements audit: no raw title, description, or attachment content in any logger call
- `_build_input_summary` and `_build_triage_completed_payload`: verified no raw text fields

**Files Created:**
- `services/api/src/json_logging.py`
- `services/agent/src/json_logging.py`
- `services/ticket-service/src/json_logging.py`
- `services/notification-worker/src/json_logging.py`
- `tests/test_structured_decision_logging.py` — 44 tests

**Files Modified:**
- `services/api/src/main.py` — replaced basicConfig with setup_logging()
- `services/agent/src/main.py` — replaced basicConfig with setup_logging()
- `services/ticket-service/src/main.py` — replaced basicConfig with setup_logging()
- `services/notification-worker/src/main.py` — replaced basicConfig with setup_logging()
- `services/agent/src/graph/nodes/generate_output.py` — added `_build_input_summary()`, enhanced `_build_triage_completed_payload()` with `input_summary` and `files_examined`
- `services/agent/src/graph/tools/search_code.py` — sanitized log to use query_length instead of raw query
- `services/api/src/adapters/inbound/fastapi_routes.py` — added "Incident received" structured logs
- `services/ticket-service/src/domain/services.py` — added "command consumed", "Creating Linear ticket", notification success logs

**Test Results:** 389 passed (44 new), 8 pre-existing failures (0 regressions introduced)

### Review Findings

- [x] [Review][Decision] `reasoning_summary` NFR5 partial violation — Resolved: replaced `reasoning_summary` with metadata-only fields `reasoning_length` (int) and `reasoning_mentions_files` (bool). Fully NFR5 compliant.
- [x] [Review][Patch] `event_id` never populated as structured field — Fixed: new log calls in ticket-service and API now use `extra={"event_id": event_id}` so the formatter populates the top-level field.
- [x] [Review][Patch] `_build_input_summary` crashes on non-string title — Fixed: added `str()` cast guard on `incident.get("title")`.
- [x] [Review][Patch] Uvicorn duplicate log output — Fixed: `setup_logging()` now clears uvicorn's own handlers (`uvicorn`, `uvicorn.error`, `uvicorn.access`) in api and ticket-service.
- [x] [Review][Patch] `StructuredJsonFormatter.format()` crashes on bad format args — Fixed: wrapped `record.getMessage()` in try/except with fallback to `str(record.msg)`.
- [x] [Review][Patch] Timestamp uses format-time not event-time — Fixed: replaced `datetime.now(timezone.utc)` with `datetime.fromtimestamp(record.created, tz=timezone.utc)`.
- [x] [Review][Defer] Notification-worker missing domain-level logs — `domain/services.py` is empty (Slack integration not yet implemented). Task 3 spec requires Slack send/success/failure logs; blocked by scaffold state. — deferred, pre-existing
- [x] [Review][Defer] No `trace_id`/`span_id` in JSON format — OTEL collector is configured but the JSON formatter emits no trace context fields. Cross-service request correlation requires OTEL integration beyond stdlib logging scope. — deferred, out of scope for this story
