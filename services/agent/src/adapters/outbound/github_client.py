import base64
import logging
from typing import Optional

import httpx

from src.config import GITHUB_TOKEN
from src.ports.outbound import CodeRepository

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
REPO = "dotnet/eShop"
REQUEST_TIMEOUT = 15.0
MAX_FILE_SIZE = 100_000  # truncate files larger than ~100KB to protect LLM context window


class GitHubClient(CodeRepository):
    def __init__(self, token: Optional[str] = None) -> None:
        self._token = token if token is not None else GITHUB_TOKEN
        headers: dict[str, str] = {
            "Accept": "application/vnd.github.v3.text-match+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API_BASE,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def search_code(self, query: str) -> list[dict]:
        try:
            resp = await self._client.get(
                "/search/code",
                params={"q": f"{query} repo:{REPO}"},
            )
            if resp.status_code == 401:
                logger.error("GitHub API authentication failed (401) — GITHUB_TOKEN is missing or invalid")
                return [{"error": "GITHUB_AUTH_FAILED: Token is missing or invalid. Code search is unavailable."}]
            if resp.status_code in (403, 429):
                logger.warning("GitHub API rate limit reached (status %s)", resp.status_code)
                return [{"error": "GitHub API rate limit reached. Try a different query or wait."}]
            resp.raise_for_status()
        except httpx.TimeoutException:
            logger.warning("GitHub API timeout during search_code")
            return [{"error": "GitHub API timeout. Proceeding with available information."}]
        except httpx.HTTPStatusError as exc:
            logger.warning("GitHub API error during search_code: %s", exc)
            return [{"error": f"GitHub API error: {exc.response.status_code}"}]

        data = resp.json()
        results: list[dict] = []
        for item in data.get("items", []):
            snippets = []
            for tm in item.get("text_matches", []):
                snippets.append(tm.get("fragment", ""))
            results.append({
                "path": item.get("path", ""),
                "name": item.get("name", ""),
                "html_url": item.get("html_url", ""),
                "score": item.get("score", 0),
                "snippets": snippets,
            })
        return results

    async def get_file_content(self, path: str) -> str:
        try:
            resp = await self._client.get(f"/repos/{REPO}/contents/{path}")
            if resp.status_code == 401:
                logger.error("GitHub API authentication failed (401) — GITHUB_TOKEN is missing or invalid")
                return "GITHUB_AUTH_FAILED: Token is missing or invalid. File reading is unavailable."
            if resp.status_code == 404:
                return f"File not found: {path}"
            if resp.status_code in (403, 429):
                logger.warning("GitHub API rate limit reached (status %s)", resp.status_code)
                return "GitHub API rate limit reached. Try a different query or wait."
            resp.raise_for_status()
        except httpx.TimeoutException:
            logger.warning("GitHub API timeout during get_file_content")
            return "GitHub API timeout. Proceeding with available information."
        except httpx.HTTPStatusError as exc:
            logger.warning("GitHub API error during get_file_content: %s", exc)
            return f"GitHub API error: {exc.response.status_code}"

        data = resp.json()
        encoding = data.get("encoding", "")
        content = data.get("content", "")

        if not content and data.get("download_url"):
            return f"File too large for GitHub Contents API: {path}. Use the file path to search for specific symbols instead."

        if encoding == "base64":
            decoded = base64.b64decode(content).decode("utf-8")
            if len(decoded) > MAX_FILE_SIZE:
                return decoded[:MAX_FILE_SIZE] + f"\n\n... [truncated — file is {len(decoded):,} chars, showing first {MAX_FILE_SIZE:,}]"
            return decoded
        return content
