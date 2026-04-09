# SCALING.md

## Current Architecture

Mila runs as a **single-instance Docker Compose deployment** with 9 services communicating via Redis pub/sub.

| Characteristic | Current State |
|---|---|
| **Deployment** | Docker Compose on a single host |
| **Service instances** | 1 per service (API, Agent, Ticket Service, Notification Worker) |
| **Message bus** | Redis pub/sub (fire-and-forget) |
| **State** | Stateless services; Redis for ticket-reporter mapping (90-day TTL) |
| **LLM calls** | Sequential — one incident triaged at a time per agent instance |
| **Data persistence** | Langfuse (Postgres), Redis mappings only |

### Known Constraints

1. **Redis pub/sub is fire-and-forget** — if the Agent or a worker is down when a message is published, that message is lost
2. **Single agent instance** — LLM triage is sequential; throughput is bounded by LLM API latency (~5–15s per classification)
3. **No request authentication** — suitable for demo/hackathon; not production-ready
4. **GitHub API rate limits** — 5,000 requests/hour for authenticated tokens; code search has additional limits
5. **No persistent job queue** — failed jobs are not retried unless the publishing service implements retries

---

## Horizontal Scaling Strategy

### Stateless Agent Scaling

The Agent service is already stateless — it reads an incident from Redis, processes it, and publishes results. No session or in-memory state persists between incidents.

**To scale horizontally:**

1. Run multiple Agent containers behind a shared Redis subscription
2. Switch from pub/sub to **Redis Streams** consumer groups — each agent instance in the group receives a unique message, with automatic load balancing and acknowledgment

```yaml
# docker-compose.prod.yml
agent:
  deploy:
    replicas: 3
```

With Redis Streams, each `incident` event is delivered to exactly one agent in the consumer group and re-delivered if not acknowledged — eliminating message loss.

### Redis Pub/Sub → Redis Streams Migration

| Feature | Pub/Sub (Current) | Streams (Production) |
|---|---|---|
| Delivery | Fire-and-forget | At-least-once with ACK |
| Consumer groups | No | Yes — load balancing built-in |
| Message persistence | None | Configurable retention |
| Replay | Not possible | Replay from any point |
| Backpressure | None | Consumer lag monitoring |

**Migration path:** Replace `redis.publish()` / `redis.subscribe()` calls with `redis.xadd()` / `redis.xreadgroup()`. Channel names map directly to stream keys. No architectural change needed — only the Redis adapter layer.

### Worker Scaling

Ticket Service and Notification Worker are also stateless and can scale the same way:

- **Ticket Service:** Multiple instances consuming from `ticket-commands` stream. Linear API handles idempotency via unique ticket references.
- **Notification Worker:** Multiple instances consuming from `notifications` stream. Slack messages are idempotent by incident ID.
- **API:** Standard horizontal scaling behind a load balancer (nginx, Traefik, or cloud LB).

---

## Multi-Codebase Support

Currently, Mila is hardcoded to analyze the `dotnet/eShop` repository. To support multiple codebases:

### 1. Parameterize Repository Configuration

```python
# Current
GITHUB_REPOS = "dotnet/eShop"

# Multi-codebase
GITHUB_REPOS = "dotnet/eShop,org/backend-api,org/frontend-app"
```

Each incident would include a `codebase` field indicating which repository to analyze.

### 2. Per-Codebase Architecture Context

Replace the single `eshop_context.md` with a codebase registry:

```
services/agent/src/domain/context/
├── dotnet-eshop.md
├── backend-api.md
└── frontend-app.md
```

The agent selects the correct context file based on the incident's target codebase.

### 3. Codebase-Aware Search

Agent tools (`search_code`, `read_file`) already accept a `repo` parameter. Multi-codebase support requires passing the correct repo from the incident event through the triage pipeline.

---

## Production Hardening

### Authentication & Authorization

- Add API key authentication for the incident submission endpoint
- Add JWT or OAuth2 for webhook endpoints (Linear, Slack, OTEL)
- Restrict internal service communication to the Docker network (already in place via `mila-net`)

### Persistent Queuing

- Replace Redis pub/sub with Redis Streams for all critical channels
- Add dead-letter queues for permanently failed messages
- Implement idempotency keys to handle at-least-once delivery

### LLM Resilience

- **Circuit breaker** already implemented (2 failures → 60s cooldown → fallback model)
- Add request-level timeouts for LLM API calls
- Add cost budgets: track token usage per incident, cap per-incident spend
- Consider local model fallback (e.g., Ollama) for complete API independence

### Observability (Production)

- Replace self-hosted Langfuse with Langfuse Cloud (or a managed instance) for reliability
- Add Prometheus metrics endpoint for each service
- Add Grafana dashboards for: triage throughput, LLM latency/cost, ticket creation success rate, notification delivery rate
- Configure alerts for: circuit breaker activation, sustained high error rates, queue backlog growth

### Data Persistence

- Add PostgreSQL for incident history, triage results, and audit trails
- Implement event sourcing: every state change (incident created → triaged → ticket created → notified → resolved) is a persistent event
- Add retention policies for Langfuse traces and Redis data

### Security Hardening

- Rate limiting on all public endpoints
- TLS termination (currently HTTP-only in Docker Compose)
- Rotate API keys and webhook secrets via a secrets manager
- Add audit logging for all external API calls (Linear, Slack, GitHub)
