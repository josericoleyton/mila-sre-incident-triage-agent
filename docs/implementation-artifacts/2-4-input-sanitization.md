# Story 2.4: Input Sanitization & Prompt Injection Detection Middleware

> **Epic:** 2 — Incident Submission Experience (UI + API)
> **Status:** ready-for-dev
> **Priority:** 🟡 Medium — Security hardening
> **Depends on:** Story 2.2 (API endpoint exists)
> **FRs:** FR29, FR30, FR31

## Story

**As a** system,
**I want** all user-submitted text to be sanitized and checked for prompt injection patterns before it reaches the LLM pipeline,
**So that** the system is protected against adversarial inputs.

## Acceptance Criteria

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

## Tasks / Subtasks

- [ ] **1. Create sanitization middleware**
  - `adapters/inbound/middleware.py` in the API service
  - Register as FastAPI middleware on the app
  - Only applies to `POST /api/incidents` (OTEL webhooks are trusted internal traffic)

- [ ] **2. Implement text sanitization**
  - Strip HTML tags (regex or lightweight library like `bleach` — but prefer regex to avoid dependency)
  - Remove null bytes (`\x00`) and control characters
  - Normalize excessive whitespace (collapse multiple spaces/newlines)
  - Trim leading/trailing whitespace

- [ ] **3. Implement prompt injection pattern detection**
  - Regex-based pattern matching for common injection phrases:
    - "ignore previous instructions"
    - "you are now"
    - "system:" / "assistant:" / "user:" (role-switching)
    - "forget everything"
    - "disregard" + "instructions"
  - Flag detected patterns in a metadata field, do NOT reject the submission
  - Log structured warning: `{ "type": "prompt_injection_detected", "pattern": "<matched>", "incident_id": "..." }`

- [ ] **4. Pass flag to Redis event**
  - The `prompt_injection_detected` boolean must be included in the `incident.created` event payload
  - The Agent reads this flag in Story 3.3b to apply extra caution in the system prompt

## Dev Notes

### Architecture Guardrails
- **Hackathon-level guardrail:** This is NOT a production WAF. Simple regex patterns suffice.
- **No false-positive blocking:** Flagged submissions are still processed — the flag is informational for the Agent.
- **Trusted internal traffic:** OTEL webhook payloads (`/api/webhooks/otel`) bypass sanitization — they come from the internal Docker network.
- **NFR7, NFR8:** Input sanitization runs BEFORE any user text reaches the LLM. Agent system prompt enforces untrusted-input boundary.

### Injection Patterns (Starter Set)
```python
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"you\s+are\s+now",
    r"^(system|assistant|user)\s*:",
    r"forget\s+everything",
    r"disregard\s+.*instructions",
    r"do\s+not\s+follow",
    r"new\s+instruction",
    r"role\s*:\s*(system|assistant)",
]
```

### Key Reference Files
- Architecture doc: `docs/planning-artifacts/architecture.md` — security architecture section
- Story 2.2: API endpoint that this middleware wraps
- Story 3.3b: Agent reads `prompt_injection_detected` flag

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
