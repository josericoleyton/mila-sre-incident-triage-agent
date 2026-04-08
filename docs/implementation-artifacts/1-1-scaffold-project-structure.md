# Story 1.1: Scaffold Project Structure with Docker Compose

> **Epic:** 1 — Project Foundation & Service Scaffolding
> **Status:** complete
> **Priority:** 🔴 Critical Path — Blocks all other epics
> **FRs:** FR34, FR35, FR40, FR41

## Story

**As a** developer,
**I want** the complete project directory structure, Dockerfiles, and Docker Compose configuration created per the architecture specification,
**So that** all service teams can begin independent development with a working containerized environment.

## Acceptance Criteria

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

## Tasks / Subtasks

- [x] **1. Create root project files**
  - `docker-compose.yml` with all 8 services defined (ui, api, agent, ticket-service, notification-worker, redis, langfuse, otel-collector)
  - `.env.example` with all env vars, placeholder values, and inline comments
  - `.dockerignore` for Python services
  - `.gitignore` for Python + Docker

- [x] **2. Create services/ui/**
  - `Dockerfile` — nginx:alpine serving static files from `/usr/share/nginx/html`
  - `nginx.conf` — static file serving + reverse proxy stubs (`/api/*` → `api:8000`, `/webhooks/linear` → `ticket-service:8002`) + rate limiting on `/api/incidents` + CORS headers
  - `public/index.html` — placeholder HTML (will be replaced by Story 2.1 with the real form)

- [x] **3. Create services/api/ hexagonal structure**
  - `Dockerfile` — Python 3.12-slim, install requirements, run `src/main.py`
  - `requirements.txt` — `fastapi`, `uvicorn[standard]`, `redis[hiredis]`, `python-multipart`, `pydantic`, `httpx`
  - `src/__init__.py`
  - `src/main.py` — minimal FastAPI app that logs "Service api started" and stays alive
  - `src/config.py` — loads all env vars: `REDIS_URL`, `SLACK_REPORTER_USER_ID`
  - `src/domain/__init__.py`, `src/domain/models.py` (empty), `src/domain/services.py` (empty)
  - `src/ports/__init__.py`, `src/ports/inbound.py` (empty), `src/ports/outbound.py` (empty)
  - `src/adapters/__init__.py`
  - `src/adapters/inbound/__init__.py`, `src/adapters/inbound/fastapi_routes.py` (empty)
  - `src/adapters/outbound/__init__.py`, `src/adapters/outbound/redis_publisher.py` (empty)

- [x] **4. Create services/agent/ hexagonal structure**
  - `Dockerfile` — Python 3.12-slim, install requirements, run `src/main.py`
  - `requirements.txt` — `pydantic-ai[all]`, `pydantic-graph`, `redis[hiredis]`, `httpx`, `pydantic`
  - `src/__init__.py`
  - `src/main.py` — minimal script that logs "Service agent started" and stays alive
  - `src/config.py` — loads: `LLM_MODEL`, `REDIS_URL`, `GITHUB_TOKEN`, `LANGFUSE_*` vars, `CONFIDENCE_THRESHOLD`
  - `src/domain/__init__.py`, `src/domain/models.py` (empty), `src/domain/prompts.py` (empty)
  - `src/ports/__init__.py`, `src/ports/inbound.py` (empty), `src/ports/outbound.py` (empty)
  - `src/adapters/__init__.py`
  - `src/adapters/inbound/__init__.py`, `src/adapters/inbound/redis_consumer.py` (empty)
  - `src/adapters/outbound/__init__.py`, `src/adapters/outbound/redis_publisher.py` (empty), `src/adapters/outbound/github_client.py` (empty)
  - `src/graph/__init__.py`, `src/graph/workflow.py` (empty)
  - `src/graph/nodes/__init__.py` (empty)
  - `src/graph/tools/__init__.py`, `src/graph/tools/search_code.py` (empty), `src/graph/tools/read_file.py` (empty)

- [x] **5. Create services/ticket-service/ hexagonal structure**
  - `Dockerfile` — Python 3.12-slim, install requirements, run `src/main.py`
  - `requirements.txt` — `fastapi`, `uvicorn[standard]`, `redis[hiredis]`, `httpx`, `pydantic`
  - `src/__init__.py`
  - `src/main.py` — minimal script that logs "Service ticket-service started" and stays alive (starts both Redis consumer + FastAPI webhook server)
  - `src/config.py` — loads: `LINEAR_API_KEY`, `LINEAR_TEAM_ID`, `LINEAR_WEBHOOK_SECRET`, `REDIS_URL`
  - `src/domain/__init__.py`, `src/domain/models.py` (empty), `src/domain/services.py` (empty)
  - `src/ports/__init__.py`, `src/ports/inbound.py` (empty), `src/ports/outbound.py` (empty)
  - `src/adapters/__init__.py`
  - `src/adapters/inbound/__init__.py`, `src/adapters/inbound/redis_consumer.py` (empty), `src/adapters/inbound/webhook_listener.py` (empty)
  - `src/adapters/outbound/__init__.py`, `src/adapters/outbound/redis_publisher.py` (empty), `src/adapters/outbound/linear_client.py` (empty)

- [x] **6. Create services/notification-worker/ hexagonal structure**
  - `Dockerfile` — Python 3.12-slim, install requirements, run `src/main.py`
  - `requirements.txt` — `redis[hiredis]`, `slack-sdk`, `pydantic`
  - `src/__init__.py`
  - `src/main.py` — minimal script that logs "Service notification-worker started" and stays alive
  - `src/config.py` — loads: `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `REDIS_URL`
  - `src/domain/__init__.py`, `src/domain/models.py` (empty), `src/domain/services.py` (empty)
  - `src/ports/__init__.py`, `src/ports/inbound.py` (empty), `src/ports/outbound.py` (empty)
  - `src/adapters/__init__.py`
  - `src/adapters/inbound/__init__.py`, `src/adapters/inbound/redis_consumer.py` (empty)
  - `src/adapters/outbound/__init__.py`, `src/adapters/outbound/slack_client.py` (empty)

- [x] **7. Create infra/ directory**
  - `infra/otel-collector-config.yaml` — placeholder config with comment about OTLP receiver + webhook exporter

- [x] **8. Verify docker compose up --build**
  - All containers start without errors
  - Redis responds to PING
  - nginx returns 200 on port 8080
  - Python services log their startup messages and stay alive

## Dev Notes

### Architecture Guardrails
- **Hexagonal Architecture:** Every Python service follows `src/domain/`, `src/ports/`, `src/adapters/inbound/`, `src/adapters/outbound/`. Domain layer has ZERO imports from adapters (AR1, AR5).
- **Config Pattern:** All environment variables accessed ONLY via `config.py`. Never use `os.getenv()` inline (AR3).
- **Naming Conventions:** `snake_case` for Python files/modules, `kebab-case` for Docker service names, Redis channels, and API paths.
- **HTTP Client:** Use `httpx.AsyncClient` everywhere — never `requests` library (AR4).
- **No Email/Resend:** Slack is the ONLY notification channel. No Resend dependency anywhere.

### Docker Compose Structure
- **Network:** Internal `mila-net` for all services. Only port 8080 (nginx) and 3000 (Langfuse) published externally (AR6).
- **Depends on:** Redis starts first → then Python services → then UI (nginx). Use `depends_on` with health checks.
- **Shared volume:** `/shared/attachments` mounted on `api` and `agent` containers for file attachment sharing.
- **Langfuse:** Self-hosted container with its own Postgres DB (use Langfuse's official Docker image).
- **OTEL Collector:** Official `otel/opentelemetry-collector-contrib` image with custom config.

### Python Service Minimal `main.py` Pattern
```python
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"<service-name>","message":"%(message)s"}')
logger = logging.getLogger(__name__)

async def main():
    logger.info("Service <service-name> started")
    # Keep alive
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
```

### Key Reference Files
- Architecture doc: `docs/planning-artifacts/architecture.md` — contains full directory structure, Docker Compose reference, env vars, and service definitions
- `.env.example` variables: `LLM_MODEL`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `REDIS_URL`, `LINEAR_API_KEY`, `LINEAR_TEAM_ID`, `LINEAR_WEBHOOK_SECRET`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `SLACK_REPORTER_USER_ID`, `GITHUB_TOKEN`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*

### Decision: Ollama removed from project (2026-04-08)

**Context:** The Ollama Docker image is ~3.6GB and caused `docker compose up --build` to hang during initial pull, making iterative development impractical during a 2-day hackathon sprint.

**Decision:** Removed Ollama entirely from the project — Docker Compose, architecture spec, and all story files. LLM inference uses only OpenRouter (default, free tier available) and Anthropic via API keys. `LLM_MODEL` default is `openrouter:google/gemma-4`.

**Impact:** Docker Compose now defines 8 services (ui, api, agent, ticket-service, notification-worker, redis, langfuse, otel-collector). All LLM calls require an API key (`OPENROUTER_API_KEY` or `ANTHROPIC_API_KEY`).
