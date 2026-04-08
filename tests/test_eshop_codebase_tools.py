"""
Tests for eShop Codebase Analysis Tools (GitHub API).

Covers:
- GitHubClient.search_code: success, rate limit, timeout, empty results
- GitHubClient.get_file_content: success, 404, rate limit, timeout, base64 decoding
- search_code tool: formats results, handles errors, handles empty
- read_file tool: returns content, propagates errors
- CodeRepository port compliance
- TriageDeps dependency container

Run:
    pytest tests/test_eshop_codebase_tools.py -v
"""

import base64
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Module loading helpers
# ---------------------------------------------------------------------------

def _add_service_to_path(service: str):
    svc_path = str(_PROJECT_ROOT / "services" / service)
    if svc_path not in sys.path:
        sys.path.insert(0, svc_path)


_add_service_to_path("agent")

from src.adapters.outbound.github_client import GitHubClient, GITHUB_API_BASE, REPO, MAX_FILE_SIZE
from src.domain.models import TriageDeps
from src.graph.tools.search_code import search_code
from src.graph.tools.read_file import read_file
from src.ports.outbound import CodeRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_search_response(items: list[dict], status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json={"total_count": len(items), "items": items},
        request=httpx.Request("GET", f"{GITHUB_API_BASE}/search/code"),
    )


def _make_content_response(content_str: str, path: str = "src/test.cs", status_code: int = 200) -> httpx.Response:
    encoded = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
    return httpx.Response(
        status_code=status_code,
        json={
            "name": path.split("/")[-1],
            "path": path,
            "content": encoded,
            "encoding": "base64",
        },
        request=httpx.Request("GET", f"{GITHUB_API_BASE}/repos/{REPO}/contents/{path}"),
    )


def _make_error_response(status_code: int, url: str = "/search/code") -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json={"message": "error"},
        request=httpx.Request("GET", f"{GITHUB_API_BASE}{url}"),
    )


def _mock_run_context(github_client: CodeRepository):
    """Create a mock RunContext[TriageDeps] for tool testing."""
    publisher = AsyncMock()
    deps = TriageDeps(github_client=github_client, publisher=publisher)
    ctx = MagicMock()
    ctx.deps = deps
    return ctx


# ---------------------------------------------------------------------------
# CodeRepository port compliance
# ---------------------------------------------------------------------------

class TestCodeRepositoryPort:
    def test_github_client_implements_code_repository(self):
        assert issubclass(GitHubClient, CodeRepository)

    def test_port_defines_search_code(self):
        assert hasattr(CodeRepository, "search_code")

    def test_port_defines_get_file_content(self):
        assert hasattr(CodeRepository, "get_file_content")


# ---------------------------------------------------------------------------
# TriageDeps tests
# ---------------------------------------------------------------------------

class TestTriageDeps:
    def test_triage_deps_holds_github_client(self):
        mock_client = AsyncMock(spec=CodeRepository)
        mock_publisher = AsyncMock()
        deps = TriageDeps(github_client=mock_client, publisher=mock_publisher)
        assert deps.github_client is mock_client
        assert deps.publisher is mock_publisher


# ---------------------------------------------------------------------------
# GitHubClient.search_code tests
# ---------------------------------------------------------------------------

class TestGitHubClientSearchCode:
    @pytest.mark.asyncio
    async def test_search_code_success(self):
        items = [
            {
                "name": "CatalogController.cs",
                "path": "src/Catalog.API/Controllers/CatalogController.cs",
                "html_url": "https://github.com/dotnet/eShop/blob/main/src/Catalog.API/Controllers/CatalogController.cs",
                "score": 1.0,
                "text_matches": [{"fragment": "public class CatalogController"}],
            }
        ]
        mock_response = _make_search_response(items)

        client = GitHubClient(token="test-token")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get = AsyncMock(return_value=mock_response)

        results = await client.search_code("CatalogController")

        assert len(results) == 1
        assert results[0]["path"] == "src/Catalog.API/Controllers/CatalogController.cs"
        assert results[0]["name"] == "CatalogController.cs"
        assert results[0]["score"] == 1.0
        assert "public class CatalogController" in results[0]["snippets"]

    @pytest.mark.asyncio
    async def test_search_code_empty_results(self):
        mock_response = _make_search_response([])

        client = GitHubClient(token="test-token")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get = AsyncMock(return_value=mock_response)

        results = await client.search_code("nonexistent_query_xyz")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_code_rate_limit_403(self):
        mock_response = _make_error_response(403)

        client = GitHubClient(token="test-token")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get = AsyncMock(return_value=mock_response)

        results = await client.search_code("test")
        assert len(results) == 1
        assert "rate limit" in results[0]["error"].lower()

    @pytest.mark.asyncio
    async def test_search_code_rate_limit_429(self):
        mock_response = _make_error_response(429)

        client = GitHubClient(token="test-token")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get = AsyncMock(return_value=mock_response)

        results = await client.search_code("test")
        assert len(results) == 1
        assert "rate limit" in results[0]["error"].lower()

    @pytest.mark.asyncio
    async def test_search_code_timeout(self):
        client = GitHubClient(token="test-token")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        results = await client.search_code("test")
        assert len(results) == 1
        assert "timeout" in results[0]["error"].lower()

    @pytest.mark.asyncio
    async def test_search_code_uses_repo_qualifier(self):
        mock_response = _make_search_response([])

        client = GitHubClient(token="test-token")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get = AsyncMock(return_value=mock_response)

        await client.search_code("OrderController")
        call_args = client._client.get.call_args
        assert call_args[0][0] == "/search/code"
        assert f"repo:{REPO}" in call_args[1]["params"]["q"]


# ---------------------------------------------------------------------------
# GitHubClient.get_file_content tests
# ---------------------------------------------------------------------------

class TestGitHubClientGetFileContent:
    @pytest.mark.asyncio
    async def test_get_file_content_success(self):
        file_content = "using Microsoft.AspNetCore;\npublic class Program { }"
        mock_response = _make_content_response(file_content, "src/Catalog.API/Program.cs")

        client = GitHubClient(token="test-token")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get = AsyncMock(return_value=mock_response)

        result = await client.get_file_content("src/Catalog.API/Program.cs")
        assert result == file_content

    @pytest.mark.asyncio
    async def test_get_file_content_404(self):
        mock_response = _make_error_response(404, "/repos/dotnet/eShop/contents/nonexistent.cs")

        client = GitHubClient(token="test-token")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get = AsyncMock(return_value=mock_response)

        result = await client.get_file_content("nonexistent.cs")
        assert "File not found" in result
        assert "nonexistent.cs" in result

    @pytest.mark.asyncio
    async def test_get_file_content_rate_limit(self):
        mock_response = _make_error_response(403, "/repos/dotnet/eShop/contents/test.cs")

        client = GitHubClient(token="test-token")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get = AsyncMock(return_value=mock_response)

        result = await client.get_file_content("test.cs")
        assert "rate limit" in result.lower()

    @pytest.mark.asyncio
    async def test_get_file_content_timeout(self):
        client = GitHubClient(token="test-token")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        result = await client.get_file_content("test.cs")
        assert "timeout" in result.lower()

    @pytest.mark.asyncio
    async def test_get_file_content_base64_decoding(self):
        original = "Hello World\nLine 2"
        encoded = base64.b64encode(original.encode("utf-8")).decode("utf-8")
        mock_response = httpx.Response(
            status_code=200,
            json={"name": "test.txt", "path": "test.txt", "content": encoded, "encoding": "base64"},
            request=httpx.Request("GET", f"{GITHUB_API_BASE}/repos/{REPO}/contents/test.txt"),
        )

        client = GitHubClient(token="test-token")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get = AsyncMock(return_value=mock_response)

        result = await client.get_file_content("test.txt")
        assert result == original

    @pytest.mark.asyncio
    async def test_get_file_content_large_file_truncated(self):
        large_content = "x" * (MAX_FILE_SIZE + 500)
        encoded = base64.b64encode(large_content.encode("utf-8")).decode("utf-8")
        mock_response = httpx.Response(
            status_code=200,
            json={"name": "big.cs", "path": "big.cs", "content": encoded, "encoding": "base64"},
            request=httpx.Request("GET", f"{GITHUB_API_BASE}/repos/{REPO}/contents/big.cs"),
        )

        client = GitHubClient(token="test-token")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get = AsyncMock(return_value=mock_response)

        result = await client.get_file_content("big.cs")
        assert "truncated" in result
        assert len(result) < len(large_content)

    @pytest.mark.asyncio
    async def test_get_file_content_oversized_no_content_field(self):
        mock_response = httpx.Response(
            status_code=200,
            json={"name": "huge.bin", "path": "huge.bin", "download_url": "https://raw.githubusercontent.com/..."},
            request=httpx.Request("GET", f"{GITHUB_API_BASE}/repos/{REPO}/contents/huge.bin"),
        )

        client = GitHubClient(token="test-token")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get = AsyncMock(return_value=mock_response)

        result = await client.get_file_content("huge.bin")
        assert "too large" in result.lower()


# ---------------------------------------------------------------------------
# search_code tool tests
# ---------------------------------------------------------------------------

class TestSearchCodeTool:
    @pytest.mark.asyncio
    async def test_tool_formats_results(self):
        mock_client = AsyncMock(spec=CodeRepository)
        mock_client.search_code.return_value = [
            {
                "path": "src/Catalog.API/Program.cs",
                "name": "Program.cs",
                "html_url": "https://github.com/...",
                "score": 1.0,
                "snippets": ["public class Program"],
            }
        ]
        ctx = _mock_run_context(mock_client)

        result = await search_code(ctx, "Program")
        assert "src/Catalog.API/Program.cs" in result
        assert "Found 1 results" in result

    @pytest.mark.asyncio
    async def test_tool_handles_empty_results(self):
        mock_client = AsyncMock(spec=CodeRepository)
        mock_client.search_code.return_value = []
        ctx = _mock_run_context(mock_client)

        result = await search_code(ctx, "nonexistent")
        assert "No results found" in result

    @pytest.mark.asyncio
    async def test_tool_handles_error_response(self):
        mock_client = AsyncMock(spec=CodeRepository)
        mock_client.search_code.return_value = [
            {"error": "GitHub API rate limit reached. Try a different query or wait."}
        ]
        ctx = _mock_run_context(mock_client)

        result = await search_code(ctx, "test")
        assert "rate limit" in result.lower()

    @pytest.mark.asyncio
    async def test_tool_limits_to_10_results(self):
        mock_client = AsyncMock(spec=CodeRepository)
        mock_client.search_code.return_value = [
            {"path": f"file{i}.cs", "name": f"file{i}.cs", "score": 1.0, "snippets": []}
            for i in range(20)
        ]
        ctx = _mock_run_context(mock_client)

        result = await search_code(ctx, "test")
        assert "showing top 10" in result


# ---------------------------------------------------------------------------
# read_file tool tests
# ---------------------------------------------------------------------------

class TestReadFileTool:
    @pytest.mark.asyncio
    async def test_tool_returns_file_content(self):
        mock_client = AsyncMock(spec=CodeRepository)
        mock_client.get_file_content.return_value = "public class CatalogController { }"
        ctx = _mock_run_context(mock_client)

        result = await read_file(ctx, "src/Catalog.API/Controllers/CatalogController.cs")
        assert "CatalogController" in result
        mock_client.get_file_content.assert_awaited_once_with("src/Catalog.API/Controllers/CatalogController.cs")

    @pytest.mark.asyncio
    async def test_tool_propagates_404_message(self):
        mock_client = AsyncMock(spec=CodeRepository)
        mock_client.get_file_content.return_value = "File not found: bad.cs"
        ctx = _mock_run_context(mock_client)

        result = await read_file(ctx, "bad.cs")
        assert "File not found" in result

    @pytest.mark.asyncio
    async def test_tool_propagates_timeout_message(self):
        mock_client = AsyncMock(spec=CodeRepository)
        mock_client.get_file_content.return_value = "GitHub API timeout. Proceeding with available information."
        ctx = _mock_run_context(mock_client)

        result = await read_file(ctx, "some/file.cs")
        assert "timeout" in result.lower()


# ---------------------------------------------------------------------------
# GitHubClient auth header tests
# ---------------------------------------------------------------------------

class TestGitHubClientAuth:
    def test_with_token_sets_auth_header(self):
        client = GitHubClient(token="my-token")
        assert client._client.headers["authorization"] == "Bearer my-token"

    def test_no_token_omits_auth_header(self):
        client = GitHubClient(token="")
        assert "authorization" not in client._client.headers
