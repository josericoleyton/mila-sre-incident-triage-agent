# Story 6.3: OTEL Collector for Proactive eShop Error Detection

> **Epic:** 6 — Observability & Proactive Detection
> **Status:** ready-for-dev
> **Priority:** 🟠 High — Key differentiator
> **Depends on:** Story 1.1 (Docker Compose with OTEL service defined); Story 2.2 (API /api/webhooks/otel endpoint)
> **FRs:** FR25 (enabler)

## Story

**As a** system,
**I want** the OTEL Collector to receive traces from the eShop Aspire application, filter for errors, and webhook them to the API as auto-generated incidents,
**So that** Mila can proactively detect infrastructure issues without human reporting.

## Acceptance Criteria

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

## Tasks / Subtasks

- [ ] **1. Create OTEL Collector configuration**
  - `infra/otel-collector-config.yaml`
  - Receivers: OTLP (gRPC on 4317, HTTP on 4318)
  - Processors: filter for error spans (status_code = ERROR, HTTP >= 500)
  - Exporters: webhook exporter to `http://api:8000/api/webhooks/otel`
  - Pipeline: traces → filter processor → webhook exporter

- [ ] **2. Configure OTEL Collector Docker service**
  - Already defined in docker-compose.yml (Story 1.1)
  - Mount `infra/otel-collector-config.yaml` as config
  - Expose OTLP ports internally (4317, 4318 — not published externally)

- [ ] **3. Define webhook exporter payload format**
  - The OTEL Collector transforms filtered error spans into a JSON webhook payload
  - Required fields: error_message, service_name, trace_id, status_code, timestamp
  - API /api/webhooks/otel endpoint (Story 2.2) expects this format

- [ ] **4. Test with eShop traces**
  - Configure eShop Aspire to send OTLP traces to the Collector
  - Trigger an error in eShop (e.g., cause a 500 response)
  - Verify: error detected → webhook sent → API creates incident → Agent triages

## Dev Notes

### Architecture Guardrails
- **OTEL Collector is a passthrough:** It receives telemetry, filters for errors, and forwards to the API. No LLM or business logic in the collector.
- **Internal network only:** OTLP ports 4317/4318 are NOT published externally. Only eShop (also internal or same Docker network) sends to the collector.
- **API webhooks are trusted:** OTEL webhooks come from the internal Docker network — no authentication needed on `/api/webhooks/otel`.

### OTEL Collector Config Structure
```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  filter/errors:
    error_mode: ignore
    traces:
      span:
        - 'status.code == STATUS_CODE_ERROR'

exporters:
  webhook:
    endpoint: http://api:8000/api/webhooks/otel
    encoding: json

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [filter/errors]
      exporters: [webhook]
```

### eShop Aspire OTEL Configuration
eShop Aspire natively supports OpenTelemetry. Configure the OTLP endpoint in the eShop environment:
```
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

### Key Reference Files
- Story 2.2: API /api/webhooks/otel endpoint
- Story 3.5: Agent always-escalate for systemIntegration
- Story 1.1: Docker Compose with OTEL Collector service
- Architecture doc: `docs/planning-artifacts/architecture.md` — OTEL configuration

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
