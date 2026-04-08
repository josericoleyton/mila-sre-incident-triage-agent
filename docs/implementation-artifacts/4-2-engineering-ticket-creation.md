# Story 4.2: Engineering Ticket Creation in Linear

> **Epic:** 4 — Ticket Lifecycle Management (Ticket-Service)
> **Status:** done
> **Priority:** 🔴 Critical — Core MVP path
> **Depends on:** Story 4.1 (Ticket-Service scaffold)
> **FRs:** FR5, FR14, FR15, FR16, FR17, FR18

## Story

**As an** SRE engineer,
**I want** an engineering ticket automatically created in Linear with file references, root cause, and suggested fix from the agent's triage,
**So that** I can start investigating immediately without back-and-forth.

## Acceptance Criteria

**Given** the Ticket-Service consumes a `ticket.create` event with `action: "create_engineering_ticket"`
**When** the service processes the command
**Then** it creates a ticket in the Linear Engineering Board with:
- **Title:** Agent-generated title with severity prefix (e.g., "[P2] NullReferenceException in OrderController.cs")
- **Body (markdown):** The pre-formatted body from the Agent containing all triage sections (affected files, root cause, suggested fix, original report, tracking ID, attachments, reasoning, confidence/severity)
- **Labels:** Component, severity, `triaged-by-mila`
- **Priority:** Mapped from agent's severity assessment

**Given** ticket creation succeeds
**When** the Linear API returns the created ticket
**Then** the Ticket-Service publishes a `notification.send` event to the `notifications` channel with:
- `type: "team_alert"`
- Linear ticket URL, severity, component, summary
- `reporter_slack_user_id`: from the ticket command (for reporter update)

**Given** ticket creation succeeds and `reporter_slack_user_id` is not null
**When** the notification event is constructed
**Then** a second `notification.send` event is published with:
- `type: "reporter_update"`
- `slack_user_id`: the reporter's Slack user ID
- `message`: "Your incident report has been received and escalated to the engineering team. Tracking ID: {incident_id}"

**Given** the Linear API is unavailable or returns an error
**When** the Ticket-Service attempts to create the ticket
**Then** it retries up to 2 times with exponential backoff
**And** if all retries fail, publishes a `ticket.error` event
**And** does NOT publish any notification events

## Tasks / Subtasks

- [x] **1. Create LinearClient outbound adapter**
  - `adapters/outbound/linear_client.py`
  - Uses `httpx.AsyncClient` (AR4)
  - Method: `create_issue(title, body, priority, labels, team_id) -> dict`
  - Linear GraphQL API endpoint: `https://api.linear.app/graphql`
  - Auth: Bearer token from `config.LINEAR_API_KEY`

- [x] **2. Implement ticket creation domain logic**
  - `domain/services.py` — `create_engineering_ticket(command: TicketCommand) -> TicketResult`
  - Map severity to Linear priority: P1→Urgent(1), P2→High(2), P3→Medium(3), P4→Low(4)
  - Call LinearClient to create issue
  - Return ticket URL and ID on success

- [x] **3. Implement retry with exponential backoff**
  - Max 2 retries (total 3 attempts)
  - Backoff: 1s, 2s
  - On final failure: publish `ticket.error` event to `errors` channel

- [x] **4. Publish team notification after success**
  - `notification.send` event with `type: "team_alert"` to `notifications` channel
  - Payload: ticket_url, severity, component, summary, incident_id

- [x] **5. Publish reporter notification after success (if reporter exists)**
  - Only if `reporter_slack_user_id` is not null (null for proactive incidents)
  - `notification.send` event with `type: "reporter_update"`
  - Message: "Your incident report has been received and escalated. Tracking ID: {incident_id}"

- [x] **6. Store ticket-incident mapping**
  - After successful Linear creation, store mapping: `linear_ticket_id → incident_id + reporter_slack_user_id`
  - Options: store in Linear ticket body metadata, or lightweight Redis hash lookup
  - Needed by Story 4.3 to correlate resolution webhooks back to incidents

## Dev Notes

### Architecture Guardrails
- **AR10 — Notification ONLY after ticket success:** Never publish notification events if Linear API fails. The flow is: Linear API success → notification. This prevents orphan Slack messages.
- **httpx only (AR4):** Linear GraphQL API via `httpx.AsyncClient`. Never `requests`.
- **Hexagonal (AR1, AR5):** LinearClient is outbound adapter behind a port interface. Domain logic in `services.py`.
- **Single Engineering Board:** One team ID from config. No helpdesk board.
- **ER3 — event_id correlation:** Propagate `event_id` from the incoming `ticket.create` event into ALL log entries and published notifications.
- **AR2 — Redis envelope:** Published `notification.send` and `ticket.created` events must follow the mandatory envelope format.
- **ER8 — ports before adapters:** Define `TicketCreator` port interface before implementing `LinearClient` adapter.

### Linear GraphQL API
```graphql
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue {
      id
      identifier
      url
    }
  }
}
```

### Priority Mapping
| Agent Severity | Linear Priority | Value |
|---|---|---|
| P1 | Urgent | 1 |
| P2 | High | 2 |
| P3 | Medium | 3 |
| P4 | Low | 4 |

### Key Reference Files
- Story 3.4: Agent publishes the ticket.create command this story consumes
- Story 4.1: Scaffold and routing
- Story 4.3: Resolution lifecycle (needs incident-ticket mapping from this story)
- Story 5.2: Notification-Worker consumes the team_alert event

## File List

- `services/ticket-service/src/ports/outbound.py` — Added `TicketCreator` port interface
- `services/ticket-service/src/adapters/outbound/linear_client.py` — LinearClient adapter with retry logic
- `services/ticket-service/src/domain/models.py` — Added `TicketResult` model
- `services/ticket-service/src/domain/services.py` — Full ticket creation domain logic, notification publishing, mapping
- `services/ticket-service/src/main.py` — Wired LinearClient into service startup
- `tests/test_engineering_ticket_creation.py` — 24 tests covering all ACs
- `tests/test_ticket_service_scaffold.py` — Updated 1 test for new `handle_ticket_command` signature
- `requirements-test.txt` — Added `fastapi` dependency

## Change Log

- 2026-04-08: Implemented Story 4.2 — Engineering Ticket Creation in Linear. All 6 tasks complete. 24 new tests + 23 existing scaffold tests pass (47 total, 0 regressions).

## Dev Agent Record

### Implementation Plan
- ER8: Defined `TicketCreator` port before implementing `LinearClient` adapter
- AR4: Used `httpx.AsyncClient` for Linear GraphQL API
- AR1/AR5: Hexagonal architecture — `LinearClient` is outbound adapter behind `TicketCreator` port
- AR10: Notifications ONLY published after Linear API success
- AR2: All published events follow mandatory Redis envelope format via `RedisPublisher`
- Retry: 3 total attempts (1 initial + 2 retries) with 1s, 2s exponential backoff
- Ticket-incident mapping published to `ticket-mappings` channel for Story 4.3 correlation

### Completion Notes
- All 6 tasks complete, all acceptance criteria satisfied
- 24 new unit tests covering: severity mapping, ticket creation flow, team/reporter notifications, retry logic, error handling
- Updated `handle_ticket_command` signature to accept optional `ticket_creator` — backward compatible
- Pre-existing failures in `test_triage_command_publishing.py` and `test_ui_nginx.py` are unrelated to this story
