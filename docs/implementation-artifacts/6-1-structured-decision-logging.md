# Story 6.1: Structured Decision Logging Across Pipeline

> **Epic:** 6 — Observability & Proactive Detection
> **Status:** ready-for-dev
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
- `reasoning_summary` (what code was examined, what was ruled out, conclusion)
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

- [ ] **1. Standardize structured logging format across all services**
  - JSON log format: `{"timestamp": "ISO-8601", "level": "INFO", "service": "<name>", "event_id": "<corr>", "message": "..."}`
  - Use Python `logging` with JSON formatter
  - Each service already has this from Story 1.1 — verify consistency

- [ ] **2. Enhance triage.completed event payload in Agent**
  - Ensure all fields from ACs are present in the event published by Story 3.4
  - Add `input_summary` (metadata only — title length, component, severity, attachment present?)
  - Verify NO raw user text in the event payload

- [ ] **3. Add structured log entries at each pipeline stage**
  - API: log on incident received, on publish success/failure
  - Agent: log on triage start, on classification complete, on command published
  - Ticket-Service: log on command consumed, on Linear API call, on success/failure
  - Notification-Worker: log on notification consumed, on Slack send, on success/failure

- [ ] **4. Verify metadata-only logging (NFR5)**
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
