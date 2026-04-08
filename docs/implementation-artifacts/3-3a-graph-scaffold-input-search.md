# Story 3.3a: Triage Graph Scaffold + AnalyzeInput & SearchCode Nodes

> **Epic:** 3 — AI Triage & Code Analysis (Agent)
> **Status:** ready-for-dev
> **Priority:** 🔴 Critical — Core MVP path
> **Depends on:** Story 3.1 (Agent scaffold), Story 3.2 (GitHub tools)
> **FRs:** FR7, FR8, FR9

## Story

**As a** system,
**I want** the Agent to define the pydantic-graph triage pipeline and implement the first two nodes (AnalyzeInputNode + SearchCodeNode),
**So that** incidents are parsed and relevant eShop code is gathered before classification.

## Acceptance Criteria

**Given** the pydantic-graph workflow definition
**When** a developer inspects `graph/workflow.py`
**Then** the graph defines four nodes: `AnalyzeInputNode → SearchCodeNode → ClassifyNode → GenerateOutputNode`
**And** edges are defined via return type hints (pydantic-graph pattern)
**And** state flows through `GraphRunContext[TriageState]`

**Given** an incident has been consumed and loaded into `TriageState`
**When** `AnalyzeInputNode` executes
**Then** it parses incident details: title, description, component, severity, attachments
**And** extracts key signals: error messages, stack traces, file references
**And** processes attachments: images → multimodal input list, logs/text → text content
**And** reads attachment files from `/shared/attachments/{incident_id}/` path
**And** updates `TriageState` with extracted signals

**Given** `AnalyzeInputNode` has populated signal fields in TriageState
**When** `SearchCodeNode` executes
**Then** it invokes the Pydantic AI Agent with tools enabled (search_code, read_file from Story 3.2)
**And** the agent autonomously searches eShop codebase based on incident signals
**And** the agent can iterate: search → read → refine → search again
**And** updates `TriageState.code_context` with gathered code evidence

**Given** an incident includes a file attachment (image or log)
**When** `AnalyzeInputNode` processes it
**Then** images are sent as multimodal vision input to the LLM
**And** log/text files are read and included as text content in the LLM context

## Tasks / Subtasks

- [ ] **1. Define pydantic-graph workflow**
  - `graph/workflow.py` — define the graph with nodes and edges
  - Nodes: `AnalyzeInputNode`, `SearchCodeNode`, `ClassifyNode`, `GenerateOutputNode`
  - Edges defined via return type hints (pydantic-graph pattern)
  - Graph state managed via `GraphRunContext` reading/writing `TriageState`

- [ ] **2. Implement AnalyzeInputNode**
  - `graph/nodes/analyze_input.py`
  - Parses incident data: title, description, component, severity, attachments
  - Extracts key signals: error messages, stack traces, file references
  - Processes attachments: images → multimodal input list, logs/text → text content
  - Reads attachment file from `/shared/attachments/{incident_id}/` path
  - Updates TriageState with extracted signals

- [ ] **3. Implement SearchCodeNode**
  - `graph/nodes/search_code.py`
  - Invokes the Pydantic AI Agent with tools enabled (search_code, read_file from Story 3.2)
  - Agent autonomously searches eShop codebase based on incident signals
  - Agent can iterate: search → read → refine → search again
  - Updates TriageState with code context gathered

- [ ] **4. Wire graph pipeline to consumer**
  - Connect Story 3.1's consumer to the graph pipeline
  - TriageState → graph run → (ClassifyNode and GenerateOutputNode are stubs until Story 3.3b)

## Dev Notes

### Architecture Guardrails
- **pydantic-graph state machine (AR8):** Each node is a class with `run()` method. Edges are return type annotations. State flows via `GraphRunContext`.
- **Hexagonal (AR1, AR5):** Graph nodes live in `graph/nodes/`. They call domain logic and ports, never adapters directly.
- **ER3 — event_id correlation:** Include `event_id` in ALL log entries within graph nodes.
- **AR2 — Redis envelope:** Any Redis messages published from the graph must follow the mandatory envelope format.

### Pydantic-Graph Node Pattern
```python
from pydantic_graph import BaseNode, GraphRunContext, End

class AnalyzeInputNode(BaseNode[TriageState]):
    async def run(self, ctx: GraphRunContext[TriageState]) -> SearchCodeNode:
        # Parse incident, extract signals
        ctx.state.signals = extract_signals(ctx.state.incident)
        return SearchCodeNode()
```

### Key Reference Files
- Architecture doc: `docs/planning-artifacts/architecture.md` — agent service, pydantic-graph pattern
- Story 3.1: Consumer that feeds this pipeline
- Story 3.2: GitHub tools used by SearchCodeNode
- Story 3.3b: ClassifyNode and GenerateOutputNode (depends on this story)

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
