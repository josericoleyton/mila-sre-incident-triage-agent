---
stepsCompleted: [step-01-validate-prerequisites, step-02-design-epics, step-03-create-stories, step-04-final-validation]
inputDocuments: [docs/planning-artifacts/prd.md, docs/planning-artifacts/architecture.md, docs/mila_ui_final_v1.html]
---

# mila - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for mila, decomposing the requirements from the PRD and Architecture into implementable stories. The epic structure is designed to **maximize parallel development** across the 5 decoupled services (UI, API, Agent, Ticket-Service, Notification-Worker) connected via the Redis event bus.

### Key Design Decisions

- **Integrations:** Linear (ticketing) + Slack (all notifications — team channel + reporter DMs). No email.
- **Single board:** One Linear Engineering Board. No helpdesk board.
- **Async everything:** Agent creates an engineering ticket only for real bugs. Reporter is notified via Slack DM.
- **Two incident sources:** `userIntegration` (UI form) and `systemIntegration` (OTEL proactive). Proactive incidents are always escalated — agent cannot dismiss them since they're telemetry-backed.
- **Non-incident dismissal:** Only for `userIntegration` type. Agent directly publishes notification to reporter (bypasses Ticket Service).
- **Reporter identity:** Hardcoded Slack user ID in config — UI always sends the same reporter. No form changes needed.
- **Agent intelligence features:** Confidence-based decisions, severity analysis, and misclassification re-escalation — all integrated into the agent's analytical capabilities for demo impact.

### Parallelism Strategy

```
Epic 1 (Foundation) ──┬──▸ Epic 2 (UI + API)           ← UI PATH PRIORITY
                      ├──▸ Epic 3 (Agent)               ← parallel
                      ├──▸ Epic 4 (Ticket Service)      ← parallel
                      └──▸ Epic 5 (Notifications)       ← parallel
                              │
                      Epic 6 (Observability + OTEL) ← after Epic 3
                              │
                      Epic 7 (Deploy + Docs) ← final
```

After Epic 1 completes, **four workstreams run in parallel** — one per decoupled service. Each service communicates only via Redis, so stories in Epics 2–5 have zero cross-epic runtime dependencies.

### Story Priority Within Epics

Stories within each epic are ordered by priority:
1. **Valid bug → ticket creation** (core MVP path)
2. **Proactive OTEL detection + escalation** (differentiator)
3. **Non-incident dismissal with reporter notification** (edge case handling)
4. **Agent intelligence features** (confidence, re-escalation — demo polish)

## Requirements Inventory

### Functional Requirements

- FR1: Reporter can submit an incident report with a title and description via a web form
- FR2: Reporter can attach one file (image, log, or video) to the incident report
- FR3: Reporter can optionally select an affected component from a predefined list
- FR4: Reporter can optionally indicate perceived severity (Low / Med / High / Crit)
- FR5: System creates an engineering ticket in the Linear Engineering Board when a bug is confirmed
- FR6: Reporter sees a confirmation screen with a tracking ID after submission
- FR7: Agent is triggered automatically when a new incident event is published
- FR8: Agent reads the incident content including any attached files (multimodal processing)
- FR9: Agent analyzes the incident against the eShop codebase (source files and documentation)
- FR10: Agent classifies the incident as either an infrastructure/code bug or a non-incident
- FR11: Agent produces a confidence score for each classification decision
- FR12: Agent logs chain-of-thought reasoning for every classification
- FR13: Agent publishes a ticket creation command when a bug is classified
- FR14: Engineering ticket includes direct reference to the affected file and line range in the codebase
- FR15: Engineering ticket includes a one-sentence probable root cause
- FR16: Engineering ticket includes a suggested first step to investigate or fix
- FR17: Engineering ticket includes the original report content and attachments
- FR18: Engineering ticket includes the incident tracking ID for correlation
- FR19: System sends Slack notification to the engineering team channel when a new engineering ticket is created
- FR20: Agent publishes a reporter notification when a non-incident is classified (userIntegration only)
- FR21: Agent provides a specific, technical resolution response explaining why this is not an incident
- FR22: Resolution response is delivered to the reporter via Slack DM
- FR23: When an engineer marks an engineering ticket as resolved, the system detects the status change
- FR24: System sends a Slack DM to the original reporter that their incident has been resolved
- FR25: Proactive incidents (systemIntegration) from OTEL are always escalated — never dismissed
- FR26: Every triage decision is logged with structured entry: timestamp, input summary, classification result, reasoning, confidence score
- FR27: Decision logs are sent to an observability platform for visualization and analysis
- FR28: Triage reasoning is visible within ticket content
- FR29: System sanitizes all user-submitted text before it reaches the LLM
- FR30: System flags inputs that contain patterns resembling prompt injection attempts
- FR31: Agent treats all user input as untrusted data, never as instructions
- FR32: Observability traces log metadata only — never raw user input content
- FR33: Full application runs via `docker compose up --build` with no host-level dependencies beyond Docker
- FR34: All integration credentials are configured via environment variables
- FR35: Repository includes `.env.example` with placeholder values and comments for all required variables
- FR36: Repository includes `README.md` with architecture overview, setup instructions, and project summary
- FR37: Repository includes `AGENTS_USE.md` with agent documentation
- FR38: Repository includes `SCALING.md` with scaling assumptions and technical decisions
- FR39: Repository includes `QUICKGUIDE.md` with step-by-step instructions
- FR40: Repository includes `docker-compose.yml` that orchestrates all services
- FR41: Repository includes `Dockerfile(s)` referenced by `docker-compose.yml`
- FR42: Repository is public and licensed under MIT

### Non-Functional Requirements

- NFR1: Non-incident path completes in under 2 minutes
- NFR2: Bug path completes in under 3 minutes
- NFR3: UI form submission to API acknowledgment completes in under 5 seconds
- NFR4: Agent trigger fires within 30 seconds of incident event publication
- NFR5: No raw user input appears in observability traces — metadata only
- NFR6: All API keys and credentials loaded from environment variables, never hardcoded
- NFR7: LLM system prompt enforces untrusted-input boundary
- NFR8: Input sanitization runs before any user-submitted text reaches the LLM
- NFR9: Linear API calls include error handling with clear failure messages
- NFR10: Slack API failures are logged and do not crash the pipeline
- NFR11: Each integration can be tested independently of the others
- NFR12: Agent gracefully handles LLM API failures or timeouts
- NFR13: Every stage of the pipeline produces at least one trace/log entry
- NFR14: Structured decision logs are queryable and visualizable
- NFR15: Agent reasoning is human-readable
- NFR16: Architecture supports horizontal scaling of agent service (documented, not implemented)
- NFR17: No hard-coded single-instance assumptions
- NFR18: `docker compose up --build` from clean clone results in fully running application
- NFR19: No host-level dependencies beyond Docker
- NFR20: Application exposes only required ports

### Additional Requirements

- AR1: Hexagonal architecture (ports & adapters) per service per architecture doc
- AR2: Redis event envelope format with mandatory fields (event_id, event_type, timestamp, source, payload)
- AR3: All environment variables accessed via config.py per service — never os.getenv() inline
- AR4: httpx.AsyncClient for all HTTP calls — never requests library
- AR5: Domain layer has zero imports from adapters — respect hexagonal boundaries
- AR6: nginx serves as API gateway — only port 8080 externally exposed (plus Langfuse 3000)
- AR7: LLM provider configurable via LLM_MODEL env var (Pydantic AI native model strings)
- AR8: Agent uses pydantic-graph for state machine orchestration of triage pipeline
- AR9: Agent uses Pydantic AI structured output (output_type=TriageResult) — no manual JSON parsing
- AR10: Notification chain: team notifications sent ONLY after ticket creation succeeds. Non-incident notifications published directly by Agent.
- AR11: Two incident source types: `userIntegration` (UI form) and `systemIntegration` (OTEL proactive). Agent behavior differs by source type.

### UX Design Requirements

- UX1: Static SPA form served via nginx — fields: title, description, component (optional), severity (optional), file attachment (optional)
- UX2: Mila contextual hint bar updates dynamically as user types title
- UX3: Progress bar reflects form completion state
- UX4: Submit button activates only when title is filled
- UX5: Success screen shows "Mila is on it" with generated tracking ID and "What happens next" steps
- UX6: File upload accepts image/*, video/*, .log, .txt up to 50MB
- UX7: Reporter identity displayed in footer (hardcoded as "Ana Botero") — Slack user ID sent automatically with every submission

### FR Coverage Map

- FR1: Epic 2 — Story 2.3 (UI form submission integration)
- FR2: Epic 2 — Story 2.3 (file upload handling)
- FR3: Epic 2 — Story 2.3 (component selection)
- FR4: Epic 2 — Story 2.3 (severity selection)
- FR5: Epic 4 — Story 4.2 (engineering ticket creation in Linear)
- FR6: Epic 2 — Story 2.3 (confirmation screen with tracking ID)
- FR7: Epic 3 — Story 3.1 (agent Redis consumer trigger)
- FR8: Epic 3 — Story 3.3a (multimodal input processing in AnalyzeInputNode)
- FR9: Epic 3 — Story 3.3a (eShop codebase analysis in SearchCodeNode) + Story 3.2 (GitHub API tools)
- FR10: Epic 3 — Story 3.3b (bug vs non-incident classification in ClassifyNode)
- FR11: Epic 3 — Story 3.7 (confidence scoring integrated into classification)
- FR12: Epic 3 — Story 3.3b (chain-of-thought reasoning)
- FR13: Epic 3 — Story 3.4 (ticket creation command for bugs)
- FR14: Epic 4 — Story 4.2 (file/line references in ticket)
- FR15: Epic 4 — Story 4.2 (root cause in ticket)
- FR16: Epic 4 — Story 4.2 (suggested fix in ticket)
- FR17: Epic 4 — Story 4.2 (original report in ticket)
- FR18: Epic 4 — Story 4.2 (tracking ID correlation in ticket)
- FR19: Epic 5 — Story 5.2 (Slack team channel notification)
- FR20: Epic 3 — Story 3.6 (non-incident dismissal, agent publishes notification)
- FR21: Epic 3 — Story 3.6 (technical resolution explanation)
- FR22: Epic 5 — Story 5.3 (Slack DM to reporter)
- FR23: Epic 4 — Story 4.3 (detect resolution via Linear webhook)
- FR24: Epic 5 — Story 5.3 + Epic 4 — Story 4.3 (Slack DM on resolution)
- FR25: Epic 3 — Story 3.5 (proactive incidents always escalated)
- FR26: Epic 6 — Story 6.1 (structured triage decision logging)
- FR27: Epic 6 — Story 6.2 (Langfuse observability platform integration)
- FR28: Epic 3 — Story 3.4 (reasoning visible in ticket content)
- FR29: Epic 2 — Story 2.4 (input sanitization middleware)
- FR30: Epic 2 — Story 2.4 (prompt injection pattern detection)
- FR31: Epic 3 — Story 3.3b (system prompt untrusted-input boundary)
- FR32: Epic 6 — Story 6.1 (metadata-only logging)
- FR33: Epic 7 — Story 7.1 (docker compose up --build)
- FR34: Epic 1 — Story 1.1 (env var configuration pattern)
- FR35: Epic 1 — Story 1.1 (.env.example with placeholders)
- FR36: Epic 7 — Story 7.3 (README.md)
- FR37: Epic 7 — Story 7.3 (AGENTS_USE.md)
- FR38: Epic 7 — Story 7.3 (SCALING.md)
- FR39: Epic 7 — Story 7.3 (QUICKGUIDE.md)
- FR40: Epic 1 — Story 1.1 (docker-compose.yml)
- FR41: Epic 1 — Story 1.1 (Dockerfiles per service)
- FR42: Epic 7 — Story 7.3 (MIT LICENSE — already exists)

## Epic List

### Epic 1: Project Foundation & Service Scaffolding
Bootstrap the multi-service project structure, Docker orchestration, and Redis event infrastructure so that all service teams can begin independent development immediately.
**FRs covered:** FR34, FR35, FR40, FR41
**Parallelism:** Blocks all other epics. Must complete first.

### Epic 2: Incident Submission Experience (UI + API)
A reporter can submit an incident report through the web form and receive immediate confirmation that Mila is processing it, with input security applied before data enters the pipeline.
**FRs covered:** FR1, FR2, FR3, FR4, FR6, FR29, FR30
**Parallelism:** Starts immediately after Epic 1. PRIORITY workstream (UI path).

### Epic 3: AI Triage & Code Analysis (Agent)
The Agent autonomously consumes incidents, analyzes the eShop codebase via GitHub API, classifies each incident as bug or non-incident with chain-of-thought reasoning, confidence scoring, and severity analysis. It publishes structured commands for downstream services and handles non-incident dismissals directly. Includes advanced agent intelligence: confidence-based decisions, severity interpretation, and misclassification re-escalation.
**FRs covered:** FR7, FR8, FR9, FR10, FR11, FR12, FR13, FR20, FR21, FR25, FR28, FR31
**Parallelism:** Starts after Epic 1. Runs in parallel with Epics 2, 4, 5.
**Stories:** 3.1, 3.2, 3.3a, 3.3b, 3.4, 3.5, 3.6, 3.7, 3.8 (9 stories)

### Epic 4: Ticket Lifecycle Management (Ticket-Service)
The Ticket-Service consumes ticket commands from Redis, creates engineering tickets in Linear with full triage details, publishes notification events on success, and handles resolution lifecycle via Linear webhooks.
**FRs covered:** FR5, FR14, FR15, FR16, FR17, FR18, FR23
**Parallelism:** Starts after Epic 1. Runs in parallel with Epics 2, 3, 5.

### Epic 5: Notifications (Notification-Worker — Slack Only)
All outbound notifications flow through a single Slack-based worker: team channel alerts for new engineering tickets, direct messages to the reporter for non-incident resolutions and bug-fix confirmations.
**FRs covered:** FR19, FR22, FR24
**Parallelism:** Starts after Epic 1. Runs in parallel with Epics 2, 3, 4.

### Epic 6: Observability & Proactive Detection
Every triage decision is logged with structured metadata, traced in Langfuse, and visualizable. The OTEL Collector enables proactive incident detection from eShop telemetry, triggering the agent pipeline automatically.
**FRs covered:** FR26, FR27, FR32
**Parallelism:** Starts after Epic 3 core stories (depends on agent instrumentation). OTEL Collector (Story 6.3) can start after Epic 2 (API endpoint exists).

### Epic 7: Deployment, Integration & Documentation
The complete application runs with a single `docker compose up --build`, all services work together end-to-end, and repository documentation meets hackathon deliverable requirements.
**FRs covered:** FR33, FR36, FR37, FR38, FR39, FR42
**Parallelism:** Final epic — depends on Epics 2-6. Can overlap with Epic 6.

---

## Epic 1: Project Foundation & Service Scaffolding

Bootstrap the multi-service project structure, Docker orchestration, and Redis event infrastructure so that all service teams can begin independent development immediately.

### Story 1.1: Scaffold Project Structure with Docker Compose

As a developer,
I want the complete project directory structure, Dockerfiles, and Docker Compose configuration created per the architecture specification,
So that all service teams can begin independent development with a working containerized environment.

**Acceptance Criteria:**

**Given** a clean clone of the repository
**When** the developer inspects the project structure
**Then** the following directories and files exist per the architecture specification:
- `services/ui/` with Dockerfile and `public/` directory
- `services/api/` with Dockerfile, `requirements.txt`, and `src/` with hexagonal structure (`domain/`, `ports/`, `adapters/inbound/`, `adapters/outbound/`)
- `services/agent/` with Dockerfile, `requirements.txt`, and `src/` with hexagonal structure plus `graph/nodes/` and `graph/tools/`
- `services/ticket-service/` with Dockerfile, `requirements.txt`, and `src/` with hexagonal structure
- `services/notification-worker/` with Dockerfile, `requirements.txt`, and `src/` with hexagonal structure
- `infra/otel-collector-config.yaml` placeholder
**And** `docker-compose.yml` defines all services (ui, api, agent, ticket-service, notification-worker, redis, langfuse, otel-collector) with correct ports and internal networking
**And** `.env.example` contains all environment variables with placeholder values and comments:
```
LLM_MODEL, OPENROUTER_API_KEY, ANTHROPIC_API_KEY,
REDIS_URL, LINEAR_API_KEY, LINEAR_TEAM_ID, LINEAR_WEBHOOK_SECRET,
SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, SLACK_REPORTER_USER_ID,
GITHUB_TOKEN, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
```
**And** each service has a `config.py` that loads environment variables as the single source of truth (never `os.getenv()` inline)
**And** each service's `requirements.txt` lists the correct Python dependencies per the architecture spec
**And** `docker compose up --build` starts all services without errors (services may not do useful work yet; they start and stay alive)

**Given** the developer runs `docker compose up --build`
**When** all containers start
**Then** Redis is accessible on port 6379 (internal), nginx responds on port 8080, and all Python services start without import errors

**Technical Notes:**
- Follow naming conventions from architecture: snake_case for Python, kebab-case for Docker/Redis/API
- Each service's `main.py` should be a minimal entry point that logs "Service {name} started" and stays alive
- Dockerfiles use Python 3.12+ slim images
- nginx Dockerfile serves a placeholder index.html
- No Resend/email dependencies anywhere — Slack is the only notification channel

### Story 1.2: Redis Event Infrastructure & Shared Domain Models

As a developer,
I want a consistent Redis pub/sub event infrastructure with shared message envelope format across all services,
So that every service can publish and consume events using the same contract without coordination.

**Acceptance Criteria:**

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

**Technical Notes:**
- Use `redis.asyncio` for async Redis operations
- Ports define abstract interfaces (`EventPublisher`, `EventConsumer`) in `ports/outbound.py` / `ports/inbound.py`
- Adapters implement the interfaces — domain layer has zero Redis imports
- The Redis consumer in each service runs as an async listener loop in `main.py`
- All event types: `incident.created`, `triage.completed`, `ticket.create`, `ticket.created`, `notification.send`, `ticket.error`, `incident.reescalate`
- `source_type` field distinguishes `userIntegration` from `systemIntegration` — critical for agent behavior

---

## Epic 2: Incident Submission Experience (UI + API)

A reporter can submit an incident report through the web form and receive immediate confirmation that Mila is processing it, with input security applied before data enters the pipeline.

### Story 2.1: Static UI Deployment with nginx

As a reporter,
I want to access the incident submission form through a web browser,
So that I can begin reporting an incident without any setup or authentication.

**Acceptance Criteria:**

**Given** the existing `docs/mila_ui_final_v1.html` static form
**When** the developer copies it to `services/ui/public/index.html`
**Then** the file is served by nginx on port 8080 at the root path `/`

**Given** the nginx configuration
**When** a user navigates to `http://localhost:8080`
**Then** the incident submission form loads with all visual elements (title, description, component dropdown, severity buttons, file upload, Mila hint bar, progress bar)
**And** the form is fully interactive (typing, selecting, uploading preview) even without a backend connected

**Given** the nginx reverse proxy configuration
**When** requests are made to `/api/*`
**Then** they are proxied to the API service at `api:8000`
**And** requests to `/webhooks/linear` are proxied to `ticket-service:8002`
**And** rate limiting is configured on `/api/incidents` (e.g., 10 req/s burst 20)
**And** CORS headers restrict origins appropriately

**Technical Notes:**
- nginx.conf: static files + reverse proxy + rate limiting + CORS
- Only port 8080 is externally exposed from the Docker network (plus Langfuse 3000)
- The static HTML file may need minor adjustments to point form submission at `/api/incidents`

### Story 2.2: API Incident Intake Endpoints

As a system,
I want FastAPI endpoints that receive incident submissions (from UI and OTEL), validate them, and publish events to Redis,
So that incidents enter the processing pipeline reliably regardless of source.

**Acceptance Criteria:**

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

**Technical Notes:**
- Use `python-multipart` for file handling
- FastAPI routes in `adapters/inbound/fastapi_routes.py` — both `/api/incidents` and `/api/webhooks/otel`
- Domain validation in `domain/services.py`
- Redis publishing via `adapters/outbound/redis_publisher.py`
- All env vars via `config.py`
- Shared Docker volume for attachments mounted across API and Agent containers
- Structured JSON logging with `event_id` correlation

### Story 2.3: UI-API Form Submission Integration

As a reporter,
I want to fill out the incident form and submit it, then see a confirmation screen with my tracking ID,
So that I know Mila received my report and is processing it.

**Acceptance Criteria:**

**Given** the reporter has filled in the title field (at minimum)
**When** the reporter clicks the Submit button
**Then** the form sends a POST request to `/api/incidents` with all form data (title, description, component, severity, file)
**And** the severity value from the button selection is captured and sent (the HTML needs a hidden input or JS capture for the active severity button)
**And** the file attachment is sent as multipart form data

**Given** the API returns HTTP 201 with an `incident_id`
**When** the UI processes the response
**Then** the success screen displays with the `incident_id` as the tracking reference (replacing the current random client-side number)
**And** the "Mila is on it" message and "What happens next" steps are shown

**Given** the API returns an error (4xx or 5xx)
**When** the UI processes the error response
**Then** the reporter sees a user-friendly error message (not a raw API error)
**And** the form remains filled so the reporter can retry

**Technical Notes:**
- Modify `submitForm()` in the HTML to make an actual `fetch()` call to `/api/incidents`
- Capture severity from the active button's data attribute
- Handle file as FormData multipart upload
- Replace hardcoded random ticket ID with API-returned `incident_id`
- No email field needed — reporter identity (Slack user ID) is configured server-side via `SLACK_REPORTER_USER_ID`

### Story 2.4: Input Sanitization & Prompt Injection Detection Middleware

As a system,
I want all user-submitted text to be sanitized and checked for prompt injection patterns before it reaches the LLM pipeline,
So that the system is protected against adversarial inputs.

**Acceptance Criteria:**

**Given** any incoming incident submission to `/api/incidents`
**When** the API middleware processes the request
**Then** all text fields (title, description) are sanitized: HTML tags stripped, control characters removed, excessive whitespace normalized
**And** the sanitized text replaces the original in the request before it reaches the route handler

**Given** an incident submission containing prompt injection patterns (e.g., "ignore previous instructions", "you are now", "system:", role-switching attempts)
**When** the middleware detects these patterns
**Then** the input is flagged with a `prompt_injection_detected: true` metadata field in the Redis event (so the Agent can apply extra caution)
**And** the submission is NOT rejected — it is still processed (to avoid false-positive blocking)
**And** a structured warning log is emitted with the pattern type detected

**Given** a benign incident submission
**When** the middleware processes it
**Then** the text passes through sanitization with minimal alteration (only dangerous content removed)
**And** no injection flag is set

**Technical Notes:**
- Implement in `adapters/inbound/middleware.py` as FastAPI middleware
- Simple regex-based pattern matching for common injection phrases
- Sanitization: strip HTML via a lightweight library or regex, remove null bytes and control chars
- This is a hackathon-level guardrail — not a production WAF
- FR29 + FR30 coverage
- Applied only to `/api/incidents` — OTEL webhook payloads are trusted (internal network)

---

## Epic 3: AI Triage & Code Analysis (Agent)

The Agent autonomously consumes incidents, analyzes the eShop codebase via GitHub API, classifies each incident as bug or non-incident with chain-of-thought reasoning, confidence scoring, and severity analysis. It publishes structured commands for downstream services and handles non-incident dismissals directly. Includes advanced agent intelligence: confidence-based decisions, severity interpretation, and misclassification re-escalation.

### Story 3.1: Agent Service Scaffold with Redis Consumer

As a system,
I want the Agent service to continuously consume incident events from the Redis `incidents` channel and initialize processing,
So that every submitted incident is automatically picked up for triage.

**Acceptance Criteria:**

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

**Technical Notes:**
- Redis consumer in `adapters/inbound/redis_consumer.py` runs async listener loop on both `incidents` and `reescalations` channels
- `main.py` wires consumer → domain → graph pipeline
- TriageState dataclass in `domain/models.py` holds all state flowing through pydantic-graph
- LLM provider configured in `config.py` reading `LLM_MODEL`

### Story 3.2: eShop Codebase Analysis Tools (GitHub API)

As an agent,
I want to search and read files from the eShop GitHub repository during triage reasoning,
So that I can identify the source code relevant to reported incidents.

**Acceptance Criteria:**

**Given** the Agent is processing an incident
**When** the agent reasoning loop calls the `search_code` tool with a query string
**Then** the tool executes a GitHub Code Search API request against the `dotnet/eShop` repository
**And** returns a list of matching file paths and code snippets
**And** the agent can iterate — searching, reading results, searching again with refined queries

**Given** the agent calls the `read_file` tool with a file path
**When** the tool executes
**Then** it fetches the full file content from the GitHub Contents API
**And** returns the file content as a string for the agent to analyze

**Given** the GitHub API returns an error (rate limit, 404, timeout)
**When** the tool encounters the error
**Then** it returns a descriptive error message to the agent (not an exception)
**And** the agent can decide to retry, try a different query, or proceed with available information

**Given** a `GITHUB_TOKEN` is configured
**When** the tools make API requests
**Then** the token is used for authentication (higher rate limits)
**And** if no token is configured, tools still work for public repos with lower rate limits

**Technical Notes:**
- Implement as Pydantic AI tools using `@agent.tool` decorator in `graph/tools/search_code.py` and `graph/tools/read_file.py`
- Tools receive dependencies via `RunContext[TriageDeps]` — TriageDeps contains GitHubClient
- GitHubClient outbound adapter in `adapters/outbound/github_client.py` uses httpx.AsyncClient
- GitHub Code Search API: `GET /search/code?q={query}+repo:dotnet/eShop`
- GitHub Contents API: `GET /repos/dotnet/eShop/contents/{path}`
- A pre-written eShop architecture context is included in the agent's system prompt (key directories, service responsibilities)

### Story 3.3a: Triage Graph Scaffold + AnalyzeInput & SearchCode Nodes

As a system,
I want the Agent to define the pydantic-graph triage pipeline and implement the first two nodes (AnalyzeInputNode + SearchCodeNode),
So that incidents are parsed and relevant eShop code is gathered before classification.

**Acceptance Criteria:**

**Given** the pydantic-graph workflow definition
**When** a developer inspects `graph/workflow.py`
**Then** the graph defines four nodes: `AnalyzeInputNode → SearchCodeNode → ClassifyNode → GenerateOutputNode`
**And** edges are defined via return type hints (pydantic-graph pattern)
**And** state flows through `GraphRunContext[TriageState]`

**Given** an incident has been consumed and loaded into `TriageState`
**When** `AnalyzeInputNode` executes
**Then** it parses incident details, extracts key signals, processes multimodal attachments, and updates TriageState

**Given** `AnalyzeInputNode` has populated signal fields
**When** `SearchCodeNode` executes
**Then** it invokes the Pydantic AI Agent with GitHub tools to search eShop codebase and updates TriageState with code context

**Technical Notes:**
- pydantic-graph workflow defined in `graph/workflow.py` with nodes in `graph/nodes/`
- FR7, FR8, FR9 coverage
- ClassifyNode and GenerateOutputNode are stubs until Story 3.3b

### Story 3.3b: ClassifyNode + GenerateOutputNode + System Prompt + Structured Output

As a system,
I want the Agent to classify each incident as bug or non-incident using LLM-powered analysis with structured output, chain-of-thought reasoning, and confidence scoring,
So that the classification is reliable, transparent, auditable, and demonstrates strong analytical capabilities.

**Acceptance Criteria:**

**Given** `SearchCodeNode` has populated code context in TriageState
**When** `ClassifyNode` executes
**Then** it invokes Pydantic AI Agent with `output_type=TriageResult` for structured output
**And** produces classification, confidence, chain-of-thought reasoning, severity assessment

**Given** the LLM returns an invalid or unparseable response
**When** Pydantic AI validation fails
**Then** the agent retries (up to 2 retries), then publishes `ticket.error`

**Given** `ClassifyNode` has produced a TriageResult
**When** `GenerateOutputNode` executes
**Then** it routes based on classification and source_type (Stories 3.4, 3.5, 3.6)

**Given** the system prompt
**When** the LLM processes any incident
**Then** all user input is framed as untrusted data to analyze (never as instructions)
**And** includes eShop architecture context and prompt injection caution when flagged

**Technical Notes:**
- Agent uses `output_type=TriageResult` for structured, validated output
- System prompt in `domain/prompts.py`
- FR10, FR12, FR28, FR31 coverage

### Story 3.4: Triage Command Publishing — Bug Path

As a system,
I want the Agent to publish structured ticket creation commands to Redis when a bug is confirmed,
So that the Ticket-Service can create the engineering ticket without any LLM dependency.

**Acceptance Criteria:**

**Given** the triage pipeline classifies an incident as a **bug**
**When** the generate_output node completes
**Then** the Agent publishes a `ticket.create` event to the `ticket-commands` channel with payload:
- `action`: `"create_engineering_ticket"`
- `title`: generated engineering ticket title with severity prefix (e.g., "[P2] NullReferenceException in OrderController.cs")
- `body`: markdown-formatted ticket body containing:
  - 📍 Affected file(s) and line range(s) from triage
  - 🔍 Probable root cause (one sentence)
  - 🛠️ Suggested investigation/fix step
  - 📋 Original report (description + context)
  - 🔗 Incident tracking ID for correlation
  - 📎 Attachment references
  - 🧠 Triage reasoning chain-of-thought summary (so engineer sees HOW the agent reached its conclusion)
  - 📊 Confidence score and severity assessment
- `severity`: mapped from agent's severity_assessment (P1-P4)
- `labels`: relevant labels (component, classification, `triaged-by-mila`)
- `reporter_slack_user_id`: from the incident data (for downstream notification)
- `incident_id`: correlation to original incident
**And** publishes a `triage.completed` event for observability

**Given** any triage completes
**When** the `triage.completed` event is published
**Then** the event payload includes: `incident_id`, `source_type`, `classification`, `confidence`, reasoning summary (metadata, not raw input), severity_assessment, and duration_ms

**Technical Notes:**
- Publishing via `adapters/outbound/redis_publisher.py`
- All commands follow the standard Redis event envelope
- The `triage.completed` event is for observability logging — no consumer acts on it directly
- The Agent never calls Linear or Slack — it only publishes commands
- FR13, FR28 coverage

### Story 3.5: Proactive Incident Processing (systemIntegration — Always Escalate)

As a system,
I want the Agent to always escalate proactive incidents from OTEL telemetry without the option to dismiss them,
So that telemetry-backed signals are never lost and always result in engineering tickets.

**Acceptance Criteria:**

**Given** the Agent is processing an incident with `source_type: "systemIntegration"`
**When** the triage pipeline runs
**Then** the classification step still performs full code analysis and reasoning (for triage quality)
**But** the final classification is always forced to `bug` regardless of the LLM's assessment
**And** the agent still produces confidence, reasoning, file_refs, root_cause, and suggested_fix normally
**And** a `ticket.create` command is published to `ticket-commands` with the full triage details
**And** the `triage.completed` event includes `"forced_escalation": true` and `source_type: "systemIntegration"`

**Given** a proactive incident from OTEL
**When** the agent formats the ticket body
**Then** the ticket includes a clear indicator: "🤖 Proactive Detection — This incident was auto-detected from production telemetry (not user-reported)"
**And** the OTEL trace metadata (service name, trace ID, status code, error message) is prominently displayed

**Technical Notes:**
- Implemented as a conditional in the `generate_output` graph node: if `source_type == "systemIntegration"`, force bug classification
- The agent's reasoning still runs fully — it adds analysis value even for forced escalations
- No reporter notification for proactive incidents (`reporter_slack_user_id` is null)
- FR25 coverage

### Story 3.6: Non-Incident Dismissal with Reporter Notification (userIntegration Only)

As a reporter,
I want to receive a specific technical explanation via Slack when Mila determines my report is not an incident,
So that I understand why without needing to chase anyone.

**Acceptance Criteria:**

**Given** the triage pipeline classifies an incident as a **non-incident**
**And** the `source_type` is `"userIntegration"`
**When** the generate_output node completes
**Then** the Agent publishes a `notification.send` event directly to the `notifications` channel (NOT through Ticket Service) with:
- `type`: `"reporter_update"`
- `slack_user_id`: from the incident's `reporter_slack_user_id`
- `message`: the specific technical resolution explanation from TriageResult (e.g., "This is expected behavior during the scheduled cache rebuild. Latency normalizes within 10 minutes. See `CatalogApi/Startup.cs` cache configuration.")
- `incident_id`: for correlation
- `confidence`: included so the notification can display the agent's certainty level
- `allow_reescalation`: `true` (enables the "This didn't help" mechanism in the Slack message)

**Given** the agent classifies a non-incident with low confidence (below threshold)
**When** the notification is constructed
**Then** the message includes a caveat: "I'm less certain about this classification. If this doesn't match what you're seeing, please re-escalate."
**And** `allow_reescalation` is set to `true`

**Given** `source_type` is `"systemIntegration"`
**When** classification results in non-incident
**Then** the agent ignores the non-incident classification and forces escalation per Story 3.5

**Technical Notes:**
- The Agent publishes directly to `notifications` channel — this is the key difference from the bug path where Ticket Service publishes notifications
- FR20, FR21 coverage
- No Linear ticket created for non-incidents
- The `allow_reescalation` flag tells the Notification Worker to include a "This didn't help" button in the Slack DM

### Story 3.7: Confidence-Based Decision Quality & Severity Analysis

As a hackathon evaluator,
I want to see the agent self-assess its classification certainty and independently evaluate severity,
So that the demo demonstrates sophisticated analytical and decision-making capabilities.

**Acceptance Criteria:**

**Given** the agent produces a confidence score with every classification
**When** confidence is **above threshold** (configurable, default 0.75)
**Then** the agent proceeds normally with its classification
**And** tickets and notifications reflect high-confidence language

**Given** the agent produces a confidence score **below threshold**
**When** the classification is `bug`
**Then** the engineering ticket includes a `🟡 Low Confidence` indicator
**And** the ticket body includes: "Agent confidence: {score}. This classification may need manual review."
**And** the triage reasoning explicitly states what made the agent uncertain

**Given** confidence is below threshold
**When** the classification is `non_incident` (userIntegration only)
**Then** the Slack DM to the reporter includes the uncertainty caveat
**And** the re-escalation mechanism is emphasized

**Given** the reporter optionally provided a perceived severity
**When** the agent assesses severity independently from code analysis
**Then** the agent's `severity_assessment` in TriageResult contains:
- Agent's severity: P1-P4 with justification based on code impact analysis
- Reporter's input: acknowledged ("Reporter indicated: High")
- Delta explanation: if they differ, the agent explains why (e.g., "Reporter indicated High severity, but code analysis suggests P3 — the affected code path handles a non-critical fallback scenario")

**Given** no severity was provided by the reporter
**When** the agent assesses severity
**Then** severity is based entirely on code analysis with no reference to reporter input

**Technical Notes:**
- Confidence threshold configured via `CONFIDENCE_THRESHOLD` env var in `config.py` (default: 0.75)
- Severity analysis integrated into the `classify` graph node's prompt
- FR11 coverage (confidence scoring), plus demo impact for severity analysis
- This story enhances Stories 3.3, 3.4, and 3.6 with richer agent intelligence

### Story 3.8: Misclassification Re-Escalation Handling

As a reporter,
I want to signal that Mila's non-incident classification was wrong so the issue gets re-evaluated and escalated to engineering,
So that the system corrects its mistakes transparently and doesn't dead-end my report.

**Acceptance Criteria:**

**Given** the Agent receives an `incident.reescalate` event on the `reescalations` channel
**When** the event contains the original `incident_id` and reporter feedback
**Then** the Agent:
1. Loads the original incident data from the event payload
2. Re-initializes the triage pipeline with `TriageState.reescalation = true`
3. Includes the reporter's feedback ("This didn't help") as additional context for the LLM
4. Forces the second-pass classification to `bug` (if the reporter says it's wrong, trust the human)
5. Produces a full triage with enhanced reasoning: "Initial classification was non-incident with confidence {X}. Reporter disagreed — re-analyzing with escalation bias."

**Given** the re-escalation triage completes
**When** the Agent publishes commands
**Then** it publishes a `ticket.create` command with:
- Standard bug ticket fields (file refs, root cause, suggested fix)
- A `🔄 Re-escalated` indicator in the ticket body
- Both the original classification reasoning and the re-escalation context
- Reporter's feedback included
**And** publishes `triage.completed` with `reescalation: true` metadata

**Given** the Slack DM to the reporter
**When** the re-escalation is processed
**Then** the reporter receives a follow-up Slack DM: "Thanks for the feedback. I've re-analyzed your report and escalated it to the engineering team. Ticket: {link}."

**Technical Notes:**
- Re-escalation events arrive on the `reescalations` Redis channel
- The `incident.reescalate` event is published by the API when it receives the Slack interaction callback (Story 5.3 handles the Slack button → API → Redis flow)
- On re-escalation, the agent always creates a ticket — this is a human-override scenario
- Demo impact: shows self-correcting agent behavior, human-in-the-loop design, transparent reasoning
- Journey 4 (Lucia — misclassification recovery) coverage

---

## Epic 4: Ticket Lifecycle Management (Ticket-Service)

The Ticket-Service consumes ticket commands from Redis, creates engineering tickets in Linear with full triage details, publishes notification events on success, and handles resolution lifecycle via Linear webhooks.

### Story 4.1: Ticket-Service Scaffold with Redis Consumer & Webhook Listener

As a system,
I want the Ticket-Service to consume ticket commands from Redis and receive webhook events from Linear,
So that it can act as the single owner of all Linear ticket operations.

**Acceptance Criteria:**

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

**Technical Notes:**
- Dual inbound adapters: `redis_consumer.py` (async listener) + `webhook_listener.py` (FastAPI on port 8002)
- `main.py` starts both the Redis consumer loop and the FastAPI webhook server concurrently (using asyncio)
- Linear webhook secret verification in `webhook_listener.py`
- All env vars via `config.py`: `LINEAR_API_KEY`, `LINEAR_TEAM_ID`, `LINEAR_WEBHOOK_SECRET`, `REDIS_URL`

### Story 4.2: Engineering Ticket Creation in Linear

As an SRE engineer,
I want an engineering ticket automatically created in Linear with file references, root cause, and suggested fix from the agent's triage,
So that I can start investigating immediately without back-and-forth.

**Acceptance Criteria:**

**Given** the Ticket-Service consumes a `ticket.create` event with `action: "create_engineering_ticket"`
**When** the service processes the command
**Then** it creates a ticket in the Linear Engineering Board with:
- **Title:** Agent-generated title with severity prefix (e.g., "[P2] NullReferenceException in OrderController.cs")
- **Body (markdown):** The pre-formatted body from the Agent containing:
  - 📍 Affected file(s) and line range(s)
  - 🔍 Probable root cause
  - 🛠️ Suggested investigation/fix
  - 📋 Original report
  - 🔗 Incident tracking ID
  - 📎 Attachment references
  - 🧠 Triage reasoning summary
  - 📊 Confidence and severity assessment
  - 🤖 Proactive detection indicator (if systemIntegration source)
  - 🔄 Re-escalation context (if re-escalated)
- **Labels:** Component, severity, `triaged-by-mila`
- **Priority:** Mapped from agent's severity assessment

**Given** ticket creation succeeds
**When** the Linear API returns the created ticket
**Then** the Ticket-Service publishes a `notification.send` event to the `notifications` channel with:
- `type: "team_alert"`
- Linear ticket URL, severity, component, summary
- `reporter_slack_user_id`: from the ticket command (for reporter update)

**Given** ticket creation succeeds and `reporter_slack_user_id` is not null
**When** the notification event is constructed
**Then** a second `notification.send` event is published with:
- `type: "reporter_update"`
- `slack_user_id`: the reporter's Slack user ID
- `message`: "Your incident report has been received and escalated to the engineering team. Tracking ID: {incident_id}"

**Given** the Linear API is unavailable or returns an error
**When** the Ticket-Service attempts to create the ticket
**Then** it retries up to 2 times with exponential backoff
**And** if all retries fail, publishes a `ticket.error` event
**And** does NOT publish any notification events

**Technical Notes:**
- Linear API client in `adapters/outbound/linear_client.py` using httpx.AsyncClient
- Single Engineering Board — configured via `LINEAR_TEAM_ID`
- FR5, FR14-18 coverage
- AR10: notification published ONLY after Linear API success
- No helpdesk ticket — reporter notification via Slack DM only

### Story 4.3: Resolution Lifecycle — Linear Webhook to Reporter Notification

As a reporter,
I want to be automatically notified via Slack when an engineer resolves the bug I reported,
So that I know my issue is fixed without checking ticket status.

**Acceptance Criteria:**

**Given** an engineer marks an engineering ticket as "Done" or "Resolved" in Linear
**When** Linear fires a webhook to `POST /webhooks/linear` on the Ticket-Service
**Then** the Ticket-Service:
1. Verifies the webhook HMAC signature
2. Extracts the incident_id from the ticket body or metadata
3. Publishes a `notification.send` event with `type: "reporter_resolved"` containing:
   - `slack_user_id`: the reporter's Slack user ID (extracted from ticket metadata)
   - `message`: "Your reported incident '{title}' has been resolved by the engineering team."
   - `incident_id`: for correlation
   - `ticket_url`: link to the resolved Linear ticket

**Given** the webhook arrives for a non-tracked ticket or a duplicate resolution
**When** the Ticket-Service processes it
**Then** it ignores the webhook and logs an informational entry (no duplicate notifications)

**Technical Notes:**
- FR23, FR24 coverage
- Webhook listener in `adapters/inbound/webhook_listener.py`
- The relationship between ticket and incident_id must be stored in the Linear ticket body or a lightweight Redis lookup keyed by Linear ticket ID
- No polling — real-time via Linear webhooks
- No Agent involvement — this is a deterministic pipeline
- For proactive incidents (no reporter_slack_user_id), no reporter notification is sent — only the `triage.completed` observability log

---

## Epic 5: Notifications (Notification-Worker — Slack Only)

All outbound notifications flow through a single Slack-based worker: team channel alerts for new engineering tickets, direct messages to the reporter for non-incident resolutions, escalation confirmations, and bug-fix notifications.

### Story 5.1: Notification-Worker Scaffold with Redis Consumer

As a system,
I want the Notification-Worker to consume notification events from Redis and route them to the appropriate Slack delivery method,
So that all outbound messaging flows through a single service.

**Acceptance Criteria:**

**Given** the Notification-Worker is running and connected to Redis
**When** a `notification.send` event is published to the `notifications` channel
**Then** the worker consumes it within 5 seconds
**And** deserializes the payload into a `Notification` domain model
**And** routes to the correct handler based on notification `type`:
- `team_alert` → Slack channel message
- `reporter_update` → Slack DM to reporter (non-incident, escalation confirmation)
- `reporter_resolved` → Slack DM to reporter (bug fixed)

**Given** the worker receives a notification with an unknown type
**When** routing fails
**Then** it logs a structured warning and skips the notification (no crash)

**Technical Notes:**
- Redis consumer in `adapters/inbound/redis_consumer.py`
- Domain routing logic in `domain/services.py`
- `main.py` starts the async consumer loop
- All env vars via `config.py`: `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `REDIS_URL`

### Story 5.2: Slack Team Channel Notifications

As an SRE team lead,
I want the engineering team to receive a Slack channel notification when a new engineering ticket is created,
So that the team is alerted immediately and can assign the issue.

**Acceptance Criteria:**

**Given** the Notification-Worker consumes a `notification.send` event with `type: "team_alert"`
**When** the Slack adapter sends the message
**Then** a formatted message is posted to the configured Slack channel with:
- Severity indicator (emoji prefix: 🔴 P1, 🟠 P2, 🟡 P3, 🔵 P4)
- Incident title
- Affected component
- One-line root cause summary
- Confidence score
- Link to the engineering ticket in Linear
- Source indicator: "👤 User-reported" or "🤖 Proactive OTEL detection"

**Given** the Slack API is unreachable or returns an error
**When** the adapter encounters the failure
**Then** it retries once after 2 seconds
**And** if retry fails, logs a structured error (does not crash, does not block other notifications)

**Technical Notes:**
- Slack adapter in `adapters/outbound/slack_client.py` using `slack-sdk`
- Uses `chat_postMessage` API with Block Kit formatting for rich messages
- `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID` from `config.py`
- FR19 coverage

### Story 5.3: Slack Direct Message to Reporter

As a reporter,
I want to receive personalized Slack DMs for every lifecycle event related to my incident,
So that I'm always informed without checking any external system.

**Acceptance Criteria:**

**Given** the Notification-Worker consumes a `notification.send` event with `type: "reporter_update"`
**When** the Slack adapter sends the DM
**Then** the configured reporter receives a Slack DM with the appropriate message:
- **Non-incident resolution:** The technical explanation from the Agent + confidence level
- **Escalation confirmation:** "Your incident has been escalated to engineering. Tracking ID: {incident_id}"
- **Re-escalation confirmation:** "Thanks for the feedback. I've re-analyzed your report and escalated it. Ticket: {link}."

**Given** the notification has `allow_reescalation: true`
**When** the Slack DM is sent for a non-incident resolution
**Then** the message includes a Slack interactive button: "❌ This didn't help — Re-escalate"
**And** when the reporter clicks the button, Slack sends an interaction payload to a configured callback URL

**Given** the Slack interaction callback fires (reporter clicks "This didn't help")
**When** the API receives the Slack interaction webhook at `/api/webhooks/slack`
**Then** the API publishes an `incident.reescalate` event to the `reescalations` Redis channel with the original `incident_id` and reporter feedback
**And** the Slack message is updated to show "🔄 Re-escalation in progress..."

**Given** the Notification-Worker consumes a `notification.send` event with `type: "reporter_resolved"`
**When** the Slack adapter sends the DM
**Then** the reporter receives: "Your reported incident '{title}' has been resolved by the engineering team. 🎉"
**And** the Linear ticket link is included

**Given** the Slack API fails to send a DM
**When** the adapter encounters the error
**Then** it logs a structured error and continues processing other notifications

**Technical Notes:**
- Slack DMs use `chat_postMessage` with the reporter's `slack_user_id` as the channel parameter
- `SLACK_REPORTER_USER_ID` is configured in env vars (hardcoded for demo — always the same person)
- Slack interactive messages require a Slack app with Interactivity enabled and a Request URL pointed at the API
- The API needs a `/api/webhooks/slack` endpoint to receive Slack interaction payloads → publish `incident.reescalate` events
- This endpoint should be added to the API service (Story 2.2 can be extended, or this interaction handling lives in the Notification Worker's domain)
- FR22, FR24 coverage + re-escalation mechanism

---

## Epic 6: Observability & Proactive Detection

Every triage decision is logged with structured metadata, traced in Langfuse, and visualizable. The OTEL Collector enables proactive incident detection from eShop telemetry, triggering the agent pipeline automatically.

### Story 6.1: Structured Decision Logging Across Pipeline

As a team lead (Diego),
I want every triage decision logged with structured metadata — classification, confidence, reasoning, and timing — without raw user input,
So that I can review triage quality and spot low-confidence decisions.

**Acceptance Criteria:**

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

**Technical Notes:**
- FR26, FR32 coverage
- Structured JSON logging to stdout in all services (Docker collects)
- Each service already correlates via `event_id` from Redis envelope
- NFR5, NFR13 coverage

### Story 6.2: Langfuse Integration for LLM Tracing

As a system,
I want all LLM calls, tool usage, and reasoning chains traced in Langfuse,
So that triage quality can be visualized, debugged, and demonstrated to hackathon judges.

**Acceptance Criteria:**

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

**Technical Notes:**
- FR27 coverage
- Pydantic AI has native OpenTelemetry instrumentation — Langfuse can consume via OTEL
- Langfuse Python SDK with `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` from config
- Langfuse Docker service already defined in docker-compose.yml from Story 1.1

### Story 6.3: OTEL Collector for Proactive eShop Error Detection

As a system,
I want the OTEL Collector to receive traces from the eShop Aspire application, filter for errors, and webhook them to the API as auto-generated incidents,
So that Mila can proactively detect infrastructure issues without human reporting.

**Acceptance Criteria:**

**Given** eShop is running with .NET Aspire and producing OTEL traces
**When** an error trace is detected (e.g., HTTP 500, exception, timeout)
**Then** the OTEL Collector filters the trace and sends a webhook to `POST /api/webhooks/otel` on the API service

**Given** the API receives an OTEL error webhook
**When** it processes the webhook payload
**Then** it creates an `incident.created` event with `source_type: "systemIntegration"` and publishes to Redis `incidents` channel
**And** the incident includes: error message, service name, trace ID, status code, timestamp
**And** `reporter_slack_user_id` is null

**Given** the Agent consumes an OTEL-sourced incident
**When** it triages the incident
**Then** the same triage pipeline runs per Story 3.5 (always escalated, full analysis)

**Technical Notes:**
- OTEL Collector config in `infra/otel-collector-config.yaml`
- Receives from eShop Aspire via OTLP protocol
- Uses OTEL Collector processors to filter for error spans
- Exports via webhook exporter to API internal endpoint
- API endpoint `POST /api/webhooks/otel` already created in Story 2.2
- This enables the "Path 2 — Proactive OTEL Detection" differentiator

---

## Epic 7: Deployment, Integration & Documentation

The complete application runs with a single `docker compose up --build`, all services work together end-to-end, and repository documentation meets hackathon deliverable requirements.

### Story 7.1: Docker Compose Finalization & Security Hardening

As a developer,
I want the Docker Compose configuration to be production-ready with health checks, proper network isolation, and security hardening,
So that `docker compose up --build` from a clean clone produces a fully working, secure application.

**Acceptance Criteria:**

**Given** a clean clone of the repository with a populated `.env` file
**When** the developer runs `docker compose up --build`
**Then** all services start in the correct order (Redis first, then services, then UI)
**And** health checks verify each service is ready before dependents start
**And** only port 8080 (nginx) and port 3000 (Langfuse) are exposed externally
**And** all inter-service communication stays on the internal Docker network
**And** the shared attachment volume is mounted on API and Agent containers

**Given** the security configuration
**When** the application is running
**Then** nginx rate-limits `/api/incidents` to prevent abuse
**And** CORS restricts origins
**And** the Linear webhook endpoint verifies HMAC signatures
**And** all credentials are loaded from env vars (none hardcoded)

**Technical Notes:**
- FR33, FR40, FR41 coverage
- NFR18, NFR19, NFR20 coverage
- Docker Compose `depends_on` with health check conditions
- Network: `internal` network for all services, only nginx published port

### Story 7.2: End-to-End Pipeline Integration Validation

As a team,
I want to verify the complete incident lifecycle works end-to-end across all services,
So that we can confidently demo the full flow.

**Acceptance Criteria:**

**Given** all services are running via Docker Compose
**When** a reporter submits a bug report through the UI (e.g., "Checkout 500 errors — NullReferenceException in OrderController")
**Then** the full bug path executes:
1. UI → API → Redis (`incident.created`, `source_type: "userIntegration"`)
2. Agent consumes → triages → classifies as bug with confidence and severity
3. Agent → `ticket.create` → Ticket Service → Linear engineering ticket created
4. Ticket Service → `notification.send` → Notification Worker → Slack channel alert + Slack DM to reporter
**And** total time is under 3 minutes (NFR2)

**Given** eShop produces an error trace via OTEL
**When** the OTEL Collector webhooks to the API
**Then** the proactive path executes:
1. OTEL Collector → API → Redis (`incident.created`, `source_type: "systemIntegration"`)
2. Agent consumes → triages → always escalated
3. Agent → `ticket.create` → Ticket Service → Linear ticket
4. Ticket Service → `notification.send` → Slack channel alert (no reporter DM)

**Given** a reporter submits a non-incident (e.g., "Catalog API latency spike" — expected cache warm-up)
**When** the agent classifies as non-incident
**Then** the non-incident path executes:
1. Agent → `notification.send` directly to Notification Worker
2. Notification Worker → Slack DM to reporter with technical explanation + "This didn't help" button
**And** total time is under 2 minutes (NFR1)

**Given** the reporter clicks "This didn't help" on the Slack DM
**When** the re-escalation triggers
**Then** the re-escalation path executes:
1. Slack interaction → API → Redis `reescalations` channel
2. Agent re-processes → forces bug classification → publishes `ticket.create`
3. Ticket Service → Linear ticket → Notification Worker → Slack DM confirmation

**Given** an engineer resolves a ticket in Linear
**When** Linear fires the resolution webhook
**Then** the resolution path executes:
1. Linear → Ticket Service → `notification.send` (reporter_resolved)
2. Notification Worker → Slack DM to reporter

**Technical Notes:**
- This is a validation story — run all demo scenarios, fix any integration gaps
- Test with actual Linear, Slack, and GitHub API
- Test confidence threshold behavior: submit a borderline case and verify low-confidence indicators
- Verify severity analysis appears in tickets (both with and without reporter-provided severity)

### Story 7.3: Repository Documentation

As a hackathon evaluator,
I want clear documentation that explains the architecture, how to set up the project, and how agents are used,
So that I can evaluate the project's technical quality and reproduce the demo.

**Acceptance Criteria:**

**Given** the repository root
**When** the evaluator checks for required files
**Then** the following files exist with complete content:

**README.md** contains:
- Project summary (what mila does)
- Architecture diagram (mermaid or image) showing services, Redis bus, Linear, Slack, OTEL
- Tech stack summary
- Setup instructions (prerequisites, env vars, docker compose)
- Demo scenarios (bug path, proactive path, non-incident path, re-escalation)

**AGENTS_USE.md** contains:
- Agent description and capabilities
- How the triage pipeline works (pydantic-graph nodes, classification, confidence, severity)
- Tool usage (search_code, read_file via GitHub API)
- Advanced agent intelligence: confidence-based decisions, severity analysis, re-escalation handling
- Observability evidence (Langfuse traces)
- Safety measures (input sanitization, prompt hardening, untrusted-input boundary)
- Responsible AI alignment

**SCALING.md** contains:
- Current architecture constraints
- Horizontal scaling strategy (stateless agent, Redis pub/sub → streams)
- Multi-codebase support path
- Production hardening considerations

**QUICKGUIDE.md** contains:
- Step 1: Clone repository
- Step 2: Copy `.env.example` to `.env`, fill in API keys (Linear, Slack, GitHub, LLM provider)
- Step 3: `docker compose up --build`
- Step 4: Open `http://localhost:8080` to submit an incident
- Step 5: Check Linear for tickets, Slack for alerts and DMs
- Step 6: Open `http://localhost:3000` for Langfuse traces

**LICENSE** — MIT (already exists)

**Technical Notes:**
- FR36-39, FR42 coverage
- Documentation should be concise and evaluator-focused
- Architecture diagram should match the actual implementation
- Highlight agent intelligence features (confidence, severity, re-escalation) in AGENTS_USE.md

---

## Dependency Graph Summary

```
Story 1.1 ──▸ Story 1.2 ──┬──▸ Epic 2 (Stories 2.1→2.2→2.3→2.4)  [UI PATH - PRIORITY]
                           ├──▸ Epic 3 (Stories 3.1→3.2→3.3a→3.3b→3.4→3.5→3.6→3.7→3.8) [PARALLEL]
                           ├──▸ Epic 4 (Stories 4.1→4.2→4.3)       [PARALLEL]
                           └──▸ Epic 5 (Stories 5.1→5.2→5.3)       [PARALLEL]
                                    │
                           Epic 6 (Stories 6.1→6.2→6.3)            [After E3 core]
                                    │
                           Epic 7 (Stories 7.1→7.2→7.3)            [Final]
```

**Parallel Workstream Assignment:**

| Workstream | Epic | Service | Can start after |
|---|---|---|---|
| **WS-1 (PRIORITY)** | Epic 2 | UI + API | Story 1.2 |
| **WS-2** | Epic 3 | Agent | Story 1.2 |
| **WS-3** | Epic 4 | Ticket-Service | Story 1.2 |
| **WS-4** | Epic 5 | Notification-Worker | Story 1.2 |

Four developers/agents can work simultaneously after the 2-story foundation is complete.

### Story Priority Order (within each epic)

**Epic 3 internal priority (highest → lowest):**
1. 3.1–3.4: Bug classification + ticket command (core MVP)
2. 3.5: Proactive incident handling (OTEL differentiator)
3. 3.6: Non-incident dismissal (edge case)
4. 3.7: Confidence + severity analysis (agent intelligence polish)
5. 3.8: Re-escalation handling (agent intelligence polish)

**Cross-epic integration order:**
1. UI → API → Redis → Agent → Ticket Service → Slack (valid bug E2E)
2. OTEL → API → Agent → Ticket Service → Slack (proactive E2E)
3. Agent → Slack DM (non-incident dismissal E2E)
4. Slack button → API → Agent → Ticket Service → Slack (re-escalation E2E)
5. Linear webhook → Ticket Service → Slack DM (resolution E2E)
