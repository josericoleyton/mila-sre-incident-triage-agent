# Story 7.1: Docker Compose Finalization & Security Hardening

> **Epic:** 7 — Deployment, Integration & Documentation
> **Status:** ready-for-dev
> **Priority:** 🔴 Critical — Final integration
> **Depends on:** Epics 1-6 (all services implemented)
> **FRs:** FR33, FR40, FR41

## Story

**As a** developer,
**I want** the Docker Compose configuration to be production-ready with health checks, proper network isolation, and security hardening,
**So that** `docker compose up --build` from a clean clone produces a fully working, secure application.

## Acceptance Criteria

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

## Tasks / Subtasks

- [ ] **1. Add health checks to all services**
  - Redis: `redis-cli ping`
  - Python services: custom healthcheck endpoint or process check
  - nginx: `curl -f http://localhost:80`
  - Langfuse: HTTP health endpoint

- [ ] **2. Configure depends_on with health check conditions**
  - Redis: starts first, all others wait for healthy
  - Python services: start after Redis healthy
  - nginx: starts after API and Ticket-Service healthy (for reverse proxy)

- [ ] **3. Verify network isolation**
  - All services on `mila-net` internal network
  - Only published ports: 8080 (nginx), 3000 (Langfuse)
  - No direct external access to API (8000), Ticket-Service (8002), Redis (6379)

- [ ] **4. Verify security measures**
  - nginx rate limiting on `/api/incidents`
  - CORS headers configured
  - Linear webhook HMAC verification
  - No hardcoded credentials
  - Shared volume permissions

- [ ] **5. Test clean-clone startup**
  - `git clone` → copy `.env.example` → fill values → `docker compose up --build`
  - All containers healthy within 60 seconds
  - No import errors or missing dependencies

## Dev Notes

### Architecture Guardrails
- **NFR18, NFR19:** `docker compose up --build` from clean clone. No host dependencies beyond Docker.
- **NFR20:** Only required ports exposed. Internal services stay internal.
- **AR6:** nginx is the single gateway. All external traffic flows through port 8080.

### Health Check Patterns
```yaml
services:
  redis:
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  api:
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 10s
      timeout: 5s
      retries: 3
```

### Key Reference Files
- Story 1.1: Initial Docker Compose setup (this story finalizes it)
- Architecture doc: `docs/planning-artifacts/architecture.md` — Docker services, network topology

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
