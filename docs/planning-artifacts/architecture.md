---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
inputDocuments: [docs/planning-artifacts/prd.md, docs/agent-x-hackathon-2026.md, docs/AGENTS_USE.md]
workflowType: 'architecture'
lastStep: 8
status: 'complete'
completedAt: '2026-04-07'
project_name: 'mila'
user_name: 'sebas'
date: '2026-04-07'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
42 FRs across 9 categories covering the full incident lifecycle: submission (FR1-6), triage & classification (FR7-12), bug handling (FR13-19), misuse handling (FR20-22), resolution lifecycle (FR23-25), observability (FR26-28), guardrails (FR29-32), deployment (FR33-35), and repository deliverables (FR36-42).

The architectural spine is the event-driven pipeline: UI → Helpdesk Ticket → Agent Trigger → Triage (multimodal LLM + codebase analysis) → Classification → Bug Path or Misuse Path → Lifecycle Notifications.

**Non-Functional Requirements:**
- Performance: Misuse path < 2 min, Bug path < 3 min, Agent trigger < 30s of ticket creation
- Security: Input sanitization before LLM, metadata-only logging, env-var credentials
- Integration reliability: Graceful failure handling for all external APIs (Linear, Slack, LLM)
- Observability: Every pipeline stage produces trace/log entries; reasoning is human-readable
- Deployment: Single `docker compose up --build` from clean clone

**Scale & Complexity:**
- Primary domain: AI agent backend + static web frontend
- Complexity level: Medium
- Estimated architectural components: 5-7 (UI static server, agent service, Linear integration, Slack integration, codebase analyzer, observability pipeline, Docker orchestration)

### Technical Constraints & Dependencies

- **2-day build sprint** — architecture must minimize complexity while delivering full E2E flow
- **Event-driven decoupling** — UI and agent are separate services; agent reacts to Redis events
- **Real integrations required** — Linear API, Slack API, eShop codebase access, observability platform
- **Docker Compose deployment** — all services containerized, no host dependencies beyond Docker
- **Multimodal LLM dependency** — requires a provider supporting text + image/log input
- **eShop codebase** — agent needs a strategy to read and analyze .NET source code efficiently
- **No authentication** — demo context only, anonymous submission

### Cross-Cutting Concerns Identified

- **Observability** — Structured decision logging at every pipeline stage, dual-purpose (ops + product feature)
- **Error handling** — No integration failure should crash the pipeline or leave tickets in inconsistent state
- **Input sanitization** — All user content treated as untrusted before reaching LLM
- **Credential management** — All secrets via environment variables, `.env.example` with placeholders
- **Responsible AI** — Transparent reasoning in every ticket/resolution, classification explainability

## Starter Template & Tech Stack Evaluation

### Primary Technology Domain

**Python AI agent backend + static web frontend** — based on project requirements analysis. The system is an event-driven AI pipeline with a thin static UI, not a traditional web application. Python is the natural choice given the dominance of AI/ML tooling in the ecosystem.

### Tech Stack Decisions

| Layer | Technology | Rationale |
|---|---|---|
| **Language** | Python 3.12+ | AI agent ecosystem, Pydantic AI native, team preference |
| **Agent Orchestration** | Pydantic AI + pydantic-graph | Type-safe agent framework with graph-based pipeline modeling, native conditional branching via return type hints, structured output via `output_type=`, dependency injection, model-agnostic (OpenRouter/Anthropic as native model strings), OTel-native observability |
| **API Service** | FastAPI | Async-native, lightweight, fast to build, handles form submission + webhook receiver + lifecycle events |
| **UI Server** | nginx | Static file server for existing HTML form (`mila_ui_final_v1.html`), no framework needed |
| **LLM Providers** | OpenRouter / Anthropic Claude | Hackathon evaluator preference, configurable via env var, Pydantic AI native model string swap |
| **Ticketing** | Linear | Native webhooks for real-time status detection, clean REST API, free unlimited tier, hackathon-listed |
| **Team Notifications** | Slack | Real-time communicator, satisfies hackathon "email and/or communicator" requirement |

| **Message Bus** | Redis | Decouples all services, event-driven architecture, demonstrates scalable design |
| **Agent Observability** | Langfuse (self-hosted) | Purpose-built LLM tracing, open source, Docker-native, OTel-native via Pydantic AI instrumentation, free |
| **eShop Observability** | Aspire Dashboard (built-in) | eShop uses .NET Aspire which includes traces, logs, metrics dashboard out of the box |
| **Error Detection** | OTEL Collector | Routes eShop error traces to API webhook for proactive incident detection |
| **Code Analysis** | GitHub API | Search + read eShop source code at runtime, production-credible approach |
| **Containerization** | Docker Compose | All services orchestrated, single `docker compose up --build` |

### LLM Provider Abstraction

Pydantic AI's native model strings enable zero-code-change provider swapping via a single environment variable:

```python
# OpenRouter (default — free tier available)
LLM_MODEL=openrouter:google/gemma-4
OPENROUTER_API_KEY=...

# Anthropic
LLM_MODEL=anthropic:claude-sonnet-4-20250514
ANTHROPIC_API_KEY=...
```

Pydantic AI resolves the provider from the model string prefix — no factory pattern or adapter layer needed. The agent code simply reads `config.LLM_MODEL` and passes it to `Agent(model=...)`.

### Architectural Components

| # | Component | Type | Docker Service | Port |
|---|---|---|---|---|
| 1 | **UI Server** | nginx static server | `ui` | 8080 |
| 2 | **API Service** | FastAPI application | `api` | 8000 |
| 3 | **Agent** | Python + Pydantic AI + pydantic-graph | `agent` | internal |
| 4 | **Ticket Service** | Python worker | `ticket-service` | internal |
| 5 | **Notification Worker** | Python worker | `notification-worker` | internal |
| 6 | **Redis** | Message bus | `redis` | 6379 |
| 7 | **Langfuse** | LLM observability | `langfuse` | 3000 |
| 8 | **OTEL Collector** | Trace routing | `otel-collector` | 4317 |
| 9+ | **eShop** | Target app (Aspire) | via `dotnet run` | Aspire defaults |

**Component Separation Rationale:**
- **UI Server** — pure static hosting, no business logic
- **API Service** — single HTTP entry point: receives UI form submissions, OTEL error webhooks, Linear resolution webhooks. Publishes all events to Redis. Never calls external APIs except Redis.
- **Agent** — pure LLM reasoning engine. Consumes incidents from Redis, analyzes code via GitHub API (in-process tool for iterative reasoning), publishes structured commands to Redis. Never calls Linear or Slack directly. Uses Pydantic AI Agent with `output_type=TriageResult` and pydantic-graph for state machine orchestration.
- **Ticket Service** — consumes ticket commands from Redis, executes against Linear API. On success, publishes notifications to Redis. On failure, publishes errors. Deterministic, no LLM.
- **Notification Worker** — consumes notification events from Redis, sends Slack messages (channel alerts + DMs). Deterministic, no LLM.
- **Redis** — central message bus. All inter-service communication flows through Redis channels.
- **Langfuse** — traces Agent LLM calls, tool usage, reasoning chains
- **OTEL Collector** — receives eShop Aspire traces, filters errors, webhooks to API for proactive detection

### Starter Template Approach

No off-the-shelf starter template — this is a **custom multi-service Python project**. The architecture is initialized as:

```
mila/
├── docker-compose.yml
├── .env.example
├── services/
│   ├── ui/                      # nginx + static HTML
│   │   ├── Dockerfile
│   │   └── public/
│   │       └── index.html       # mila_ui_final_v1.html
│   ├── api/                     # FastAPI service
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   ├── agent/                   # Pydantic AI triage agent
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   ├── ticket-service/          # Linear ticket worker
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   └── notification-worker/     # Slack worker
│       ├── Dockerfile
│       ├── requirements.txt
│       └── src/
├── infra/
│   └── otel-collector-config.yaml
├── docs/
├── README.md
├── AGENTS_USE.md
├── SCALING.md
├── QUICKGUIDE.md
└── LICENSE
```

### Key Python Dependencies

**API Service:**
- `fastapi`, `uvicorn` — web framework + ASGI server
- `redis` (redis-py) — publish events to Redis
- `httpx` — async HTTP client
- `python-multipart` — file upload handling

**Agent Service:**
- `pydantic-ai` — agent framework (includes pydantic-graph, model-agnostic LLM abstraction)
- `pydantic-graph` — graph-based state machine for triage pipeline (included with pydantic-ai)
- `redis` — consume incidents, publish commands
- `httpx` — GitHub API calls (in-process reasoning tool)
- `langfuse` — LLM observability SDK

**Ticket Service:**
- `redis` — consume ticket commands, publish notifications/errors
- `httpx` — Linear API calls

**Notification Worker:**
- `redis` — consume notification events
- `slack-sdk` — Slack API

**Note:** Project initialization (scaffolding the folder structure, Dockerfiles, and base configurations) should be the first implementation story.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- Event-driven architecture with Redis message bus
- Agent as pure reasoning engine, decoupled from external systems
- Separation of reasoning (Agent) from execution (Ticket Service, Notification Worker)
- GitHub API for runtime codebase analysis (not clone + index)
- Linear for ticketing with native webhooks

**Important Decisions (Shape Architecture):**
- Two intake paths: UI form (required) + OTEL proactive detection (differentiator)
- Slack as team communicator (real-time, satisfies hackathon requirement)
- OTEL Collector for eShop error routing (leverages Aspire's built-in telemetry)

**Deferred Decisions (Post-MVP / SCALING.md):**
- Horizontal scaling of agent instances
- Multi-codebase support beyond eShop
- Learning from resolution patterns
- Additional ticketing system integrations

### Event-Driven Architecture

**Decision:** All inter-service communication flows through Redis as a message bus. No service calls another service directly via HTTP (except Agent → GitHub API for iterative reasoning).

**Redis Channels:**

| Channel | Publisher | Consumer | Payload |
|---|---|---|---|
| `incidents` | API (form + OTEL webhook) | Agent | `{source, title, description, attachments, reporter_slack_user_id, trace_data}` |
| `ticket-commands` | Agent | Ticket Service | `{action: "create", title, body, severity, labels, reporter_ref}` |
| `notifications` | Ticket Service, API | Notification Worker | `{type: "team_alert"\|"reporter_dm", channel, slack_user_id, message}` |
| `errors` | Ticket Service | Logging | `{service, error, context}` |

**Rationale:** Decouples all components. Agent can be scaled independently. Ticket creation failures don't cascade into false notifications. Every service has a single responsibility.

### Agent Design — Brain vs. Hands

**Decision:** The Agent is a pure LLM reasoning engine. It consumes incident events, reasons about them (code analysis, classification, content generation), and publishes structured commands to Redis. It never calls Linear or Slack.

**Agent In-Process Tools (part of reasoning loop):**
- `search_code` → GitHub API — iterative code search during triage
- `read_file` → GitHub API — read specific source files for analysis

**Agent Output Commands (via Redis, executed by workers):**
- `ticket-commands` → Ticket Service executes against Linear
- `notifications` → triggered by Ticket Service on success (not by Agent directly)

**Rationale:** GitHub API calls are thinking tools — the agent searches, reads, thinks, searches again. This iterative loop can't be decoupled. Linear/Slack are execution — deterministic, no LLM needed, and must respect error handling (e.g., don't notify if ticket creation failed).

### Codebase Analysis Strategy

**Decision:** GitHub API at runtime (search + read files). No cloning, no vector store, no local indexing.

**How it works:**
1. Agent receives incident with error details
2. Agent calls `search_code(query, repo:"dotnet/eShop")` via GitHub Code Search API
3. Agent reads relevant files via GitHub Contents API
4. Agent reasons over code + incident data to produce root cause analysis

**Supplemented by:** A pre-written eShop architecture context file (key directories, service responsibilities, common patterns) in the agent's system prompt — simulating the runbooks and architecture docs real SRE teams maintain.

**Rationale:** Production-credible. Real SRE agents query SCM APIs, not clone entire repos. No infrastructure overhead. GitHub API is free for public repos.

### Ticketing System

**Decision:** Linear (replaces Notion from initial PRD).

**Rationale:**
- Native outbound webhooks — when ticket status changes to "Done", Linear calls API webhook instantly
- Eliminates polling entirely for resolution detection
- Clean REST API, free unlimited tier
- Explicitly listed in hackathon brief as accepted ticketing system

### Dual Intake Architecture

**Decision:** Two paths into the same pipeline, both publishing to Redis `incidents` channel.

**Path 1 — UI Form (Required by hackathon):**
```
User submits form → API receives POST → API publishes to Redis:incidents
```

**Path 2 — Proactive OTEL Detection (Differentiator):**
```
eShop error → OTEL Collector detects → webhook to API → API publishes to Redis:incidents
```

Agent consumes from Redis regardless of source. Same triage pipeline for both.

**eShop runs via .NET Aspire** with built-in observability (Aspire Dashboard). OTEL Collector receives a copy of eShop traces and filters for errors.

### Resolution Notification (Real-Time)

**Decision:** Linear webhook → API → Redis → Notification Worker → Slack DM to reporter. No polling. No agent involved.

**Flow:**
```
Engineer resolves ticket in Linear
  → Linear fires webhook to API
  → API publishes to Redis:notifications
  → Notification Worker sends Slack DM to reporter
```

**Rationale:** Resolution notification is deterministic — no LLM reasoning needed. Direct pipeline. Real-time via Linear webhooks.

### Notification Chain — Error Safety

**Decision:** Notifications are only sent AFTER ticket creation succeeds. Ticket Service controls this.

**Flow:**
```
Agent → Redis:ticket-commands → Ticket Service → Linear API
                                      │
                                 success? ─── yes → Redis:notifications → Notification Worker → Slack
                                      │
                                      └──── no  → Redis:errors (logged, no notification)
```

**Rationale:** If Linear API fails, the team should NOT receive a Slack message about a ticket that doesn't exist.

### Service Responsibility Matrix

| Service | Does | Does NOT |
|---|---|---|
| **API** | Receives UI form submissions and OTEL error webhooks, publishes events to Redis | Call Linear, Slack, or receive Linear webhooks |
| **Agent** | LLM reasoning, code analysis via GitHub API, publishes structured commands to Redis | Call Linear or Slack directly |
| **Ticket Service** | Executes ticket operations on Linear, receives Linear status webhooks, publishes notifications on success | Send Slack messages or make LLM decisions |
| **Notification Worker** | Sends Slack messages (channel alerts + DMs) | Create tickets, make decisions, or call LLMs |

### Observability Architecture

| Traces From | Platform | Purpose |
|---|---|---|
| eShop services | **Aspire Dashboard** (built-in) | eShop APM: HTTP requests, DB queries, service latency, exceptions |
| OTEL Collector | Receives from Aspire, filters errors → API webhook | Proactive error detection bridge |
| Mila Agent | **Langfuse** (self-hosted) | LLM traces: prompts, reasoning, tool calls, token usage, classification decisions |

### LLM Provider Configuration

Three providers, swappable via environment variable:

| Provider | Use Case | Config |
|---|---|---|
| OpenRouter | Default — free tier available (e.g., Gemma 4) | `LLM_MODEL=openrouter:google/gemma-4` |
| Anthropic Claude | Premium inference | `LLM_MODEL=anthropic:claude-sonnet-4-20250514` |

### Docker Services Summary

| # | Service | Type | LLM? | Port |
|---|---|---|---|---|
| 1 | `ui` | nginx (API gateway + static) | No | 8080 (only externally exposed) |
| 2 | `api` | FastAPI | No | 8000 (internal) |
| 3 | `agent` | Pydantic AI + pydantic-graph | ✅ Yes | internal |
| 4 | `ticket-service` | Python worker + webhook listener | No | 8002 (internal) |
| 5 | `notification-worker` | Python worker | No | internal |
| 6 | `redis` | Message bus | No | 6379 (internal) |
| 7 | `langfuse` | LLM observability | No | 3000 (dashboard) |
| 8 | `otel-collector` | Trace routing | No | 4317 (internal) |
| 9+ | eShop (Aspire) | Target application | No | Aspire defaults |

## Implementation Patterns & Consistency Rules

### Naming Conventions

| Context | Convention | Example |
|---|---|---|
| Python code (functions, variables, modules) | `snake_case` | `create_ticket`, `reporter_slack_user_id`, `redis_consumer.py` |
| Python classes | `PascalCase` | `TriageState`, `IncidentEvent` |
| Redis channels | `kebab-case` | `incidents`, `ticket-commands`, `notifications`, `errors` |
| API endpoints | `kebab-case`, plural | `/api/incidents`, `/api/webhooks/linear`, `/api/webhooks/otel` |
| JSON payloads (Redis + API) | `snake_case` | `{ "reporter_slack_user_id": "...", "trace_data": {...} }` |
| Docker services | `kebab-case` | `ticket-service`, `notification-worker` |
| Environment variables | `UPPER_SNAKE_CASE` | `LLM_PROVIDER`, `LINEAR_API_KEY`, `REDIS_URL` |
| Event naming | `entity.action` | `incident.created`, `ticket.create`, `notification.send` |
| Agent tools | `verb_noun` snake_case | `search_code`, `read_file` |

### Hexagonal Architecture Per Service

Every service follows hexagonal (ports & adapters) architecture to clearly separate business logic from infrastructure:

```
services/{service-name}/
├── Dockerfile
├── requirements.txt
└── src/
    ├── __init__.py
    ├── main.py                    # entry point, wires adapters to ports
    ├── config.py                  # env var loading (single source of truth)
    ├── domain/                    # core business logic (no external deps)
    │   ├── __init__.py
    │   ├── models.py              # domain entities, value objects
    │   └── services.py            # domain logic
    ├── ports/                     # interfaces (abstract base classes)
    │   ├── __init__.py
    │   ├── inbound.py             # driving ports (how the world calls us)
    │   └── outbound.py            # driven ports (how we call the world)
    └── adapters/                  # implementations
        ├── __init__.py
        ├── inbound/               # driving adapters
        │   ├── __init__.py
        │   └── redis_consumer.py  # or fastapi_routes.py
        └── outbound/              # driven adapters
            ├── __init__.py
            └── {integration}.py   # linear_client.py, slack_client.py, etc.
```

**Service-to-hexagonal mapping:**

| Service | Inbound Adapter | Domain | Outbound Adapter |
|---|---|---|---|
| **API** | FastAPI routes (`fastapi_routes.py`) | Incident intake, webhook handling | Redis publisher (`redis_publisher.py`) |
| **Agent** | Redis consumer (`redis_consumer.py`) | LLM triage reasoning (Pydantic AI + pydantic-graph) | Redis publisher (`redis_publisher.py`), GitHub API (`github_client.py`) |
| **Ticket Service** | Redis consumer (`redis_consumer.py`) | Ticket command processing | Linear API (`linear_client.py`), Redis publisher (`redis_publisher.py`) |
| **Notification Worker** | Redis consumer (`redis_consumer.py`) | Notification routing | Slack (`slack_client.py`) |

**Key principle:** Domain layer has ZERO imports from adapters. Ports define abstract interfaces. Adapters implement them. `main.py` wires everything together via dependency injection.

### Redis Message Envelope

Every Redis message across ALL services follows this envelope:

```json
{
  "event_id": "uuid-v4",
  "event_type": "incident.created",
  "timestamp": "2026-04-08T14:30:00Z",
  "source": "api",
  "payload": { }
}
```

**Mandatory fields:** `event_id`, `event_type`, `timestamp`, `source`, `payload`.

**Event types:**

| Event Type | Publisher | Consumer | Description |
|---|---|---|---|
| `incident.created` | API | Agent | New incident from UI form or OTEL alert |
| `triage.completed` | Agent | — (logged) | Agent completed triage (for observability) |
| `ticket.create` | Agent | Ticket Service | Command to create a ticket in Linear |
| `ticket.created` | Ticket Service | — (logged) | Confirmation ticket was created |
| `notification.send` | Ticket Service, API | Notification Worker | Send Slack notification |
| `ticket.error` | Ticket Service | Logging | Ticket creation failed |

### Error Handling Pattern

**Every service must:**
1. Wrap all external calls in try/except
2. On failure: log structured JSON + publish to `errors` channel
3. Never crash — continue consuming next message

**Structured log format:**
```json
{
  "timestamp": "ISO-8601",
  "level": "info | warning | error",
  "service": "api | agent | ticket-service | notification-worker",
  "event_id": "correlates to Redis event",
  "message": "human readable description",
  "error": "exception details if applicable"
}
```

### API Response Format

**Success:**
```json
{ "status": "ok", "data": { } }
```

**Error:**
```json
{ "status": "error", "message": "human readable", "code": "VALIDATION_ERROR" }
```

### Agent-Specific Patterns

**pydantic-graph state:** Single `TriageState` dataclass flows through all graph nodes via `GraphRunContext`. Every node reads from and writes to the same state structure. Edges are defined via return type hints — the graph structure is the code.

**Pydantic AI structured output:** Agent uses `output_type=TriageResult` (Pydantic model) for type-safe, validated structured output. No manual JSON parsing.

**Dependency injection:** Agent tools receive `TriageDeps` (GitHubClient, RedisPublisher) via `RunContext[TriageDeps]` — clean hexagonal boundary.

**Agent output:** Agent publishes structured commands to Redis, never free-text. Ticket content is pre-formatted markdown.

**LLM provider swap:** Configured via `config.py` reading `LLM_MODEL` env var as native model string (e.g., `openrouter:google/gemma-4`, `anthropic:claude-sonnet-4-20250514`). No factory pattern needed — Pydantic AI resolves provider from prefix.

### Enforcement Rules

**All AI agents implementing stories MUST:**

1. Follow the Redis event envelope format for ALL messages
2. Use `config.py` for ALL environment variable access — never `os.getenv()` inline
3. Include `event_id` correlation in ALL log entries
4. Handle ALL external API failures with try/except + error channel publish
5. Use `httpx.AsyncClient` for ALL HTTP calls — never `requests`
6. Keep domain logic free of adapter imports — respect hexagonal boundaries
7. Place new adapters in `adapters/inbound/` or `adapters/outbound/` only
8. Define interfaces in `ports/` before implementing adapters

### Required Repository Root Files

These files are **mandatory hackathon deliverables** and must exist at the repository root:

| File | Purpose | Hackathon Requirement |
|---|---|---|
| `README.md` | Architecture overview, project summary, setup instructions | FR36 |
| `AGENTS_USE.md` | Agent documentation: use cases, implementation, observability, safety | FR37 |
| `SCALING.md` | Scaling assumptions and technical decisions | FR38 |
| `QUICKGUIDE.md` | Step-by-step: clone → `.env` → `docker compose up --build` | FR39 |
| `docker-compose.yml` | Orchestrates all services, exposes required ports | FR40 |
| `.env.example` | All env vars with placeholder values and comments | FR35 |
| `Dockerfile` (per service) | One Dockerfile per service, referenced by docker-compose | FR41 |
| `LICENSE` | MIT license | FR42 |

## Project Structure & Boundaries

### Complete Project Directory Structure

```
mila/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── LICENSE                              # MIT
├── README.md                            # Architecture overview + setup
├── AGENTS_USE.md                        # Agent documentation (hackathon template)
├── SCALING.md                           # Scaling assumptions + decisions
├── QUICKGUIDE.md                        # clone → .env → docker compose up
│
├── infra/
│   └── otel-collector-config.yaml       # OTEL Collector pipeline config
│
├── services/
│   ├── ui/
│   │   ├── Dockerfile
│   │   ├── nginx.conf                   # static files + reverse proxy + rate limiting + CORS
│   │   └── public/
│   │       └── index.html               # mila_ui_final_v1.html
│   │
│   ├── api/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   │       ├── __init__.py
│   │       ├── main.py                  # FastAPI app, wires adapters
│   │       ├── config.py                # env vars: REDIS_URL
│   │       ├── domain/
│   │       │   ├── __init__.py
│   │       │   ├── models.py            # IncidentReport, WebhookEvent
│   │       │   └── services.py          # validate_incident, build_event
│   │       ├── ports/
│   │       │   ├── __init__.py
│   │       │   ├── inbound.py           # IncidentReceiver, OtelWebhookReceiver
│   │       │   └── outbound.py          # EventPublisher
│   │       └── adapters/
│   │           ├── __init__.py
│   │           ├── inbound/
│   │           │   ├── __init__.py
│   │           │   ├── fastapi_routes.py     # POST /api/incidents, /api/webhooks/otel
│   │           │   └── middleware.py         # input sanitization, CORS
│   │           └── outbound/
│   │               ├── __init__.py
│   │               └── redis_publisher.py    # publish to incidents channel
│   │
│   ├── agent/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   │       ├── __init__.py
│   │       ├── main.py                  # entry point, wires graph + adapters
│   │       ├── config.py                # env vars: LLM_MODEL, GITHUB_TOKEN, REDIS_URL
│   │       ├── domain/
│   │       │   ├── __init__.py
│   │       │   ├── models.py            # TriageState (dataclass), Classification, TriageResult (Pydantic BaseModel)
│   │       │   ├── services.py          # triage logic, classification rules
│   │       │   └── prompts.py           # system prompts, eShop context, prompt templates
│   │       ├── ports/
│   │       │   ├── __init__.py
│   │       │   ├── inbound.py           # IncidentConsumer
│   │       │   └── outbound.py          # CodeSearcher, CodeReader, CommandPublisher
│   │       ├── adapters/
│   │       │   ├── __init__.py
│   │       │   ├── inbound/
│   │       │   │   ├── __init__.py
│   │       │   │   └── redis_consumer.py     # consume from incidents channel
│   │       │   └── outbound/
│   │       │       ├── __init__.py
│   │       │       ├── github_client.py      # search_code, read_file via GitHub API
│   │       │       └── redis_publisher.py    # publish to ticket-commands
│   │       └── graph/
│   │           ├── __init__.py
│   │           ├── workflow.py           # pydantic-graph state graph definition
│   │           ├── nodes/
│   │           │   ├── __init__.py
│   │           │   ├── analyze_input.py      # parse incident, extract key details
│   │           │   ├── search_code.py        # search eShop via GitHub API
│   │           │   ├── classify.py           # bug vs misuse classification
│   │           │   └── generate_output.py    # create ticket content + commands
│   │           └── tools/
│   │               ├── __init__.py
│   │               ├── search_code.py        # @agent.tool: GitHub code search
│   │               └── read_file.py          # @agent.tool: GitHub file read
│   │
│   ├── ticket-service/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   │       ├── __init__.py
│   │       ├── main.py                  # entry point, wires adapters
│   │       ├── config.py                # env vars: LINEAR_API_KEY, LINEAR_WEBHOOK_SECRET, REDIS_URL
│   │       ├── domain/
│   │       │   ├── __init__.py
│   │       │   ├── models.py            # TicketCommand, TicketResult, TicketStatusEvent
│   │       │   └── services.py          # process_ticket_command, process_status_change
│   │       ├── ports/
│   │       │   ├── __init__.py
│   │       │   ├── inbound.py           # TicketCommandConsumer, TicketWebhookReceiver
│   │       │   └── outbound.py          # TicketCreator, EventPublisher
│   │       └── adapters/
│   │           ├── __init__.py
│   │           ├── inbound/
│   │           │   ├── __init__.py
│   │           │   ├── redis_consumer.py     # consume from ticket-commands
│   │           │   └── webhook_listener.py   # POST /webhooks/linear (status changes)
│   │           └── outbound/
│   │               ├── __init__.py
│   │               ├── linear_client.py      # create/update tickets in Linear
│   │               └── redis_publisher.py    # publish to notifications or errors
│   │
│   └── notification-worker/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── src/
│           ├── __init__.py
│           ├── main.py                  # entry point, wires adapters
│           ├── config.py                # env vars: SLACK_TOKEN, REDIS_URL
│           ├── domain/
│           │   ├── __init__.py
│           │   ├── models.py            # Notification, NotificationType
│           │   └── services.py          # route_notification
│           ├── ports/
│           │   ├── __init__.py
│           │   ├── inbound.py           # NotificationConsumer
│           │   └── outbound.py          # TeamNotifier
│           └── adapters/
│               ├── __init__.py
│               ├── inbound/
│               │   ├── __init__.py
│               │   └── redis_consumer.py     # consume from notifications
│               └── outbound/
│                   ├── __init__.py
│                   └── slack_client.py       # post to Slack channel + DMs
│
└── docs/
    ├── planning-artifacts/
    │   ├── prd.md
    │   └── architecture.md
    └── implementation-artifacts/
```

### Security Architecture — nginx as API Gateway

nginx serves dual purpose: static file server + API gateway. **Only port 8080 is externally exposed** (plus Langfuse 3000 for dashboard access).

**Routing configuration:**

| Route | Target | Access |
|---|---|---|
| `/` | Static HTML (UI) | Public |
| `/api/incidents` | `api:8000` | Public (rate limited) |
| `/api/webhooks/otel` | `api:8000` | Internal Docker network only |
| `/webhooks/linear` | `ticket-service:8002` | Public (signature verified) |

**Security layers:**

| Layer | Implementation | Location |
|---|---|---|
| Single entry point | nginx reverse proxy, only port 8080 exposed | `nginx.conf` |
| Rate limiting | `limit_req` on `/api/incidents` | `nginx.conf` |
| CORS | Restrict origins to UI domain | `nginx.conf` |
| Webhook signature verification | Linear HMAC verification | `ticket-service/webhook_listener.py` |
| Input sanitization | Strip dangerous content before LLM | `api/middleware.py` |
| Prompt injection detection | Pattern matching on user input | `api/middleware.py` |
| Secrets management | All credentials via env vars | `.env.example` |
| Internal network isolation | All services except nginx on internal Docker network | `docker-compose.yml` |

### Architectural Boundaries

**Service boundary principle:** Each service owns its integration domain end-to-end.

| Service | Owns | Does NOT touch |
|---|---|---|
| **API** | UI form intake, OTEL webhook intake | Linear, Slack |
| **Agent** | LLM reasoning, GitHub code analysis | Linear, Slack |
| **Ticket Service** | All Linear operations (create, update, webhook) | Slack, LLM |
| **Notification Worker** | All outbound messaging (Slack channel + DMs) | Linear, LLM, GitHub |

### Requirements to Structure Mapping

| FR | Requirement | Service | File(s) |
|---|---|---|---|
| FR1-4 | Incident submission form | UI | `services/ui/public/index.html` |
| FR5 | Create ticket on submission | API → Redis → Agent → Ticket Service | `fastapi_routes.py` → `redis_publisher.py` → `generate_output.py` → `linear_client.py` |
| FR6 | Confirmation with ticket ID | API | `fastapi_routes.py` |
| FR7 | Agent triggered on new ticket | Agent | `redis_consumer.py` |
| FR8 | Multimodal processing | Agent | `analyze_input.py`, `llm_provider.py` |
| FR9 | Analyze against eShop codebase | Agent | `search_code.py`, `read_file.py`, `github_client.py` |
| FR10 | Classify as bug or misuse | Agent | `classify.py` |
| FR11 | Confidence score | Agent | `classify.py`, `models.py (Classification)` |
| FR12 | Chain-of-thought reasoning | Agent | `prompts.py`, Langfuse tracing |
| FR13-18 | Engineering ticket content | Agent → Ticket Service | `generate_output.py` → `linear_client.py` |
| FR19 | Notification to team | Ticket Service → Notification Worker | `redis_publisher.py` → `slack_client.py` |
| FR20-22 | Misuse resolution | Agent → Ticket Service | `generate_output.py` → `linear_client.py` |
| FR23-25 | Resolution lifecycle | Linear webhook → Ticket Service → Notification Worker | `webhook_listener.py` → `redis_publisher.py` → `slack_client.py` |
| FR26-28 | Observability | Agent + Langfuse | `workflow.py` (auto-traced), Langfuse dashboard |
| FR29-32 | Guardrails & safety | API + Agent | `middleware.py` (sanitization), `prompts.py` (system prompt hardening) |
| FR33-35 | Deployment | Root | `docker-compose.yml`, `.env.example` |
| FR36-42 | Repository deliverables | Root | `README.md`, `AGENTS_USE.md`, `SCALING.md`, `QUICKGUIDE.md`, `LICENSE` |

### Integration Points & Data Flow

**Inbound (HTTP → internal):**

| Endpoint | Service | Source | Via |
|---|---|---|---|
| `POST /api/incidents` | API | UI form submission | nginx gateway |
| `POST /api/webhooks/otel` | API | OTEL Collector error alert | Internal Docker network |
| `POST /webhooks/linear` | Ticket Service | Linear status change webhook | nginx gateway |

**Internal (Redis channels):**

```
incidents ──▸ Agent ──▸ ticket-commands ──▸ Ticket Service ──▸ notifications ──▸ Notification Worker
```

**Outbound (services → external APIs):**

| Service | External API | Purpose |
|---|---|---|
| Agent | GitHub API | Code search + file read (in-process reasoning tool) |
| Agent | OpenRouter / Anthropic | LLM inference |
| Agent | Langfuse | Trace LLM calls and reasoning |
| Ticket Service | Linear API | Create/update tickets |
| Notification Worker | Slack API | Team channel alerts + reporter DMs |

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**

| Check | Status |
|---|---|
| Python 3.12 + FastAPI + Pydantic AI + pydantic-graph | ✅ All Python-native, no conflicts |
| Redis as sole inter-service bus | ✅ All services use redis-py, consistent pattern |
| Hexagonal architecture per service | ✅ Uniform structure, ports/adapters everywhere |
| nginx as gateway + static server | ✅ Single entry, routes to internal services |
| OpenRouter + Anthropic via Pydantic AI native model strings | ✅ Provider resolved from model string prefix (e.g., `openrouter:google/gemma-4`) |
| Linear + webhook to ticket-service directly | ✅ Clean ownership — ticket-service owns all Linear |
| OTEL Collector → API webhook (internal network) | ✅ Not routed through nginx, internal only |
| Langfuse for agent tracing only (not eShop APM) | ✅ eShop uses Aspire Dashboard separately |

No contradictions found.

**Pattern Consistency:** All naming, structure, and communication patterns align with the Python/Redis/hexagonal stack. snake_case everywhere in code, kebab-case for Docker/Redis/API.

**Structure Alignment:** Project tree follows hexagonal architecture uniformly. Every service has identical port/adapter structure. All files map to specific FRs.

### Requirements Coverage Validation ✅

**Functional Requirements (FR1-42):** All 42 FRs mapped to specific services and files in the Requirements to Structure Mapping table. No uncovered requirements.

**Misuse Path (FR20-22):** Uses the same pipeline as bug path with different command payload. Agent publishes `ticket.resolve` command → Ticket Service updates Linear to "Resolved" with guidance → Notification Worker sends Slack DM to reporter.

**Non-Functional Requirements (NFR1-20):**

| NFR | Status | Architectural Support |
|---|---|---|
| NFR1-2 Performance (<2min misuse, <3min bug) | ✅ | Async pipeline, LLM is the only bottleneck |
| NFR3-4 Submission (<5s), trigger (<30s) | ✅ | API → Redis is milliseconds, agent consumes immediately |
| NFR5-8 Security/Privacy | ✅ | nginx gateway, sanitization middleware, env vars, metadata-only logging |
| NFR9-12 Integration reliability | ✅ | Each service handles errors, publishes to errors channel, no cascading |
| NFR13-15 Observability | ✅ | Langfuse (agent) + Aspire Dashboard (eShop) + structured JSON logging |
| NFR16-17 Scalability | ✅ | Stateless agent, Redis decoupling — documented for SCALING.md |
| NFR18-20 Deployment | ✅ | `docker compose up --build`, only port 8080 + 3000 externally exposed |

### Implementation Readiness Validation ✅

| Check | Status |
|---|---|
| Every service has complete file tree with specific file names | ✅ |
| Every FR maps to specific files | ✅ |
| Redis event envelope format defined with mandatory fields | ✅ |
| All event types documented with publisher/consumer | ✅ |
| Hexagonal structure consistent across all 4 custom services | ✅ |
| Python dependency list per service | ✅ |
| LLM provider swap mechanism defined | ✅ |
| Security layers documented with implementation locations | ✅ |
| Enforcement rules for AI agents listed (8 rules) | ✅ |
| Hackathon deliverable files mapped to root | ✅ |

### Gap Analysis

**No critical gaps.**

**Minor gap addressed:** `.env.example` variable listing documented below.

### Environment Variables (.env.example)

```env
# LLM Configuration (Pydantic AI native model strings)
LLM_MODEL=openrouter:google/gemma-4    # openrouter:google/gemma-4 | anthropic:claude-sonnet-4-20250514
OPENROUTER_API_KEY=                    # required if LLM_MODEL starts with openrouter:
ANTHROPIC_API_KEY=                     # required if LLM_MODEL starts with anthropic:

# Redis
REDIS_URL=redis://redis:6379

# Linear (Ticketing)
LINEAR_API_KEY=
LINEAR_TEAM_ID=
LINEAR_WEBHOOK_SECRET=

# Slack (Team Notifications)
SLACK_BOT_TOKEN=
SLACK_CHANNEL_ID=
SLACK_REPORTER_USER_ID=                # Slack user ID for reporter DMs (demo: hardcoded)

# GitHub (Code Analysis)
GITHUB_TOKEN=                          # optional for public repos, recommended for rate limits

# Agent Configuration
CONFIDENCE_THRESHOLD=0.75              # classification confidence threshold (0.0-1.0)

# Langfuse (Observability)
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=http://langfuse:3000
```

### Architecture Completeness Checklist

- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped
- [x] Critical decisions documented with rationale
- [x] Technology stack fully specified
- [x] Integration patterns defined (Redis event bus)
- [x] Security architecture defined (nginx gateway)
- [x] Naming conventions established
- [x] Hexagonal architecture structure defined per service
- [x] Communication patterns specified (event envelope)
- [x] Error handling patterns documented
- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped (inbound/internal/outbound)
- [x] Requirements to structure mapping complete (FR1-42)
- [x] NFR coverage verified (NFR1-20)
- [x] Hackathon deliverable files mapped
- [x] Environment variables documented

### Implementation Phasing

**Phase 1 — UI Path (Priority: MUST work first)**

The complete required hackathon flow via UI form:

```
UI form → nginx → API → Redis:incidents → Agent (triage + code analysis)
  → Redis:ticket-commands → Ticket Service → Linear (create ticket)
  → Redis:notifications → Notification Worker → Slack (team + reporter DM)

Engineer resolves → Linear webhook → Ticket Service → Redis:notifications
  → Notification Worker → Slack DM (reporter notified)
```

Phase 1 validates the **entire end-to-end pipeline** with all services, integrations, and the resolution lifecycle.

**Phase 2 — Proactive Detection (After Phase 1 works end-to-end)**

Add eShop + OTEL Collector as a second incident source:

```
eShop error → OTEL Collector (filter errors) → webhook to API → Redis:incidents → same pipeline
```

No architectural changes needed. The OTEL Collector publishes to the same `incidents` channel. The agent processes incidents identically regardless of source.

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High — all decisions validated, no gaps, complete file tree, all FRs/NFRs covered.

**Key Strengths:**
- Event-driven decoupling via Redis enables independent development and testing of each service
- Hexagonal architecture ensures clean boundaries and testability
- Single agent with focused responsibility (reasoning only, no I/O)
- nginx gateway provides security without extra infrastructure
- Two-phase implementation prioritizes the hackathon-required flow

**AI Agent Implementation Guidelines:**
- Follow all architectural decisions exactly as documented
- Use implementation patterns consistently across all components
- Respect hexagonal boundaries — domain layer has zero adapter imports
- Follow the Redis event envelope format for all messages
- Implement Phase 1 (UI path) completely before Phase 2 (OTEL detection)
