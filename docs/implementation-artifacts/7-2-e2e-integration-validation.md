# Story 7.2: End-to-End Pipeline Integration Validation

> **Epic:** 7 — Deployment, Integration & Documentation
> **Status:** ready-for-dev
> **Priority:** 🔴 Critical — Demo readiness
> **Depends on:** Story 7.1 (Docker Compose finalized), all Epics 1-6

## Story

**As a** team,
**I want** to verify the complete incident lifecycle works end-to-end across all services,
**So that** we can confidently demo the full flow.

## Acceptance Criteria

**Given** all services are running via Docker Compose
**When** a reporter submits a bug report through the UI (e.g., "Checkout 500 errors — NullReferenceException in OrderController")
**Then** the full bug path executes:
1. UI → API → Redis (`incident.created`, `source_type: "userIntegration"`)
2. Agent consumes → triages → classifies as bug with confidence and severity
3. Agent → `ticket.create` → Ticket Service → Linear engineering ticket created
4. Ticket Service → `notification.send` → Notification Worker → Slack channel alert + Slack DM to reporter
**And** total time is under 3 minutes (NFR2)

**Given** eShop produces an error trace via OTEL
**When** the OTEL Collector webhooks to the API
**Then** the proactive path executes:
1. OTEL Collector → API → Redis (`incident.created`, `source_type: "systemIntegration"`)
2. Agent consumes → triages → always escalated
3. Agent → `ticket.create` → Ticket Service → Linear ticket
4. Ticket Service → `notification.send` → Slack channel alert (no reporter DM)

**Given** a reporter submits a non-incident (e.g., "Catalog API latency spike" — expected cache warm-up)
**When** the agent classifies as non-incident
**Then** the non-incident path executes:
1. Agent → `notification.send` directly to Notification Worker
2. Notification Worker → Slack DM to reporter with technical explanation + "This didn't help" button
**And** total time is under 2 minutes (NFR1)

**Given** the reporter clicks "This didn't help" on the Slack DM
**When** the re-escalation triggers
**Then** the re-escalation path executes:
1. Slack interaction → API → Redis `reescalations` channel
2. Agent re-processes → forces bug classification → publishes `ticket.create`
3. Ticket Service → Linear ticket → Notification Worker → Slack DM confirmation

**Given** an engineer resolves a ticket in Linear
**When** Linear fires the resolution webhook
**Then** the resolution path executes:
1. Linear → Ticket Service → `notification.send` (reporter_resolved)
2. Notification Worker → Slack DM to reporter

## Tasks / Subtasks

- [ ] **1. Test bug path (user-reported)**
  - Submit incident via UI form
  - Verify all 4 stages complete
  - Verify Linear ticket content (file refs, root cause, reasoning, severity)
  - Verify Slack channel alert + reporter DM
  - Verify total time < 3 minutes

- [ ] **2. Test proactive path (OTEL)**
  - Trigger error in eShop or simulate OTEL webhook
  - Verify forced escalation, no reporter DM
  - Verify "🤖 Proactive Detection" indicator in ticket

- [ ] **3. Test non-incident path**
  - Submit a non-incident report
  - Verify Slack DM with technical explanation
  - Verify "This didn't help" button present
  - Verify total time < 2 minutes

- [ ] **4. Test re-escalation path**
  - Click re-escalation button (or simulate Slack interaction webhook)
  - Verify agent re-triages with forced bug classification
  - Verify "🔄 Re-escalated" indicator in ticket
  - Verify reporter confirmation DM

- [ ] **5. Test resolution path**
  - Mark ticket as Done in Linear (or simulate webhook)
  - Verify reporter receives resolution DM

- [ ] **6. Test confidence/severity analysis**
  - Submit borderline cases, verify low-confidence indicators
  - Verify severity analysis in tickets (with and without reporter severity)

- [ ] **7. Verify Langfuse traces**
  - Open `http://localhost:3000`
  - Verify traces for each triage
  - Verify tool calls, token usage, metadata visible

- [ ] **8. Fix integration gaps**
  - Document and fix any issues found during testing

## Dev Notes

### Architecture Guardrails
- **This is a validation story** — no new code, just testing and fixing integration issues.
- **Test with actual integrations:** Linear API, Slack API, GitHub API.
- **NFR1/NFR2 timing:** Non-incident < 2 min, Bug path < 3 min.

### Demo Scenarios
| # | Scenario | Path | Key Things to Verify |
|---|---|---|---|
| 1 | Bug report | UI → API → Agent → Ticket → Slack | Full E2E, ticket quality |
| 2 | Proactive OTEL | Collector → API → Agent → Ticket → Slack | Forced escalation |
| 3 | Non-incident | UI → API → Agent → Slack DM | Direct notification, button |
| 4 | Re-escalation | Slack button → API → Agent → Ticket → Slack | Self-correction |
| 5 | Resolution | Linear → Ticket Service → Slack DM | Webhook processing |

### Key Reference Files
- All story files in `docs/implementation-artifacts/`
- PRD: `docs/planning-artifacts/prd.md` — user journeys, success criteria
- Architecture: `docs/planning-artifacts/architecture.md`

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
