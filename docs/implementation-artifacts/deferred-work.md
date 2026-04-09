# Deferred Work

Items identified during code reviews that are deferred for future stories or cross-cutting concerns.

## From Story 4-1: Ticket-Service Scaffold

| # | Finding | File | Reason |
|---|---------|------|--------|
| 1 | asyncio.gather doesn't restart on single-task failure | main.py:40-43 | Pre-existing pattern shared by agent service; needs project-wide decision |
| 2 | No request size limit on webhook endpoint | webhook_listener.py | Nginx reverse proxy handles upstream body limits |
| 3 | No rate limiting on webhook endpoint | webhook_listener.py | Nginx reverse proxy handles upstream rate limiting |
| 4 | Handler exception crashes redis consumer loop | redis_consumer.py:52 | Pre-existing code not changed by this story; needs try/except in consumer loop |

## Deferred from: code review of story-3.6 (2026-04-08)

- **W1: Fallback + systemIntegration → no ticket.create published** — When `triage_result=None` for systemIntegration, fallback creates bug result but only publishes `triage.completed`, never `ticket.create`. Pre-existing from original fallback block design.
- **W2: Empty slack_user_id propagated to notification payload** — `state.incident.get("reporter_slack_user_id", "")` defaults to empty string with no validation. Same pattern used in `_build_ticket_command`. Pre-existing from Story 3.4.
- **W3: In-place mutation of state.triage_result.classification** — Story 3.5's forced-bug override mutates the TriageResult in place (`result.classification = Classification.bug`). Any post-graph audit of `state.triage_result` sees the overridden value, not the original LLM output. Pre-existing from Story 3.5.
- **W4: description triple-backtick injection in _format_ticket_body** — User-supplied `description` field is fenced in backticks but the description itself is not sanitized, unlike `error_message` which strips triple backticks. Pre-existing from Story 3.4.
- **W5: attachment_url markdown injection** — Raw URL is interpolated into markdown list item with no sanitization. Could enable link injection. Pre-existing.
- **W6: Negative duration_ms if monotonic clock state is stale** — If `triage_started_at` exceeds current `time.monotonic()`, `duration_ms` becomes negative. No `max(0, ...)` guard. Pre-existing edge case.

## Deferred from: code review of story-3.8 (2026-04-08)

- **W1: Empty `slack_user_id` fallback on re-escalation notification** — `state.incident.get("reporter_slack_user_id", "")` defaults to empty string with no validation. Pre-existing pattern shared by all notification payloads (see story-3.6 W2).

## Deferred from: code review of story-6.1 (2026-04-08)

- **W1: Notification-worker missing domain-level logs** — `services/notification-worker/src/domain/services.py` is empty (Slack integration not yet implemented). Task 3 of Story 6.1 requires Slack send/success/failure logs but these are blocked by the scaffold state. Should be addressed when Slack integration is implemented (Story 5.2+).
- **W2: No `trace_id`/`span_id` in JSON log format** — The OTEL collector is configured (`infra/otel-collector-config.yaml`) but the `StructuredJsonFormatter` emits no trace context fields. Cross-service request correlation requires OTEL SDK integration beyond Python stdlib logging. Consider adding `opentelemetry-instrumentation-logging` or manual trace context injection in a future observability story.
