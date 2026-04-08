# Story 2.2: API Incident Intake Endpoints

> **Epic:** 2 — Incident Submission Experience (UI + API)
> **Status:** ready-for-dev
> **Priority:** 🟠 High — UI path priority workstream
> **Depends on:** Story 1.2 (Redis infrastructure, domain models)
> **FRs:** FR1, FR2, FR3, FR4, FR6

## Story

**As a** system,
**I want** FastAPI endpoints that receive incident submissions (from UI and OTEL), validate them, and publish events to Redis,
**So that** incidents enter the processing pipeline reliably regardless of source.

## Acceptance Criteria

**Given** the API service is running
**When** a POST request is sent to `/api/incidents` with a JSON/multipart body containing title (required), description (optional), component (optional), severity (optional), and file attachment (optional)
**Then** the API validates the request (title is non-empty, file type is allowed, file size ≤ 50MB)
**And** generates an internal `incident_id` (UUID v4)
**And** sets `source_type` to `"userIntegration"`
**And** sets `reporter_slack_user_id` to the configured `SLACK_REPORTER_USER_ID` from config
**And** publishes an `incident.created` event to the Redis `incidents` channel with the full incident data in the payload
**And** returns HTTP 201 with `{ "status": "ok", "data": { "incident_id": "...", "message": "Incident received" } }`

**Given** a POST request to `/api/webhooks/otel` with an OTEL error payload
**When** the API processes it
**Then** it creates an `incident.created` event with `source_type: "systemIntegration"` containing: error message, service name, trace ID, status code, timestamp
**And** `reporter_slack_user_id` is null (proactive incidents have no reporter)
**And** publishes to the Redis `incidents` channel

**Given** a POST request with missing title to `/api/incidents`
**When** the API processes it
**Then** it returns HTTP 422 with `{ "status": "error", "message": "Title is required", "code": "VALIDATION_ERROR" }`

**Given** Redis is temporarily unavailable
**When** the API attempts to publish
**Then** it returns HTTP 503 with `{ "status": "error", "message": "Service temporarily unavailable", "code": "PUBLISH_ERROR" }` and logs a structured error

**Given** a file attachment is included
**When** the API processes it
**Then** the file is stored temporarily on a shared Docker volume (`/shared/attachments/{incident_id}/`) and its path is included in the Redis event payload so the Agent can access it for multimodal processing

## Tasks / Subtasks

- [ ] **1. Create FastAPI route — POST /api/incidents**
  - In `adapters/inbound/fastapi_routes.py`
  - Accept multipart form data: title (str, required), description (str, optional), component (str, optional), severity (str, optional), file (UploadFile, optional)
  - Validate: title non-empty, file type in allowed list (image/*, video/*, .log, .txt), file size ≤ 50MB
  - Generate `incident_id` (UUID v4)
  - Set `source_type = "userIntegration"`
  - Set `reporter_slack_user_id` from `config.SLACK_REPORTER_USER_ID`
  - Return 201 with `{ status: "ok", data: { incident_id, message } }`

- [ ] **2. Create FastAPI route — POST /api/webhooks/otel**
  - Accept JSON body with OTEL error payload
  - Extract: error_message, service_name, trace_id, status_code, timestamp
  - Generate `incident_id` (UUID v4)
  - Set `source_type = "systemIntegration"`, `reporter_slack_user_id = None`
  - Publish `incident.created` to Redis `incidents` channel

- [ ] **3. Create FastAPI route — POST /api/webhooks/slack**
  - Accept Slack interaction payload (for re-escalation button clicks)
  - Parse the interaction payload to extract `incident_id` and action
  - Publish `incident.reescalate` event to Redis `reescalations` channel
  - Return HTTP 200 (Slack requires fast response)

- [ ] **4. Wire domain validation**
  - `domain/services.py` — `validate_incident(title, file_type, file_size)` → raises domain errors
  - Route handler calls domain validation before publishing

- [ ] **5. Implement file storage**
  - Save uploaded file to `/shared/attachments/{incident_id}/{filename}`
  - Include `attachment_url` (file path) in the Redis event payload
  - Shared Docker volume is mounted on both API and Agent containers

- [ ] **6. Wire Redis publisher**
  - Use `RedisPublisher` from Story 1.2 to publish `incident.created` events
  - Wrap publish in try/except → return 503 on Redis failure

- [ ] **7. Register routes in main.py**
  - Include the router in the FastAPI app
  - Add structured logging middleware (request_id, timestamp)

## Dev Notes

### Architecture Guardrails
- **Hexagonal pattern:** Routes in `adapters/inbound/`, validation in `domain/`, publishing in `adapters/outbound/`. Domain never imports from adapters (AR1, AR5).
- **Config only (AR3):** `SLACK_REPORTER_USER_ID`, `REDIS_URL` from `config.py`.
- **No email/Resend:** Reporter identity is hardcoded Slack user ID from config.
- **Response format:** Always `{ status, data/message, code }` — consistent error envelope.
- **ER3 — event_id correlation:** Include `event_id` in ALL log entries for traceability.
- **AR2 — Redis envelope:** Published `incident.created` events MUST use the mandatory envelope format.

### API Response Patterns
```python
# Success
{"status": "ok", "data": {"incident_id": "uuid", "message": "Incident received"}}
# Validation error
{"status": "error", "message": "Title is required", "code": "VALIDATION_ERROR"}
# Service error
{"status": "error", "message": "Service temporarily unavailable", "code": "PUBLISH_ERROR"}
```

### File Upload Constraints
- Allowed types: `image/*`, `video/*`, `.log`, `.txt`
- Max size: 50MB
- Storage: `/shared/attachments/{incident_id}/{original_filename}`
- Use `python-multipart` for FastAPI file handling

### OTEL Webhook Payload (expected from OTEL Collector)
```json
{
  "error_message": "HTTP 500 Internal Server Error",
  "service_name": "catalog-api",
  "trace_id": "abc123...",
  "status_code": 500,
  "timestamp": "2026-04-08T10:30:00Z"
}
```

### Key Reference Files
- Architecture doc: `docs/planning-artifacts/architecture.md` — API service definition, endpoint specs
- Story 1.2: Redis publisher and domain models (dependency)
- Story 5.3: Slack webhook endpoint for re-escalation interaction callback

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
