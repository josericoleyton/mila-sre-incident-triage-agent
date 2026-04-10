# Story 6.3: OTEL Collector for Proactive eShop Error Detection

> **Epic:** 6 — Observability & Proactive Detection
> **Status:** review
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

- [x] **1. Create OTEL Collector configuration**
  - `infra/otel-collector-config.yaml`
  - Receivers: OTLP (gRPC on 4317, HTTP on 4318)
  - Processors: filter for error spans (status_code = ERROR, HTTP >= 500)
  - Exporters: webhook exporter to `http://api:8000/api/webhooks/otel`
  - Pipeline: traces → filter processor → webhook exporter

- [x] **2. Configure OTEL Collector Docker service**
  - Already defined in docker-compose.yml (Story 1.1)
  - Mount `infra/otel-collector-config.yaml` as config
  - Expose OTLP ports internally (4317, 4318 — not published externally)

- [x] **3. Define webhook exporter payload format**
  - The OTEL Collector transforms filtered error spans into a JSON webhook payload
  - Required fields: error_message, service_name, trace_id, status_code, timestamp
  - API /api/webhooks/otel endpoint (Story 2.2) expects this format

- [x] **4. Test with eShop traces**
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

### Implementation Notes (2026-04-08)

**Decision: otlphttp exporter** — The OTEL Collector uses `otlphttp/mila` exporter (JSON encoding, no compression) to send filtered error spans to the API in OTLP-JSON format (`resourceSpans` envelope). Standard OTEL exporters only produce OTLP format, not custom JSON.

**Decision: dual-format API endpoint** — Updated `/api/webhooks/otel` to auto-detect the payload format: if `resourceSpans` key is present → parse OTLP format; otherwise → use the original simple JSON format from Story 2.2. Full backward compatibility preserved.

**Decision: filter processor strategy** — Uses `filter/errors` processor with OTTL condition `status.code != STATUS_CODE_ERROR` to DROP all non-error spans, keeping only spans the OTEL spec marks as errors. The `error_mode: ignore` ensures misbehaving spans pass through rather than being silently dropped.

**Decision: internal-only ports** — Replaced `ports: ["4317:4317"]` (external publish) with `expose: ["4317", "4318"]` (internal Docker network only) per security guardrails. Added `depends_on: [api]`.

### File List
- `infra/otel-collector-config.yaml` — Full collector pipeline: otlp receiver → filter/errors → batch → otlphttp/mila exporter
- `docker-compose.yml` — Updated otel-collector service: removed external ports, added expose 4317/4318, added depends_on api
- `services/api/src/adapters/inbound/fastapi_routes.py` — Added OTLP-JSON handler (_handle_otlp_traces), helper functions for attribute extraction and timestamp conversion; refactored existing handler into _handle_simple_otel
- `tests/test_otel_collector.py` — 27 new tests: collector config validation (9), OTLP webhook handling (10), simple JSON regression (2), Docker Compose structure (6)

### Change Log
- 2026-04-08: Implemented all 4 tasks for Story 6.3. 27 new tests, 88 tests pass across OTEL-related files (0 regressions).
- 2026-04-08: Code review fixes — addressed all 8 findings (D1, P1-P7). Partial-write handling, null-safe OTLP parsing, safe int conversion, removed external DNS, added healthcheck condition. 37 tests (10 new edge case tests), 98 total pass.
