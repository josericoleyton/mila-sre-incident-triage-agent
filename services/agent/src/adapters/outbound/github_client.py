import base64
import logging
from typing import Optional

import httpx

from src.config import GITHUB_REPOS, GITHUB_TOKEN
from src.ports.outbound import CodeRepository

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
REQUEST_TIMEOUT = 15.0
MAX_FILE_SIZE = 100_000


class GitHubClient(CodeRepository):
    def __init__(self, token: Optional[str] = None, repos: Optional[list[str]] = None) -> None:
        self._token = token if token is not None else GITHUB_TOKEN
        self._repos = repos if repos is not None else GITHUB_REPOS
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
        all_results: list[dict] = []
        for repo in self._repos:
            results = await self._search_code_in_repo(query, repo)
            all_results.extend(results)
        return all_results

    async def _search_code_in_repo(self, query: str, repo: str) -> list[dict]:
        try:
            resp = await self._client.get(
                "/search/code",
                params={"q": f"{query} repo:{repo}"},
            )
            if resp.status_code == 401:
                logger.error("GitHub API authentication failed (401) — GITHUB_TOKEN is missing or invalid")
                return [{"error": "GITHUB_AUTH_FAILED: Token is missing or invalid. Code search is unavailable."}]
            if resp.status_code in (403, 429):
                logger.warning("GitHub API rate limit reached (status %s) for repo %s", resp.status_code, repo)
                return [{"error": f"GitHub API rate limit reached for {repo}. Try a different query or wait."}]
            resp.raise_for_status()
        except httpx.TimeoutException:
            logger.warning("GitHub API timeout during search_code for repo %s", repo)
            return [{"error": f"GitHub API timeout for {repo}. Proceeding with available information."}]
        except httpx.HTTPStatusError as exc:
            logger.warning("GitHub API error during search_code for repo %s: %s", repo, exc)
            return [{"error": f"GitHub API error for {repo}: {exc.response.status_code}"}]

        data = resp.json()
        results: list[dict] = []
        for item in data.get("items", [])[:20]:
            snippets = []
            for tm in item.get("text_matches", []):
                fragment = tm.get("fragment", "")
                snippets.append(fragment[:500])
            results.append({
                "path": item.get("path", ""),
                "name": item.get("name", ""),
                "repo": repo,
                "html_url": item.get("html_url", ""),
                "score": item.get("score", 0),
                "snippets": snippets,
            })
        return results

    async def get_file_content(self, path: str, repo: Optional[str] = None) -> str:
        target_repo = repo or self._repos[0] if self._repos else "dotnet/eShop"
        try:
            resp = await self._client.get(f"/repos/{target_repo}/contents/{path}")
            if resp.status_code == 401:
                logger.error("GitHub API authentication failed (401) — GITHUB_TOKEN is missing or invalid")
                return "GITHUB_AUTH_FAILED: Token is missing or invalid. File reading is unavailable."
            if resp.status_code == 404:
                return f"File not found: {path} in {target_repo}"
            if resp.status_code in (403, 429):
                logger.warning("GitHub API rate limit reached (status %s) for repo %s", resp.status_code, target_repo)
                return f"GitHub API rate limit reached for {target_repo}. Try a different query or wait."
            resp.raise_for_status()
        except httpx.TimeoutException:
            logger.warning("GitHub API timeout during get_file_content for repo %s", target_repo)
            return "GitHub API timeout. Proceeding with available information."
        except httpx.HTTPStatusError as exc:
            logger.warning("GitHub API error during get_file_content for repo %s: %s", target_repo, exc)
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
