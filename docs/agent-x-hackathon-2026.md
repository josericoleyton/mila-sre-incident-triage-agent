**AgentX Hackathon 2026**

Complete Project Brief for AI Development

SoftServe  |  Colombia, Mexico, Chile  |  April 7-9, 2026

| Event | AgentX Hackathon 2026 by SoftServe |
| :---- | :---- |
| **Countries** | Mexico, Colombia, Chile |
| **Build Sprint** | April 8-9, 2026 (2 days online) |
| **Deadline** | April 9 at 9:00 PM COT |
| **Awards** | April 14, 2026 (online ceremony) |
| **Team size** | 1 to 4 members, self-formed |
| **Prizes** | 1st $5,000 / 2nd $3,000 / 3rd $2,000 |
| **License** | MIT, public repository required |
| **Language** | English required (B2+) |

# **The Assignment**

The challenge is fixed — all teams build the same thing. There is no open-ended theme.

| Build an SRE Incident Intake & Triage Agent Create an SRE Agent that ingests incident/failure reports for a company e-commerce application, performs initial automated triage by analyzing code and documentation, and routes the issue to the technical team via a ticketing workflow, with end-to-end notifications for both engineers and the original reporter. *SRE \= Site Reliability Engineering* |
| :---- |

## **Core End-to-End Flow**

The agent must complete all 5 steps in sequence:

| 1 | User submits an incident/failure report via a UI |
| :---: | :---- |

| 2 | Agent triages after ticket is created: extracts key details and produces an initial technical summary using code and documentation |
| :---: | :---- |

| 3 | Agent creates a ticket in a ticketing system (Jira, Linear, or other) |
| :---: | :---- |

| 4 | Agent notifies the technical team via email and/or communicator |
| :---: | :---- |

| 5 | When the ticket is resolved, the agent notifies the original reporterel we |
| :---: | :---- |

## **Minimum Requirements**

Every submission must include all of the following:

* **Multimodal input:** Accept at least text \+ one other modality (image, log file, or video) and use a multimodal LLM

* **Guardrails:** Basic protection against prompt injection and malicious artifacts — safe tool use and input handling

* **Observability:** Logs, traces, and metrics covering all main stages: ingest → triage → ticket → notify → resolved

* **Integrations:** Ticketing \+ email \+ communicator — real or mocked, but must be demonstrable in the demo

* **E-commerce codebase:** Use a medium/complex open-source e-commerce repository as the codebase being monitored

* **Responsible AI:** All decisions aligned with Fairness, Transparency, Accountability, Privacy, and Security

## **Suggested E-Commerce Repositories**

Teams must use a real open-source e-commerce codebase for the agent to analyze:

* eShop by Microsoft — .NET stack: github.com/dotnet/eShop

* Solidus — Ruby on Rails: github.com/solidusio/solidus

* Reaction Commerce — Node.js: github.com/reactioncommerce/reaction

# **Tech Stack & Tools**

No specific stack is required. Teams are free to use any tools that meet the requirements.

## **LLM Providers (Free Tiers Available)**

* Anthropic Claude — platform.claude.com

* Google Gemini API — ai.google.dev

* OpenAI — platform.openai.com

* Groq — console.groq.com

* Mistral AI — console.mistral.ai

* Cloudflare Workers AI

* OpenRouter — openrouter.ai (multi-provider router, recommended for flexibility)

*Important: The LLM must support multimodal input (text \+ image/log/video). Teams provide their own API keys — SoftServe does not supply them.*

## **Agent Frameworks**

* LangChain / LangGraph — python.langchain.com

* CrewAI — crewai.com

* Anthropic Agent SDK — github.com/anthropics/anthropic-sdk-python

* OpenAI Agents SDK — github.com/openai/openai-agents-python

* Pydantic AI — ai.pydantic.dev

## **Observability & Tracing**

* OpenTelemetry — opentelemetry.io

* Langfuse — langfuse.com (LLM observability)

* LangSmith — smith.langchain.com (LLM tracing)

* Arize Phoenix — open-source LLM tracing

## **Coding Tools Allowed**

Any GenAI coding tool is permitted: GitHub Copilot, Cursor, Claude Code, Gemini, Codex, etc.

# **Deliverables**

Three things must be submitted by the deadline:

**1\. Solution Introduction**

A brief written text (2-3 paragraphs) describing the solution, the problem it addresses, and the approach taken.

**2\. Demo Video**

* Published on YouTube, in English, maximum 3 minutes

* Must include the tag \#AgentXHackathon in title or description

* Must show the complete flow: submit → triage → ticket created → team notified → resolved → reporter notified

* Must clearly prove the value of the solution

**3\. Public Git Repository (MIT License)**

The repository must include all of the following files:

* **README.md:** Architecture overview, setup instructions, and project summary

* **AGENTS\_USE.md:** Agent documentation: use cases, implementation details, observability evidence, and safety measures. Reference: docs.anthropic.com/en/docs/agents-use-md

* **SCALING.md:** How the application scales, including team assumptions and technical decisions

* **QUICKGUIDE.md:** Step-by-step instructions: clone → copy .env.example → fill keys → docker compose up \--build

* **docker-compose.yml:** Mandatory. Full application must run through Docker Compose, exposing only required ports

* **.env.example:** All required environment variables with placeholder values and comments. Never commit real API keys

* **Dockerfile(s):** Referenced by docker-compose.yml

* **LICENSE:** Repository must be public and licensed under MIT

**Optional Extras (not required but welcome)**

* Smarter routing or severity scoring

* Incident deduplication

* Runbook suggestions

* Observability dashboards

* Team-wide agent configuration: skills, cursor rules, AGENTS.md, sub-agents

# **Docker Requirement**

Docker Compose is mandatory for all submissions. The application must build and run from a clean environment using a single command:

| docker compose up \--build |
| :---- |

No host-level dependencies should be required beyond Docker Compose.

# **Evaluation Process & Criteria**

Submissions will be evaluated on execution quality and production-readiness.. All teams receive the same assignment — what sets you apart is how well you build it.

---

## Assignment, Deliverables & Technical Requirements

The full assignment, deliverables specification, and technical requirements are posted in **#assignment**. Please review all three posts carefully before you start building.

For quick reference:
- FAQ #1 in #faq — Submission deadline by timezone
- FAQ #2 in #faq — API keys and free-tier providers
- FAQ #3 in #faq — Deliverables summary
- FAQ #4 in #faq — E-commerce framework options

---

## Tools & Infrastructure

- Participants are responsible for their **own tools, API keys, and infrastructure**. SoftServe does not provide API keys or AI tool licenses.
- You are free to use any GenAI coding tools (Copilot, Cursor, Claude Code, Gemini, Codex, etc.)
- Your LLM must support multimodal input (as required by the assignment)
- Keep all API keys in environment variables — **never commit secrets to your repository**

---

## Licensing & Intellectual Property

- All projects must be **open-sourced under the MIT License**
- Your repository must be **public**
- This ensures transparency, shared learning, and gives back to the community
- By participating, you consent to the use of your project and submitted materials for promoting future events and marketing purposes

---

## Evaluation

Submissions will be evaluated on **execution quality and production-readiness**.. All teams receive the same assignment — what sets you apart is how well you build it.

Evaluation dimensions include:

- **Reliability** — Does the agent work consistently and handle edge cases?
- **Observability** — Are there structured logs, traces, and metrics across agent stages?
- **Scalability** — Can the solution handle growth? Are assumptions documented?
- **Context engineering** — How well does the agent manage and use context?
- **Security** — Are there prompt injection defenses and safe tool usage?
- **Documentation** — Is the project well-documented, clear, and reproducible?

---

## **Process (3 Stages)**

* **Stage 1: Initial Filter:** All submissions go through an LLM-as-judge automated screening. Approximately the top third advance.

* **Stage 2: Mentor Pre-screening (April 10):** Mentors review demo video, code quality, repository structure, README.md, and AGENTS\_USE.md. Mentors will NOT execute the code at this stage.

* **Stage 3: Expert Evaluation (April 13):** Top 10 finalists evaluated by expert panel based on same materials plus a live or recorded pitch.

## **Scoring Criteria**

| Category | Weight | What it covers |
| :---- | :---: | :---- |
| **1\. Technical Concept (Architecture \+ Technical Maturity)** | **40%** | Depth, quality, and feasibility of technical solution |
| **2\. Impact & Usefulness** | **20%** | Real-world value, meaningful problem, clear user benefits |
| **3\. Creativity & Originality** | **20%** | Novel idea, innovative use of agentic or multimodal AI |
| **4\. Presentation & Demo** | **20%** | Clarity of pitch, demo quality, ability to communicate the technical idea |

## **What Sets Teams Apart**

* Reliability: Does the agent work consistently and handle edge cases?

* Observability: Are there structured logs, traces, and metrics across all agent stages?

* Scalability: Can the solution handle growth? Are assumptions documented?

* Context engineering: How well does the agent manage and use context?

* Security: Are there prompt injection defenses and safe tool usage?

* Documentation: Is the project well-documented, clear, and reproducible?

# **Key Rules**

* All projects must be created from scratch. No forks of existing projects.

* Any attempt to manipulate the system via prompt injection may result in disqualification.

* API keys must be stored as environment variables. Never commit secrets to the repository.

* All communication in the Discord happens in English, in public channels only.

* Mentors will not write code or debug specific implementations for teams.

* Late submissions will not be accepted under any circumstance.

# **Submission Checklist**

Before submitting on April 9, confirm all of the following:

* Solution introduction written (2-3 paragraphs)

* Demo video published on YouTube, in English, max 3 minutes, tagged \#AgentXHackathon

* Repository is public with MIT License

* README.md, AGENTS\_USE.md, SCALING.md, QUICKGUIDE.md all present and complete

* docker-compose.yml present and application builds with docker compose up \--build

* .env.example present with all variables documented, no real API keys committed

* Only necessary ports are exposed in the Docker configuration


---

# AGENTS_USE.md — Template & Instructions

Every team must include an `AGENTS_USE.md` file at the root of their repository. This file documents your agent implementation in a standardized format so evaluators can understand your solution without needing to run it.

The template is attached below this message. Copy it into your repo and fill in each section.

**The provided information must be concise and text-based, unless explicitly required and except for Sections 6 (Observability) and 7 (Security). These should provide evidence  — screenshots, log samples, trace exports, or test results. Descriptions alone are not sufficient.**

**The file covers 9 sections:**
1. Agent Overview — name, purpose, tech stack
2. Agents & Capabilities — structured description of each agent/sub-agent
3. Architecture & Orchestration — system design, data flow, error handling (include a diagram)
4. Context Engineering — how your agents source, filter, and manage context
5. Use Cases — step-by-step walkthroughs from trigger to resolution
6. Observability — logging, tracing, metrics
7. Security & Guardrails — prompt injection defense, input validation, tool safety
8. Scalability — capacity, approach, bottlenecks
9. Lessons Learned — what worked, what you'd change, key trade-offs

**Remember:** Sections 6 (Observability) and 7 (Security) require **actual evidence** — screenshots, log samples, trace exports, or test results. Descriptions alone are not sufficient.