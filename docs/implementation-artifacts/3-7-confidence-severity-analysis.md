# Story 3.7: Confidence-Based Decision Quality & Severity Analysis

> **Epic:** 3 — AI Triage & Code Analysis (Agent)
> **Status:** ready-for-dev
> **Priority:** 🟢 Low — Agent intelligence polish (demo impact)
> **Depends on:** Story 3.3b (Classification pipeline), Story 3.4 (Bug path), Story 3.6 (Non-incident path)
> **FRs:** FR11

## Story

**As a** hackathon evaluator,
**I want** to see the agent self-assess its classification certainty and independently evaluate severity with testable quality indicators,
**So that** the demo demonstrates sophisticated analytical capabilities and low-confidence classifications are clearly flagged.

## Acceptance Criteria

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
- Delta explanation: if they differ, the agent explains why

**Given** no severity was provided by the reporter
**When** the agent assesses severity
**Then** severity is based entirely on code analysis with no reference to reporter input

## Tasks / Subtasks

- [ ] **1. Configure confidence threshold**
  - `CONFIDENCE_THRESHOLD` in `config.py` (default: 0.75, float)
  - Read from env var

- [ ] **2. Enhance ticket body for low-confidence bugs**
  - In Story 3.4's ticket formatting code
  - If confidence < threshold: add `🟡 Low Confidence` section
  - Include: score, uncertainty reasons from reasoning field

- [ ] **3. Enhance notification for low-confidence non-incidents**
  - In Story 3.6's notification construction
  - Already handled by the caveat logic — verify it works with real confidence values

- [ ] **4. Enhance severity analysis in system prompt**
  - Update `domain/prompts.py` to instruct the agent on severity assessment:
    - Always produce P1-P4 severity with code-based justification
    - If reporter provided severity, acknowledge it and explain any difference
    - If no reporter severity, assess purely from code analysis
  - Severity criteria: P1 (critical/data loss), P2 (major feature broken), P3 (minor/workaround exists), P4 (cosmetic/low impact)

- [ ] **5. Format severity_assessment in ticket body**
  - Include agent's severity, reporter's input (if provided), delta explanation
  - Example: "Agent severity: P2 (checkout flow impacted, workaround exists). Reporter indicated: High. Delta: Agent downgraded because the affected path only triggers on empty carts."

## Dev Notes

### Architecture Guardrails
- **This story enhances Stories 3.3, 3.4, and 3.6** — it doesn't add new infrastructure, just richer intelligence in existing flows.
- **Config (AR3):** `CONFIDENCE_THRESHOLD` from `config.py`.
- **Demo impact:** This is a hackathon differentiator. Judges see self-aware agent behavior.

### Severity Mapping
| Agent Severity | Priority | Description |
|---|---|---|
| P1 | Urgent | Critical failure, data loss, complete service outage |
| P2 | High | Major feature broken, significant user impact |
| P3 | Medium | Minor issue, workaround exists, limited impact |
| P4 | Low | Cosmetic, enhancement, minimal user impact |

### Key Reference Files
- Story 3.3b: Classification pipeline (produces confidence + severity)
- Story 3.4: Bug path ticket formatting (enhanced with low-confidence indicator)
- Story 3.6: Non-incident notification (enhanced with confidence caveat)

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
