# AGENTS_USE.md

## 1. Agent Overview

**Agent Name:** Mila
**Purpose:** Mila is an autonomous SRE triage agent that ingests incident reports for the eShop e-commerce platform, analyzes the actual production codebase via GitHub API, and classifies each incident as a real infrastructure/code bug or a non-incident. For bugs, it creates engineering tickets in Linear with root cause analysis, severity assessment, and suggested fixes. For non-incidents, it delivers a clear technical explanation directly to the reporter. The entire pipeline runs without human intervention.
**Tech Stack:** Python 3.14, Pydantic AI, pydantic-graph, FastAPI, Redis, configurable LLM via `LLM_MODEL` (default: `openrouter:google/gemma-4` with circuit-breaker fallback), Langfuse for LLM observability.

---

## 2. Agent Capabilities

### Agent: Mila — SRE Triage Agent

| Field | Description |
|-------|-------------|
| **Role** | Analyze incident reports, search the eShop codebase, classify as bug or non-incident, generate structured triage output |
| **Type** | Autonomous — fully automated pipeline with no human-in-the-loop (except optional re-escalation) |
| **LLM** | Configurable via `LLM_MODEL`. Default: `openrouter:google/gemma-4` with automatic failover via circuit breaker. Supports any OpenRouter or Anthropic model. |
| **Inputs** | Incident events from Redis: title, description, component, severity, file attachments (images analyzed as multimodal BinaryContent, logs parsed as text), OTEL error traces |
| **Outputs** | `TriageResult`: classification (bug/non_incident), confidence (0.0–1.0), reasoning, file references, root cause, suggested fix, resolution explanation, severity assessment (P1–P4) |
| **Tools** | `search_code` (GitHub Code Search API), `read_file` (GitHub Contents API) |

---

## 3. Triage Pipeline

The agent's internal pipeline is a **pydantic-graph state machine** with four nodes executed in sequence:

```
AnalyzeInputNode → SearchCodeNode → ClassifyNode → GenerateOutputNode
```

Each node receives and updates a `TriageState` dataclass that accumulates context as the pipeline progresses.

### Node Responsibilities

**AnalyzeInputNode**
Extracts error signals, stack traces, and file references from the incident title, description, and all attached files using regex patterns. Processes images as multimodal `BinaryContent` and log files as inline text. Enforces file size limits (5MB per file, 20MB total).

**SearchCodeNode**
Builds search queries from extracted signals and iteratively searches the eShop codebase via GitHub API. Reads relevant source files to understand the code context. Capped at 5 search iterations and 100KB per file read. Binary files are automatically excluded.

**ClassifyNode**
Sends the incident data, attachment content, and code context to the LLM with the triage system prompt. Produces a structured `TriageResult` enforced by Pydantic AI's `output_type`. Includes retry logic (2 attempts) on LLM failure. Adds a prompt injection warning addendum when injection was detected upstream.

**GenerateOutputNode**
Routes the result based on classification. For bugs: publishes a `ticket.create_engineering_ticket` command to Redis. For non-incidents from user reports: publishes a `notification.send` event directly to the reporter. Handles forced escalation for proactive (OTEL-detected) incidents and re-escalated incidents.

### Context Engineering

| Source | How it is used |
|--------|----------------|
| Incident data | Title, description, component, severity fed directly into classification prompt |
| File attachments | Images sent as `BinaryContent` for visual analysis; logs included as inline text (truncated at 3,000 chars) |
| eShop architecture context | `eshop_context.md` loaded at runtime and injected as `SYSTEM CONTEXT` in the classification prompt |
| GitHub code search | Runtime search via `search_code` tool using signals extracted from the incident |
| GitHub file contents | Specific source files read via `read_file` tool after search identifies relevant paths |
| OTEL error traces | For proactive incidents: trace data, span attributes, and error messages included as incident context |

### Confidence and Severity

- Confidence scored 0.0–1.0 based on evidence strength. Incidents below the configured `CONFIDENCE_THRESHOLD` (default 0.75) are flagged in the ticket and reporter notification.
- Severity assessed independently as P1–P4 based on code impact analysis (scope, business impact, workaround availability). Any difference between agent and reporter severity is documented in the ticket.

### Re-escalation

Reporters can re-escalate a non-incident classification via their Slack DM. The agent re-triages with escalation bias, incorporating the reporter's feedback as additional context. Re-escalated incidents always produce a bug classification.

---

## 4. Use Cases

### Use Case 1: Real bug with code evidence

**Scenario:** An Incident Manager reports an error observed in a service, attaching logs or describing symptoms. The root cause lives in the codebase.

**How Mila handles it:**
The agent extracts error signals from the incident text and all attached files. It builds targeted search queries from those signals and iteratively searches the eShop codebase via GitHub API, reading relevant source files until it has enough context to identify the root cause. The classification node receives the incident data, the attachment content, and the code context together, and produces a `TriageResult` with a `bug` classification, a P1–P4 severity, the affected file paths, root cause explanation, and a suggested fix. The Ticket Service creates a Linear ticket with all of that information structured and ready for the engineer to act on immediately.

**Key implementation decisions:**
Signal extraction from attachments (`AnalyzeInputNode`) ensures that error patterns in log files directly inform the GitHub search queries in `SearchCodeNode`, making the code search targeted rather than generic. Structured output via `output_type=TriageResult` guarantees that file references come from real GitHub API results, not hallucinated paths.

---

### Use Case 2: Non-incident dismissal

**Scenario:** An Incident Manager reports something that turns out to be expected behavior, a known limitation, or a high-traffic event rather than a code defect.

**How Mila handles it:**
The same triage pipeline runs as in Use Case 1. When the classification node determines the incident does not meet the bug criteria defined in the system prompt, it produces a `non_incident` classification with a `resolution_explanation` field containing a technical explanation of why no escalation is needed. The `GenerateOutputNode` detects this classification and publishes a `notification.send` event directly to the reporter via Slack DM, bypassing the engineering board entirely. No Linear ticket is created.

**Key implementation decisions:**
The `allow_reescalation` flag is set to `True` on non-incident notifications, which causes the Notification Worker to include a re-escalation button in the reporter's Slack DM. This ensures the reporter always has a path to escalate if Mila's assessment is wrong, without generating noise for the engineering team.

---

### Use Case 3: Proactive detection via OpenTelemetry

**Scenario:** No human reports anything. eShop emits error spans that are detected by the OTEL Collector before any Incident Manager notices the problem.

**How Mila handles it:**
The OTel Collector (`infra/otel-collector-config.yaml`) receives spans from eShop via OTLP, filters for error-status spans only, and forwards them to Mila's API as JSON webhooks. The API parses the `resourceSpans` payload, extracts service name, trace ID, and error message, and publishes the incident to Redis as a `systemIntegration` source type. The same four-node triage pipeline runs. In `GenerateOutputNode`, proactive incidents receive forced bug classification and forced escalation bias, because system-detected errors represent real observed failures.

**Key implementation decisions:**
The `source_type: systemIntegration` field propagates through the entire pipeline, allowing each node to adjust its behavior. The classification node is aware this is a proactive incident. The output node forces escalation regardless of confidence. The notification worker omits the re-escalation button since there is no human reporter.

---

### Use Case 4: Re-escalation after misclassification

**Scenario:** Mila classifies an incident as a non-incident, but the reporter believes the assessment is wrong and requests a second review.

**How Mila handles it:**
The reporter clicks the re-escalation button in their Slack DM. The Slack interaction webhook fires to the API, which publishes the incident to the Redis `reescalations` channel with the reporter's feedback and the original classification. The agent re-triages the incident with escalation bias applied at the system prompt level and the reporter's feedback included as additional context in the classification prompt. Re-escalated incidents always produce a `bug` classification regardless of confidence.

**Key implementation decisions:**
Re-escalation feedback is sanitized and capped at 500 characters before reaching the LLM. The `original_classification` and `reescalation: True` flags are preserved in `TriageState` and surfaced in the Linear ticket body so engineers can see the full history of the incident.

---

### Use Case 5: Resolution loop closure

**Scenario:** An engineer resolves a Linear ticket. The original reporter needs to be informed that their incident is closed.

**How Mila handles it:**
When an engineer marks a Linear ticket as Done or Resolved, Linear fires a webhook to the Ticket Service (delivered via ngrok tunnel). The Ticket Service verifies the webhook signature via HMAC, looks up the original reporter email from a Redis mapping stored at ticket creation time (90-day TTL), and publishes a `reporter_resolved` notification event to Redis. The Notification Worker sends a Slack DM to the reporter using the Slack Bot API (`users_lookupByEmail` to resolve the email to a user ID, then `chat_postMessage` to open and send to their DM channel).

**Key implementation decisions:**
The Redis ticket mapping stores the `linear_ticket_id → incident_id + reporter_email` relationship at creation time, enabling correlation at resolution without requiring the webhook payload to carry reporter data. An idempotency check (`mark_resolved`) prevents duplicate notifications if Linear fires the webhook more than once. Proactive incidents (no reporter email) are explicitly skipped at the notification step.

---

## 5. Observability

### Structured Logging

Every service emits JSON logs with `timestamp`, `level`, `service`, `event_id`, `incident_id`, and `message` fields. Decision logging is emitted at every pipeline stage including classification chosen, confidence score, severity assessment, and reasoning chain summary.

### LLM Tracing with Langfuse

The Agent instruments all Pydantic AI nodes with OpenTelemetry spans exported to Langfuse (self-hosted at port 3000). Each triage pipeline produces a full trace showing:

1. System prompt and incident context sent to LLM
2. Tool calls (`search_code`, `read_file`) with inputs and outputs
3. Classification response with confidence and reasoning
4. Token usage and latency per step

Access the Langfuse dashboard at `http://localhost:3000` after running `docker compose up`.

### Proactive Detection Pipeline

The OTel Collector receives spans from eShop via OTLP, filters for error-status spans only, and forwards them to Mila's API as incident webhooks. The pipeline configuration is in `infra/otel-collector-config.yaml`.

### Triage Completion Events

Every triage publishes a `triage.completed` event to an observability channel with structured metadata: classification, confidence, severity, source type, duration in milliseconds, files examined, and whether escalation was forced or triggered by re-escalation.

---

## 6. Security & Guardrails

### Prompt Injection Defense

An API middleware (`middleware.py`) scans all user-submitted text before it reaches the agent, detecting 8 known injection patterns including role reassignment, instruction overrides, forget commands, and role switching. When detected, the `prompt_injection_detected` flag is set on the incident event and the agent receives an additional caution addendum in its system prompt. The incident is still processed to avoid denial-of-service via false positives.

The system prompt explicitly instructs the agent to treat all incident data as untrusted input to be analyzed, never as instructions to follow.

### Input Validation and Sanitization

All text fields are stripped of HTML tags, control characters, and excess whitespace before processing. File uploads are validated for MIME type and size (5MB per file, 20MB total, 50MB request limit). Re-escalation feedback is capped at 500 characters.

### Tool Use Safety

GitHub API tools are read-only. Binary files are automatically excluded from code search. File reads are capped at 100KB. Code search is limited to 5 iterations per triage.

### Data Handling

All API keys via environment variables. Linear webhook payloads are verified via HMAC signatures. Langfuse stores traces locally on self-hosted Postgres with no external data transmission. Raw user input is never included in observability events.

---

## 7. Responsible AI

**Transparency** — Every triage decision includes a chain-of-thought reasoning field and a confidence score. Low-confidence classifications are flagged explicitly in both the ticket and the reporter notification.

**Fairness** — Classification criteria are defined explicitly in the system prompt. Severity is assessed independently from reporter input, with any difference between agent and reporter assessment documented in the ticket.

**Accountability** — All triage decisions are logged with full metadata. Reporters can re-escalate any non-incident classification if they disagree with Mila's assessment.

**Privacy** — Raw user input is never included in observability events. Only metadata is emitted to the observability channel.

**Security** — Prompt injection detection, input sanitization, HMAC webhook verification, and read-only tool access are enforced at every stage of the pipeline.
