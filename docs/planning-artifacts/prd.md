---
stepsCompleted: [step-01-init, step-02-discovery, step-02b-vision, step-02c-executive-summary, step-03-success, step-04-journeys, step-05-domain, step-06-innovation, step-07-project-type, step-08-scoping, step-09-functional, step-10-nonfunctional, step-11-polish, step-12-complete]
inputDocuments: [docs/agent-x-hackathon-2026.md, docs/sre_sequence_clean.html]
workflowType: 'prd'
classification:
  projectType: web_app + api_backend
  domain: SRE/DevOps Tooling (AI agent system)
  complexity: medium
  projectContext: greenfield
  targetCodebase: eShop by Microsoft (.NET)
  integrations: [Notion (ticketing), Email (notifications)]
  techStack: TBD
---

# Product Requirements Document - mila

**Author:** sebas
**Date:** April 7, 2026

## Executive Summary

**mila** is an AI-powered SRE Incident Intake & Triage Agent that automates the full incident management lifecycle for e-commerce platform infrastructure. It replaces the manual, time-consuming process of incident triage — where SRE engineers spend significant time reading reports, investigating codebases, classifying severity, and coordinating across teams — with an autonomous agent pipeline that handles everything from intake to resolution notification.

An internal team member (ops lead, support lead, or infrastructure monitor) submits an incident report (text plus screenshots or log files) through a web UI when they observe a technical issue — service availability problems, 500 errors, inter-service timeouts, performance degradation, or failing deployments. The agent creates a helpdesk ticket, then performs deep analysis of the actual codebase (Microsoft eShop, .NET) and its documentation to understand root causes. It classifies the incident as either a non-incident (misconfiguration, expected system behavior, or outside SRE scope) — in which case it auto-resolves the ticket and sends the reporter a specific technical explanation — or a real infrastructure/code bug, for which it creates a detailed engineering ticket (severity, root cause analysis, suggested fix), notifies the team, and monitors through to resolution. When an engineer resolves the issue, the agent closes the loop by updating the helpdesk ticket and notifying the original reporter.

The system uses real integrations — Notion for ticketing, email for notifications — delivering a tangible, verifiable end-to-end workflow with minimal human interaction.

### What Makes This Special

- **End-to-end autonomy:** Not a chatbot or a classifier — a complete pipeline that drives every step from report submission to resolution notification without human coordination
- **Deep code analysis:** The agent reads and analyzes the actual production codebase to produce actionable triage reports with root causes and suggested fixes, giving engineers immediate context instead of vague descriptions
- **Intelligent noise filtering:** Non-incidents (misconfigurations, expected behaviors, out-of-scope reports) are auto-resolved with specific technical explanations, ensuring engineering only sees real infrastructure and code bugs
- **Two-board architecture:** A user-facing Helpdesk board and an internal Engineering Board, with the AI agent serving as the intelligent bridge that enriches context at every handoff
- **Real integrations, not mocks:** Notion, email, and the monitored codebase are all live, making the workflow demonstrable and production-credible

## Project Classification

- **Project Type:** Web application + API backend (incident submission UI + AI agent backend)
- **Domain:** SRE/DevOps Tooling — AI agent orchestration for incident management
- **Complexity:** Medium — multimodal AI processing, multi-step agent pipeline, multiple real external integrations, observability requirements; no heavy regulatory burden
- **Project Context:** Greenfield — built from scratch for the AgentX Hackathon 2026 (April 8-9 build sprint)
- **Target Codebase:** eShop by Microsoft (.NET)

## Success Criteria

### User Success

**Incident Reporter (ops lead, support lead, infrastructure monitor):**
- Non-incident reports are resolved in under 2 minutes with a specific, technical explanation — not a generic "contact support" message, but a targeted response (e.g., "this is an expected behavior during scheduled scaling events — the service auto-recovers within 3 minutes, here's the relevant config")
- The reporter trusts the system after their first interaction because the response demonstrates understanding of the actual infrastructure context
- For real bug reports, the reporter is automatically notified when the issue is resolved — zero need to chase anyone for status

**SRE Engineer:**
- Every engineering ticket answers three questions the engineer would otherwise spend 30+ minutes figuring out:
  1. **Where:** Direct reference to the file and line range in the codebase where the issue likely originates
  2. **Why:** Probable root cause in one clear sentence
  3. **What next:** Suggested first step to investigate or fix
- Original report content and attachments (screenshots, logs) are included in the ticket — no back-and-forth with the reporter
- Engineer opens the ticket and can start working immediately

### Business Success (Hackathon Evaluation)

- **Technical Concept (40%):** Triage reasoning quality is the differentiator — the agent shows its chain of thought: what code it analyzed, what it ruled out, and why it reached its conclusion
- **Creativity & Innovation (20%):** The bug/non-incident bifurcation with distinct handling paths demonstrates architectural creativity beyond a linear pipeline
- **Presentation & Demo (20%):** A clean 3-minute demo with a recognizable SRE scenario (e.g., "checkout service returning 500 errors after a deployment") that anyone can follow
- **Architecture quality:** Clean, well-designed system that fully achieves the hackathon's non-functional requirements (observability, guardrails, responsible AI, multimodal input)

### Technical Success

- Complete end-to-end flow executes autonomously with zero manual intervention between steps
- Multimodal input processing: text + at least one other modality (image, log file)
- Real integrations with Notion (ticketing) and email (notifications) — not mocked
- Observability: logs, traces, and metrics covering ingest → triage → ticket → notify → resolve
- Guardrails: protection against prompt injection and safe tool use
- Responsible AI alignment: fairness, transparency, accountability, privacy, security

### Measurable Outcomes

- Non-incident case: report submitted → specific technical explanation delivered to reporter in < 2 minutes
- Bug case: report submitted → engineering ticket with code references, root cause, and suggested fix created autonomously
- Triage accuracy: correct classification (bug vs non-incident) demonstrated across demo scenarios
- Full loop: submit → triage → ticket → notify → resolve → reporter notified — all steps verifiable in the demo

## User Journeys

> **Note:** Mila is an internal SRE tool. The e-commerce end customer who triggered the original problem is not a system user — they are invisible to these journeys by design.

### Journey 1: Lucia — Non-Incident Resolution (Happy Path)

Lucia, an ops lead on the platform team, notices that response times on the Catalog API have spiked to 3 seconds. She submits a report through the UI — types a description, attaches a Grafana screenshot showing the latency spike. Within seconds she sees her helpdesk ticket confirmed as open. Mila analyzes the eShop codebase and infrastructure context, determines this is expected behavior during the nightly cache warm-up window — not a bug. The helpdesk ticket auto-resolves, and Lucia gets a specific explanation: "This is expected behavior during the scheduled cache rebuild (runs nightly at 02:00 UTC). Latency normalizes within 10 minutes. See `CatalogApi/Startup.cs` cache configuration for the warm-up schedule." She's satisfied — no engineering escalation needed, and she has the technical context to close the internal alert.

**Key capability revealed:** Multimodal intake, autonomous triage against real codebase, actionable non-incident resolution with specific technical guidance.

### Journey 2: Marco — Real Bug Reported (Happy Path)

Marco, a support lead handling escalations, receives reports that the checkout service is returning intermittent 500 errors. He submits a report with a screenshot of the error page and a paste of the service log showing `NullReferenceException` in the ordering pipeline. He immediately sees his helpdesk ticket confirmed as open. Behind the scenes — invisible to Marco — Mila triages the report, identifies the likely source in `OrderingApi/OrderController.cs` where a null basket reference isn't handled when the Redis cache is evicted under load, and creates an engineering ticket in Notion's Engineering Board with file references, root cause ("unhandled null when basket cache entry expires mid-checkout"), and a suggested fix. Marco doesn't know about the internal engineering workflow. He just knows his helpdesk ticket is open and being handled. Days later, when the engineer marks the issue resolved, Marco gets an automatic email: "Your reported incident has been resolved."

**Key capability revealed:** Internal workflow abstraction — reporters see helpdesk status only, never internal engineering details. Full lifecycle notification on resolution.

### Journey 3: Andrea — Engineer Receives Triaged Bug

Andrea, a backend engineer, gets an email notification about a new P2 ticket on the Engineering Board. She opens Notion and finds Mila's triage report with everything she needs: the affected file and line range in the eShop codebase, a one-sentence probable root cause, and a suggested first step to investigate. The original report and Marco's service log are attached. She starts working immediately — no need to go back and ask the reporter for more context. When she fixes the issue and marks the ticket resolved, the system handles the rest.

**Key capability revealed:** The "saves 30 minutes" engineering ticket — three answers (where, why, what next) plus original attachments. Zero back-and-forth.

### Journey 4: Lucia — Misclassification Recovery (Edge Case)

Lucia submits another report — this time the Ordering API is timing out on 10% of requests during normal business hours. Mila analyzes and incorrectly classifies it as expected behavior under load, resolving the ticket with an explanation about auto-scaling thresholds. Lucia reads the response and knows this isn't normal — the timeout rate is well above baseline for this time of day. She clicks "This didn't help" on the resolution response. The helpdesk ticket re-opens and Mila re-escalates: this time it creates an engineering ticket, flagging that the initial classification was overridden by the reporter. The engineering ticket includes Mila's original reasoning alongside the reporter's rejection, giving the engineer full context on why the automated triage missed.

**Key capability revealed:** Graceful misclassification recovery. The system handles its own mistakes transparently rather than dead-ending the reporter. Demonstrates thoughtful edge-case design to judges.

### Journey 5: Diego — Observability & Triage Quality Review

Diego, the team lead, reviews Mila's performance through the observability traces. Every triage decision is logged with full chain-of-thought reasoning: what code files Mila examined, what evidence it weighed, why it classified as bug vs non-incident, and its confidence level. Diego spots that a P3 ticket was classified with low confidence — he reviews the reasoning log and sees Mila flagged uncertainty because the code path was ambiguous. He notes this as a case where the codebase documentation could be improved. The logs serve dual purpose: operational monitoring for Diego's team, and evidence of observability compliance for the hackathon evaluation.

**Key capability revealed:** Every agent decision is traceable with reasoning. Serves both as a product feature (triage quality monitoring) and hackathon requirement (observability evidence).

### Journey Requirements Summary

| Capability | Revealed By |
|---|---|
| Multimodal incident submission (text + image/log) | Journeys 1, 2 |
| Autonomous triage against real codebase | Journeys 1, 2, 4 |
| Non-incident auto-resolution with specific technical guidance | Journey 1 |
| Engineering ticket with file refs, root cause, suggested fix | Journeys 2, 3 |
| Internal workflow abstraction (reporter sees helpdesk only) | Journey 2 |
| Automatic resolution notification to reporter | Journeys 2, 3 |
| "This didn't help" re-escalation mechanism | Journey 4 |
| Chain-of-thought reasoning logs for every triage decision | Journeys 4, 5 |
| Observability traces across full pipeline | Journey 5 |
| Confidence scoring on classifications | Journey 5 |

## Domain-Specific Requirements

> These requirements are scoped to hackathon minimum compliance — pragmatic implementations, not production-grade overengineering.

### Responsible AI — Transparent Reasoning

Mila logs her classification reasoning visibly in every ticket and resolution response. Example: "I classified this as a bug because I found an unhandled null reference in `OrderingApi/OrderController.cs` line 87 — the basket cache entry is not checked before access." This is a feature, not overhead — it satisfies fairness, transparency, and accountability requirements through a single structured output format in the agent's prompt. Every triage decision is explainable and auditable.

**Implementation level:** One prompt instruction + structured output format.

### Guardrails — Prompt Injection Protection

- Basic input sanitization on all user-submitted text before it reaches the LLM
- System prompt instructs the agent to treat all user input as untrusted data, never as instructions
- Simple pattern-matching check that flags reports containing prompt injection indicators
- Documented in `AGENTS_USE.md` as a safety measure

**Implementation level:** System prompt hardening + input validation. No full security layer.

### Data Privacy

- UI displays a note that attachments are processed by the agent and not stored permanently
- Observability traces log metadata only (ticket ID, classification result, confidence) — never raw user input
- No persistent storage of attachment contents beyond what's needed for the active triage

**Implementation level:** Metadata-only logging + UI disclosure. Pragmatic for demo context.

### Observability — Structured Decision Logging

This is the one requirement worth investing in properly. It serves dual purpose: hackathon compliance and the product feature Diego uses in Journey 5.

Every agent decision gets a structured log entry with:
- **Timestamp**
- **Input summary** (metadata, not raw content)
- **Classification result** (bug / non-incident)
- **Reasoning** (what code was analyzed, what was ruled out, why the conclusion was reached)
- **Confidence score**

Visualization via Langfuse or Arize Phoenix with minimal setup — both offer free tiers and fast integration.

**Implementation level:** Structured logging at every decision point + lightweight observability platform integration.

## Technical Architecture Requirements

### UI — Incident Submission Form

- Static SPA form already designed (`docs/mila_ui_final_v1.html`) — functional, clean, minimal
- Anonymous submission, no authentication — the form is a demo input mechanism only
- Fields: title, description, affected component (optional), perceived severity (optional), file attachment (image/log/video)
- Success screen confirms ticket creation with a ticket ID and explains what happens next
- Mila bar provides contextual hints as the user types
- **Not a production UI** — in real-world use, companies have their own helpdesk platforms. Mila receives input from those systems. The form exists solely to demonstrate the end-to-end workflow

### Agent — Separate Event-Driven Service

- The SRE Agent (Mila) runs as a **separate service**, not embedded in the UI backend
- Triggered by events (ticket creation on the Helpdesk board) — not by direct UI calls
- The UI creates a helpdesk ticket → the agent is triggered → the agent performs triage and orchestrates the rest
- This separation is critical: it mirrors real-world deployment where the agent listens to an existing helpdesk system

### Integration Architecture

- All integrations via **API, MCP, or webhook** — whatever each tool supports best
- **Notion** — Helpdesk board (user-facing tickets) and Engineering board (internal triage tickets), accessed via Notion API
- **Email** — notifications to engineering team (new ticket) and to reporter (resolution), via email API/SMTP
- **eShop codebase** — agent reads and analyzes source code for triage, method TBD (local clone, GitHub API, or indexed)
- **Observability platform** — Langfuse or Arize Phoenix for structured decision logging
- Integration quality is the primary differentiator — clean, reliable connections between real systems

### Data Format

- Ticket content must be **clear and information-rich** — format (JSON, markdown, structured text) is secondary to clarity
- Engineering tickets must contain: file/line references, root cause sentence, suggested fix, original report + attachments
- Non-incident resolution responses must contain: specific technical explanation, relevant context

### What Matters vs What Doesn't

| Matters (invest time here) | Doesn't matter (keep minimal) |
|---|---|
| Integration reliability between Notion, email, codebase | UI polish beyond current HTML |
| Triage reasoning quality and depth | Authentication/user management |
| Ticket content clarity and completeness | Real-time UI updates |
| Event-driven agent triggering | UI framework choice |
| Observability across the full pipeline | Browser compatibility |

### Implementation Considerations

- The form can be served as a simple static page — no framework needed
- The agent service needs to handle: event listening, LLM calls (multimodal), Notion API, email API, codebase access
- Docker Compose must orchestrate: UI static server + agent service + any infrastructure (per hackathon requirement)
- All integration credentials via environment variables (`.env.example` with placeholders, never real keys)

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** End-to-end workflow validation — prove the complete incident lifecycle works flawlessly with real integrations. The MVP is not a feature demo; it's a working pipeline.

**Core principle:** Every integration must work, every notification must fire, every step in the workflow must complete. Depth of triage reasoning matters more than breadth of features.

### MVP Feature Set (Phase 1 — April 8)

**Core User Journeys Supported:**
- Journey 1 (Lucia — non-incident resolution)
- Journey 2 (Marco — bug report)
- Journey 3 (Andrea — engineer receives triaged ticket)

**Must-Have Capabilities:**

1. **Incident submission UI** — static form (`mila_ui_final_v1.html`) creates a helpdesk ticket in Notion
2. **Event-driven agent trigger** — agent detects new helpdesk ticket and begins triage
3. **Multimodal triage** — agent analyzes text + attachment against eShop codebase, classifies as bug or non-incident
4. **Bug path:**
   - Engineering ticket created in Notion Engineering Board (file/line refs, root cause, suggested fix, original report + attachment)
   - Email notification sent to engineering team with severity, component, and ticket link
5. **Non-incident path:**
   - Helpdesk ticket updated to Resolved with specific, technical guidance
   - Resolution response delivered to reporter
6. **Resolution notification** — when engineer marks ticket resolved, reporter is notified via email
7. **Observability** — structured decision log for every triage (timestamp, classification, reasoning, confidence) via Langfuse or Arize Phoenix
8. **Guardrails** — input sanitization, system prompt hardening against prompt injection
9. **Docker Compose** — full application runs with `docker compose up --build`
10. **Responsible AI** — transparent reasoning visible in every ticket and resolution

### Post-MVP Features

**Phase 2 — Growth (April 9 if time allows):**

Ordered by impact:
1. **"This didn't help" re-escalation** — misclassification recovery (Journey 4 — Lucia)
2. **Runbook suggestions** in engineering tickets
3. **Severity scoring with explicit reasoning**
4. **Incident deduplication**
5. **Observability dashboard** (skip if tight — decision log in tickets suffices)

**Phase 3 — Vision (Future):**
- Multi-codebase support beyond eShop
- Learning from resolution patterns to improve triage accuracy
- Integration with additional ticketing systems (Jira, Linear) and communicators (Slack, Teams)
- Automated runbook execution — agent-driven remediation

### Risk Mitigation Strategy

**Technical Risks:**
- LLM triage quality may be inconsistent → Invest April 9 in prompt engineering and demo scenario tuning
- Notion API rate limits or latency → Test early, have error handling for API failures
- Multimodal processing (image/log analysis) may be slow → Ensure timeout handling, test with representative attachments

**Integration Risks:**
- Any single integration failure breaks the demo → Test each integration independently before wiring the full pipeline
- Email delivery delays → Use a reliable transactional email service, test deliverability early

**Demo Risks:**
- Triage produces weak analysis on demo day → Pre-test with the exact demo scenario repeatedly, refine prompts
- Flow breaks mid-demo → Have a pre-recorded backup video as fallback

## Functional Requirements

### Incident Submission

- **FR1:** Reporter can submit an incident report with a title and description via a web form
- **FR2:** Reporter can attach one file (image, log, or video) to the incident report
- **FR3:** Reporter can optionally select an affected component from a predefined list
- **FR4:** Reporter can optionally indicate perceived severity (Low / Med / High / Crit)
- **FR5:** System creates a helpdesk ticket in the Helpdesk board upon submission
- **FR6:** Reporter sees a confirmation screen with a ticket ID after submission

### Agent Triage & Classification

- **FR7:** Agent is triggered automatically when a new helpdesk ticket is created
- **FR8:** Agent reads the ticket content including any attached files (multimodal processing)
- **FR9:** Agent analyzes the incident against the eShop codebase (source files and documentation)
- **FR10:** Agent classifies the incident as either an infrastructure/code bug or a non-incident
- **FR11:** Agent produces a confidence score for each classification decision
- **FR12:** Agent logs chain-of-thought reasoning for every classification (what code was examined, what was ruled out, why the conclusion was reached)

### Bug Handling Path

- **FR13:** Agent creates an engineering ticket on the Engineering Board when a bug is classified
- **FR14:** Engineering ticket includes direct reference to the affected file and line range in the codebase
- **FR15:** Engineering ticket includes a one-sentence probable root cause
- **FR16:** Engineering ticket includes a suggested first step to investigate or fix
- **FR17:** Engineering ticket includes the original report content and attachments
- **FR18:** Engineering ticket includes a link back to the helpdesk ticket
- **FR19:** Agent sends email notification to the engineering team when a new engineering ticket is created (with severity, component, and ticket link)

### Non-Incident Handling Path

- **FR20:** Agent updates the helpdesk ticket to Resolved when a non-incident is classified
- **FR21:** Agent provides a specific, technical resolution response (not generic "contact support") explaining why this is not an incident and providing relevant context
- **FR22:** Resolution response is delivered to the reporter

### Resolution Lifecycle

- **FR23:** When an engineer marks an engineering ticket as resolved, the system detects the status change
- **FR24:** System updates the corresponding helpdesk ticket to Resolved
- **FR25:** System sends an email notification to the original reporter that their incident has been resolved

### Observability & Decision Logging

- **FR26:** Every triage decision is logged with a structured entry: timestamp, input summary (metadata only), classification result, reasoning, and confidence score
- **FR27:** Decision logs are sent to an observability platform for visualization and analysis
- **FR28:** Triage reasoning is visible within ticket content (both engineering tickets and non-incident resolutions)

### Guardrails & Safety

- **FR29:** System sanitizes all user-submitted text before it reaches the LLM
- **FR30:** System flags inputs that contain patterns resembling prompt injection attempts
- **FR31:** Agent treats all user input as untrusted data, never as instructions
- **FR32:** Observability traces log metadata only — never raw user input content

### Deployment & Operations

- **FR33:** Full application runs via `docker compose up --build` with no host-level dependencies beyond Docker
- **FR34:** All integration credentials are configured via environment variables
- **FR35:** Repository includes `.env.example` with placeholder values and comments for all required variables

### Repository Deliverables

- **FR36:** Repository includes `README.md` with architecture overview, setup instructions, and project summary
- **FR37:** Repository includes `AGENTS_USE.md` with agent documentation: use cases, implementation details, observability evidence, and safety measures
- **FR38:** Repository includes `SCALING.md` with scaling assumptions and technical decisions
- **FR39:** Repository includes `QUICKGUIDE.md` with step-by-step instructions: clone → copy `.env.example` → fill keys → `docker compose up --build`
- **FR40:** Repository includes `docker-compose.yml` that orchestrates all services and exposes only required ports
- **FR41:** Repository includes `Dockerfile(s)` referenced by `docker-compose.yml`
- **FR42:** Repository is public and licensed under MIT (`LICENSE` file present)

## Non-Functional Requirements

### Performance

- **NFR1:** Non-incident path completes (submission → resolution delivered to reporter) in under 2 minutes
- **NFR2:** Bug path completes (submission → engineering ticket created + team notified) in under 3 minutes
- **NFR3:** UI form submission to helpdesk ticket creation completes in under 5 seconds
- **NFR4:** Agent trigger fires within 30 seconds of helpdesk ticket creation

### Security & Privacy

- **NFR5:** No raw user input (report text, attachment content) appears in observability traces — metadata only
- **NFR6:** All API keys and credentials are loaded from environment variables, never hardcoded or committed
- **NFR7:** LLM system prompt enforces untrusted-input boundary — user content is never interpreted as instructions
- **NFR8:** Input sanitization runs before any user-submitted text reaches the LLM

### Integration Reliability

- **NFR9:** Notion API calls include error handling with clear failure messages if the API is unreachable or rate-limited
- **NFR10:** Email delivery uses a reliable transactional service; failures are logged and do not crash the pipeline
- **NFR11:** Each integration (Notion, email, codebase access) can be tested independently of the others
- **NFR12:** Agent gracefully handles LLM API failures or timeouts without leaving tickets in an inconsistent state

### Observability

- **NFR13:** Every stage of the pipeline (ingest → triage → ticket → notify → resolve) produces at least one trace/log entry
- **NFR14:** Structured decision logs are queryable and visualizable in the observability platform
- **NFR15:** Agent reasoning is human-readable — an evaluator can follow the chain of thought without technical context

### Scalability (Documented for SCALING.md)

- **NFR16:** Architecture supports horizontal scaling of the agent service for concurrent incident processing (documented as a design decision, not implemented for hackathon)
- **NFR17:** No hard-coded single-instance assumptions — agent service is stateless per triage operation

### Deployment

- **NFR18:** `docker compose up --build` from a clean clone with a populated `.env` file results in a fully running application
- **NFR19:** No host-level dependencies required beyond Docker and Docker Compose
- **NFR20:** Application exposes only the required ports (UI, agent service health check if applicable)
