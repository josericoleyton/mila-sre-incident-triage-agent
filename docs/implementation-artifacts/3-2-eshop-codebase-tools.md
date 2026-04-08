# Story 3.2: eShop Codebase Analysis Tools (GitHub API)

> **Epic:** 3 — AI Triage & Code Analysis (Agent)
> **Status:** done
> **Priority:** 🔴 Critical — Core MVP path
> **Depends on:** Story 3.1 (Agent scaffold)
> **FRs:** FR9

## Story

**As an** agent,
**I want** to search and read files from the eShop GitHub repository during triage reasoning,
**So that** I can identify the source code relevant to reported incidents.

## Acceptance Criteria

**Given** the Agent is processing an incident
**When** the agent reasoning loop calls the `search_code` tool with a query string
**Then** the tool executes a GitHub Code Search API request against the `dotnet/eShop` repository
**And** returns a list of matching file paths and code snippets
**And** the agent can iterate — searching, reading results, searching again with refined queries

**Given** the agent calls the `read_file` tool with a file path
**When** the tool executes
**Then** it fetches the full file content from the GitHub Contents API
**And** returns the file content as a string for the agent to analyze

**Given** the GitHub API returns an error (rate limit, 404, timeout)
**When** the tool encounters the error
**Then** it returns a descriptive error message to the agent (not an exception)
**And** the agent can decide to retry, try a different query, or proceed with available information

**Given** a `GITHUB_TOKEN` is configured
**When** the tools make API requests
**Then** the token is used for authentication (higher rate limits)
**And** if no token is configured, tools still work for public repos with lower rate limits

## Tasks / Subtasks

- [x] **1. Create GitHubClient outbound adapter**
  - `adapters/outbound/github_client.py`
  - Uses `httpx.AsyncClient` (AR4 — never `requests`)
  - Methods: `search_code(query: str) -> list[dict]`, `get_file_content(path: str) -> str`
  - Base URL: `https://api.github.com`
  - Auth: Bearer token from `config.GITHUB_TOKEN` (optional)
  - Repository: `dotnet/eShop` (hardcoded for hackathon)

- [x] **2. Implement search_code tool**
  - `graph/tools/search_code.py`
  - Pydantic AI tool using `@agent.tool` decorator
  - Receives `RunContext[TriageDeps]` for dependency injection
  - Calls `GitHubClient.search_code(query)`
  - GitHub Code Search API: `GET /search/code?q={query}+repo:dotnet/eShop`
  - Returns formatted list: file path, matched snippet, relevance score

- [x] **3. Implement read_file tool**
  - `graph/tools/read_file.py`
  - Pydantic AI tool using `@agent.tool` decorator
  - Calls `GitHubClient.get_file_content(path)`
  - GitHub Contents API: `GET /repos/dotnet/eShop/contents/{path}`
  - Decodes base64 content from API response
  - Returns file content as plain text string

- [x] **4. Error handling**
  - Rate limit (403/429): return "GitHub API rate limit reached. Try a different query or wait."
  - 404: return "File not found: {path}"
  - Timeout: return "GitHub API timeout. Proceeding with available information."
  - Never raise exceptions — always return descriptive string messages

- [x] **5. Create TriageDeps dependency container**
  - Dataclass/model holding `github_client: GitHubClient`
  - Passed to agent via `RunContext` for tool dependency injection

## Dev Notes

### Architecture Guardrails
- **Hexagonal pattern:** GitHubClient is an outbound adapter. Define a port interface `CodeRepository` in `ports/outbound.py`. Tools call the port, not the adapter directly (AR1, AR5).
- **httpx only (AR4):** Never use `requests`. Use `httpx.AsyncClient` with connection pooling.
- **Config only (AR3):** `GITHUB_TOKEN` from `config.py`.
- **Pydantic AI tools (AR8):** Tools use `@agent.tool` decorator and receive deps via `RunContext[TriageDeps]`.

### GitHub API Details
```python
# Code Search
GET https://api.github.com/search/code?q={query}+repo:dotnet/eShop
Headers: Authorization: Bearer {GITHUB_TOKEN}
Response: { "items": [{ "name": "...", "path": "...", "html_url": "...", "text_matches": [...] }] }

# File Contents
GET https://api.github.com/repos/dotnet/eShop/contents/{path}
Headers: Authorization: Bearer {GITHUB_TOKEN}
Response: { "content": "base64...", "encoding": "base64", "name": "...", "path": "..." }
```

### eShop Architecture Context (for system prompt)
The agent's system prompt should include a brief overview of the eShop repository structure so it can make intelligent search queries:
- `src/Catalog.API/` — Product catalog service
- `src/Ordering.API/` — Order processing
- `src/Basket.API/` — Shopping cart
- `src/WebApp/` — Frontend Blazor app
- `src/eShop.ServiceDefaults/` — Shared configuration

### Key Reference Files
- Architecture doc: `docs/planning-artifacts/architecture.md` — GitHub API integration details
- Story 3.1: Agent scaffold and TriageDeps
- Story 3.3a: Graph pipeline that uses these tools (SearchCodeNode)

## File List

- `services/agent/src/ports/outbound.py` — Added `CodeRepository` port interface
- `services/agent/src/adapters/outbound/github_client.py` — `GitHubClient` adapter (httpx, base64 decode, error handling)
- `services/agent/src/domain/models.py` — Added `TriageDeps` dataclass
- `services/agent/src/graph/tools/search_code.py` — `search_code` tool function
- `services/agent/src/graph/tools/read_file.py` — `read_file` tool function
- `services/agent/src/graph/tools/__init__.py` — Tool exports
- `tests/test_eshop_codebase_tools.py` — 24 tests covering all ACs

## Change Log

- **2026-04-08:** Implemented Story 3.2 — GitHubClient adapter, search_code/read_file tools, TriageDeps container, CodeRepository port, full error handling, 24 unit tests (all pass, 0 regressions).
- **2026-04-08:** Code review — applied 2 patches: (P1) large file truncation guard at 100KB to protect LLM context window, (P2) handle >1MB files where GitHub returns download_url instead of content. Added 2 edge-case tests. 100/100 tests pass.

## Chat Command Log

- Added `CodeRepository` abstract port in `ports/outbound.py` (hexagonal pattern AR1/AR5)
- Implemented `GitHubClient` with `httpx.AsyncClient`, Bearer auth (optional), rate-limit/404/timeout handling returning descriptive strings (never exceptions)
- Created `TriageDeps` dataclass in `domain/models.py` holding `github_client: CodeRepository` and `publisher: EventPublisher`
- Implemented `search_code` tool — calls port, formats top-10 results with snippets, handles error/empty states
- Implemented `read_file` tool — calls port, returns decoded file content or error string
- Wrote 24 tests: port compliance, adapter unit tests (success/error paths), tool formatting/routing tests, auth header tests
- Full regression suite: 98/98 passed
