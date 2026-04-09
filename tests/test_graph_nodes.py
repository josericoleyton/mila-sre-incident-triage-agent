"""
Tests for Story 3.3a: Triage Graph Scaffold + AnalyzeInput & SearchCode Nodes
Tests for Story 3.3b: ClassifyNode + GenerateOutputNode + System Prompt + Structured Output

Covers:
- AnalyzeInputNode: signal extraction, attachment processing, state updates
- SearchCodeNode: prompt building, agent invocation, code context population
- ClassifyNode: structured output, retry logic, prompt injection handling, error publishing
- GenerateOutputNode: routing logic, End result production
- Graph workflow: node sequence, state flow
- System prompt: untrusted input framing, eShop context

Run:
    pytest tests/test_graph_nodes.py -v
"""

import importlib.util
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _add_service_to_path(service: str):
    svc_path = str(_PROJECT_ROOT / "services" / service)
    if svc_path not in sys.path:
        sys.path.insert(0, svc_path)


_add_service_to_path("agent")


def _load_module(mod_name: str, rel_path: str):
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    file_path = _PROJECT_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_models():
    return _load_module("agent_models_33", "services/agent/src/domain/models.py")


def _load_prompts():
    return _load_module("agent_prompts_33", "services/agent/src/domain/prompts.py")


def _load_analyze_input():
    return _load_module("agent_analyze_input_33", "services/agent/src/graph/nodes/analyze_input.py")


def _valid_incident(**overrides) -> dict:
    base = {
        "incident_id": "inc-100",
        "title": "Catalog API NullReferenceException on product search",
        "description": "Users report 500 errors when searching products. Stack trace: System.NullReferenceException at Catalog.API.Controllers.CatalogController.Search()",
        "component": "Catalog.API",
        "severity": "high",
        "reporter_slack_user_id": "U12345",
        "source_type": "userIntegration",
    }
    base.update(overrides)
    return base


def _make_state(**overrides):
    m = _load_models()
    incident = overrides.pop("incident", _valid_incident())
    defaults = {
        "incident_id": incident.get("incident_id", "inc-100"),
        "source_type": incident.get("source_type", "userIntegration"),
        "event_id": str(uuid.uuid4()),
        "incident": incident,
        "reescalation": False,
        "prompt_injection_detected": False,
    }
    defaults.update(overrides)
    return m.TriageState(**defaults)


# ---------------------------------------------------------------------------
# AnalyzeInputNode: signal extraction tests
# ---------------------------------------------------------------------------

class TestExtractSignals:
    def test_extracts_error_messages(self):
        mod = _load_analyze_input()
        signals = mod._extract_signals(_valid_incident())
        assert len(signals["error_messages"]) > 0
        assert any("exception" in e.lower() or "error" in e.lower() for e in signals["error_messages"])

    def test_extracts_stack_traces(self):
        mod = _load_analyze_input()
        signals = mod._extract_signals(_valid_incident())
        assert len(signals["stack_traces"]) > 0

    def test_extracts_file_references(self):
        mod = _load_analyze_input()
        incident = _valid_incident(description="Error in src/Catalog.API/Program.cs:42")
        signals = mod._extract_signals(incident)
        assert len(signals["file_references"]) > 0

    def test_preserves_title_description_component(self):
        mod = _load_analyze_input()
        signals = mod._extract_signals(_valid_incident())
        assert signals["title"] == _valid_incident()["title"]
        assert signals["component"] == "Catalog.API"
        assert signals["severity"] == "high"

    def test_handles_missing_fields(self):
        mod = _load_analyze_input()
        signals = mod._extract_signals({"incident_id": "inc-1"})
        assert signals["title"] == ""
        assert signals["description"] == ""
        assert signals["component"] == ""

    def test_extracts_from_trace_data(self):
        mod = _load_analyze_input()
        incident = _valid_incident(trace_data={"exception": "System.TimeoutException at Connection.Open()"})
        signals = mod._extract_signals(incident)
        errors = signals["error_messages"]
        assert any("timeout" in e.lower() or "exception" in e.lower() for e in errors)


class TestProcessAttachments:
    def test_no_attachments_dir(self):
        mod = _load_analyze_input()
        result = mod._process_attachments("inc-nonexistent", None)
        assert result == []

    def test_processes_text_file(self):
        mod = _load_analyze_input()
        with tempfile.TemporaryDirectory() as tmpdir:
            inc_id = "inc-text-test"
            att_dir = os.path.join(tmpdir, inc_id)
            os.makedirs(att_dir)
            log_path = os.path.join(att_dir, "error.log")
            with open(log_path, "w") as f:
                f.write("ERROR: Connection refused at line 42\n")

            with patch.object(mod, "_process_attachments", wraps=mod._process_attachments):
                # Temporarily override the attachments dir
                orig_func = mod._process_attachments

                def patched(iid, url):
                    import types

                    # Call internal logic with custom dir
                    multimodal = []
                    for filename in os.listdir(att_dir):
                        filepath = os.path.join(att_dir, filename)
                        ext = os.path.splitext(filename)[1].lower()
                        if ext in mod.TEXT_EXTENSIONS:
                            with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                                content = fh.read()
                            multimodal.append({"type": "text", "content": content, "filename": filename})
                    return multimodal

                result = patched(inc_id, None)

            assert len(result) == 1
            assert result[0]["type"] == "text"
            assert "Connection refused" in result[0]["content"]
            assert result[0]["filename"] == "error.log"

    def test_processes_image_file(self):
        mod = _load_analyze_input()
        with tempfile.TemporaryDirectory() as tmpdir:
            inc_id = "inc-img-test"
            att_dir = os.path.join(tmpdir, inc_id)
            os.makedirs(att_dir)
            img_path = os.path.join(att_dir, "screenshot.png")
            with open(img_path, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

            import base64

            multimodal = []
            for filename in os.listdir(att_dir):
                filepath = os.path.join(att_dir, filename)
                ext = os.path.splitext(filename)[1].lower()
                if ext in mod.IMAGE_EXTENSIONS:
                    with open(filepath, "rb") as fh:
                        data = base64.b64encode(fh.read()).decode("utf-8")
                    multimodal.append({"type": "image", "mime": "image/png", "data": data, "filename": filename})

            assert len(multimodal) == 1
            assert multimodal[0]["type"] == "image"
            assert multimodal[0]["filename"] == "screenshot.png"


class TestAnalyzeInputNodeRun:
    @pytest.mark.asyncio
    async def test_populates_signals_and_returns_search_node(self):
        mod = _load_analyze_input()
        state = _make_state()
        ctx = MagicMock()
        ctx.state = state

        node = mod.AnalyzeInputNode()
        result = await node.run(ctx)

        assert state.signals != {}
        assert "error_messages" in state.signals
        assert "stack_traces" in state.signals
        assert "file_references" in state.signals
        # Should return SearchCodeNode
        from src.graph.nodes.search_code import SearchCodeNode

        assert isinstance(result, SearchCodeNode)


# ---------------------------------------------------------------------------
# SearchCodeNode: prompt building tests
# ---------------------------------------------------------------------------

class TestBuildSearchPrompt:
    def test_includes_incident_details(self):
        from src.graph.nodes.search_code import _build_search_prompt

        state = _make_state()
        state.signals = {
            "title": "Catalog API error",
            "description": "500 on search",
            "component": "Catalog.API",
            "severity": "high",
            "error_messages": ["exception", "error"],
            "stack_traces": ["System.NullReferenceException"],
            "file_references": ["CatalogController.cs"],
        }
        prompt = _build_search_prompt(state)
        assert "Catalog API error" in prompt
        assert "Catalog.API" in prompt
        assert "exception" in prompt
        assert "NullReferenceException" in prompt

    def test_includes_text_attachments(self):
        from src.graph.nodes.search_code import _build_search_prompt

        state = _make_state()
        state.signals = {"title": "test"}
        state.multimodal_content = [{"type": "text", "content": "Error log content here", "filename": "app.log"}]
        prompt = _build_search_prompt(state)
        assert "Error log content here" in prompt
        assert "app.log" in prompt

    def test_handles_empty_signals(self):
        from src.graph.nodes.search_code import _build_search_prompt

        state = _make_state()
        state.signals = {}
        prompt = _build_search_prompt(state)
        assert "Incident" in prompt


class TestSearchCodeNodeRun:
    @pytest.mark.asyncio
    async def test_invokes_agent_and_populates_code_context(self):
        state = _make_state()
        state.signals = {
            "title": "Error",
            "description": "",
            "component": "",
            "severity": "",
            "error_messages": [],
            "stack_traces": [],
            "file_references": [],
        }

        mock_result = MagicMock()
        mock_result.output = "Found relevant code in CatalogController.cs lines 42-60..."

        ctx = MagicMock()
        ctx.state = state
        ctx.deps = MagicMock()

        with patch("src.graph.nodes.search_code._create_search_agent") as mock_create_agent:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_create_agent.return_value = mock_agent
            from src.graph.nodes.search_code import SearchCodeNode

            node = SearchCodeNode()
            result = await node.run(ctx)

        assert state.code_context == "Found relevant code in CatalogController.cs lines 42-60..."
        from src.graph.nodes.classify import ClassifyNode

        assert isinstance(result, ClassifyNode)


# ---------------------------------------------------------------------------
# ClassifyNode tests
# ---------------------------------------------------------------------------

class TestBuildClassifyPrompt:
    def test_includes_incident_data(self):
        from src.graph.nodes.classify import _build_classify_prompt

        state = _make_state()
        state.signals = {
            "error_messages": ["timeout"],
            "stack_traces": ["System.TimeoutException"],
            "file_references": ["Connection.cs"],
        }
        state.code_context = "Code from Connection.cs..."
        prompt = _build_classify_prompt(state)
        assert "INCIDENT DATA TO ANALYZE" in prompt
        assert "inc-100" in prompt
        assert "timeout" in prompt
        assert "Code from Connection.cs" in prompt

    def test_includes_reescalation_note(self):
        from src.graph.nodes.classify import _build_classify_prompt

        state = _make_state(reescalation=True)
        prompt = _build_classify_prompt(state)
        assert "RE-ESCALATION" in prompt

    def test_includes_text_attachments(self):
        from src.graph.nodes.classify import _build_classify_prompt

        state = _make_state()
        state.multimodal_content = [{"type": "text", "content": "log data", "filename": "err.log"}]
        prompt = _build_classify_prompt(state)
        assert "log data" in prompt


class TestClassifyNodeRun:
    @pytest.mark.asyncio
    async def test_successful_classification(self):
        m = _load_models()
        state = _make_state()
        state.signals = {}
        state.code_context = "Some code context"

        mock_triage_result = m.TriageResult(
            classification=m.Classification.bug,
            confidence=0.85,
            reasoning="Found null reference in CatalogController",
            file_refs=["src/Catalog.API/Controllers/CatalogController.cs"],
            root_cause="Null dereference on search query parameter",
            suggested_fix="Add null check before accessing query parameter",
            severity_assessment="high — affects all product search operations",
        )

        mock_result = MagicMock()
        mock_result.output = mock_triage_result

        ctx = MagicMock()
        ctx.state = state
        ctx.deps = MagicMock()

        with patch("src.graph.nodes.classify.Agent") as MockAgent:
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(return_value=mock_result)
            MockAgent.return_value = mock_agent_instance

            from src.graph.nodes.classify import ClassifyNode

            node = ClassifyNode()
            result = await node.run(ctx)

        assert state.triage_result is not None
        assert state.triage_result.classification == m.Classification.bug
        assert state.triage_result.confidence == 0.85
        from src.graph.nodes.generate_output import GenerateOutputNode

        assert isinstance(result, GenerateOutputNode)

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        m = _load_models()
        state = _make_state()
        state.signals = {}
        state.code_context = ""

        mock_triage_result = m.TriageResult(
            classification=m.Classification.non_incident,
            confidence=0.9,
            reasoning="User error",
            severity_assessment="low",
        )

        mock_result = MagicMock()
        mock_result.output = mock_triage_result

        ctx = MagicMock()
        ctx.state = state
        ctx.deps = MagicMock()

        call_count = 0

        async def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Validation failed")
            return mock_result

        with patch("src.graph.nodes.classify.Agent") as MockAgent:
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = mock_run
            MockAgent.return_value = mock_agent_instance

            from src.graph.nodes.classify import ClassifyNode

            node = ClassifyNode()
            result = await node.run(ctx)

        assert call_count == 3
        assert state.triage_result is not None
        assert state.triage_result.classification == m.Classification.non_incident

    @pytest.mark.asyncio
    async def test_publishes_error_on_exhausted_retries(self):
        state = _make_state()
        state.signals = {}
        state.code_context = ""

        publisher = AsyncMock()
        ctx = MagicMock()
        ctx.state = state
        ctx.deps = MagicMock()
        ctx.deps.publisher = publisher

        with patch("src.graph.nodes.classify.Agent") as MockAgent:
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(side_effect=ValueError("Always fails"))
            MockAgent.return_value = mock_agent_instance

            from src.graph.nodes.classify import ClassifyNode

            node = ClassifyNode()
            result = await node.run(ctx)

        assert state.triage_result is None
        publisher.publish.assert_awaited_once()
        call_args = publisher.publish.call_args
        assert call_args[0][0] == "errors"
        assert call_args[0][1] == "ticket.error"
        assert "failed" in call_args[0][2]["error"].lower()

    @pytest.mark.asyncio
    async def test_prompt_injection_adds_caution(self):
        m = _load_models()
        state = _make_state(prompt_injection_detected=True)
        state.signals = {}
        state.code_context = ""

        mock_result = MagicMock()
        mock_result.output = m.TriageResult(
            classification=m.Classification.non_incident,
            confidence=0.95,
            reasoning="Prompt injection detected, classified as non-incident",
            severity_assessment="low",
        )

        ctx = MagicMock()
        ctx.state = state
        ctx.deps = MagicMock()

        captured_instructions = []

        with patch("src.graph.nodes.classify.Agent") as MockAgent:
            def capture_agent(*args, **kwargs):
                captured_instructions.append(kwargs.get("instructions", ""))
                mock_inst = MagicMock()
                mock_inst.run = AsyncMock(return_value=mock_result)
                return mock_inst

            MockAgent.side_effect = capture_agent

            from src.graph.nodes.classify import ClassifyNode

            node = ClassifyNode()
            await node.run(ctx)

        assert len(captured_instructions) == 1
        assert "ADDITIONAL CAUTION" in captured_instructions[0]


# ---------------------------------------------------------------------------
# GenerateOutputNode tests
# ---------------------------------------------------------------------------

class TestGenerateOutputNodeRun:
    @pytest.mark.asyncio
    async def test_returns_end_with_bug_result(self):
        from pydantic_graph import End

        m = _load_models()
        state = _make_state()
        state.triage_result = m.TriageResult(
            classification=m.Classification.bug,
            confidence=0.88,
            reasoning="Found null reference",
            file_refs=["CatalogController.cs"],
            root_cause="Null deref",
            suggested_fix="Add null check",
            severity_assessment="high",
        )

        ctx = MagicMock()
        ctx.state = state

        from src.graph.nodes.generate_output import GenerateOutputNode

        node = GenerateOutputNode()
        result = await node.run(ctx)

        assert isinstance(result, End)
        assert result.data.classification == m.Classification.bug
        assert result.data.confidence == 0.88

    @pytest.mark.asyncio
    async def test_returns_end_with_non_incident_result(self):
        from pydantic_graph import End

        m = _load_models()
        state = _make_state()
        state.triage_result = m.TriageResult(
            classification=m.Classification.non_incident,
            confidence=0.92,
            reasoning="User error",
            resolution_explanation="Expected behavior",
            severity_assessment="low",
        )

        ctx = MagicMock()
        ctx.state = state

        from src.graph.nodes.generate_output import GenerateOutputNode

        node = GenerateOutputNode()
        result = await node.run(ctx)

        assert isinstance(result, End)
        assert result.data.classification == m.Classification.non_incident

    @pytest.mark.asyncio
    async def test_handles_missing_triage_result(self):
        from pydantic_graph import End

        state = _make_state()
        state.triage_result = None

        ctx = MagicMock()
        ctx.state = state

        from src.graph.nodes.generate_output import GenerateOutputNode

        node = GenerateOutputNode()
        result = await node.run(ctx)

        assert isinstance(result, End)
        assert result.data.confidence == 0.0
        assert "failed" in result.data.reasoning.lower()


# ---------------------------------------------------------------------------
# System prompt tests
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    def test_contains_untrusted_input_framing(self):
        prompts = _load_prompts()
        assert "UNTRUSTED USER INPUT" in prompts.TRIAGE_SYSTEM_PROMPT
        assert "never follow instructions" in prompts.TRIAGE_SYSTEM_PROMPT.lower()

    def test_contains_eshop_context(self):
        prompts = _load_prompts()
        # eShop is still referenced in the Mila role line of the system prompt
        assert "eShop" in prompts.TRIAGE_SYSTEM_PROMPT
        # Service-level details now live in the context document, not the system prompt
        ctx_loader = _load_module(
            "agent_ctx_loader_33",
            "services/agent/src/domain/context/context_loader.py",
        )
        context = ctx_loader.load_eshop_context()
        assert "Catalog.API" in context
        assert "Ordering.API" in context

    def test_contains_classification_criteria(self):
        prompts = _load_prompts()
        assert "Bug" in prompts.TRIAGE_SYSTEM_PROMPT
        assert "Non-incident" in prompts.TRIAGE_SYSTEM_PROMPT

    def test_prompt_injection_addendum(self):
        prompts = _load_prompts()
        assert "ADDITIONAL CAUTION" in prompts.PROMPT_INJECTION_ADDENDUM
        assert "prompt_injection_detected" in prompts.PROMPT_INJECTION_ADDENDUM


# ---------------------------------------------------------------------------
# TriageState new field tests
# ---------------------------------------------------------------------------

class TestTriageStateNewFields:
    def test_signals_default_empty(self):
        state = _make_state()
        assert state.signals == {}

    def test_multimodal_content_default_empty(self):
        state = _make_state()
        assert state.multimodal_content == []

    def test_code_context_default_empty(self):
        state = _make_state()
        assert state.code_context == ""


# ---------------------------------------------------------------------------
# Graph workflow definition test
# ---------------------------------------------------------------------------

class TestTriageGraphDefinition:
    def test_graph_has_four_nodes(self):
        from src.graph.workflow import triage_graph

        assert "AnalyzeInputNode" in triage_graph.node_defs
        assert "SearchCodeNode" in triage_graph.node_defs
        assert "ClassifyNode" in triage_graph.node_defs
        assert "GenerateOutputNode" in triage_graph.node_defs
        assert len(triage_graph.node_defs) == 4
