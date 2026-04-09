import logging

from pydantic_ai import RunContext

from src.domain.models import TriageDeps

logger = logging.getLogger(__name__)

_SKIP_EXTS = frozenset({
    ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp",
    ".ttf", ".woff", ".woff2", ".eot", ".otf",
    ".css", ".min.js", ".map",
})


async def search_code(ctx: RunContext[TriageDeps], query: str) -> str:
    """Search the configured GitHub repositories for code matching the query.

    Use this to find source files relevant to the incident being triaged.
    Results include a 'repo' field indicating which repository each match came from.
    You can refine your search by calling this tool multiple times with different queries,
    but stay within the limit specified in your instructions.
    If you get an authentication error, STOP searching — do not retry.
    """
    logger.info("search_code called query_length=%d", len(query))
    results = await ctx.deps.github_client.search_code(query)

    if not results:
        return "No results found for the query."

    if len(results) == 1 and "error" in results[0]:
        error_msg = results[0]["error"]
        if "GITHUB_AUTH_FAILED" in error_msg:
            return (
                "STOP: GitHub authentication failed. The GITHUB_TOKEN is not configured. "
                "Do NOT retry search_code — it will fail every time. "
                "Proceed to classification using only the incident description and any other available context."
            )
        return error_msg

    code_results = [r for r in results if not any(r.get("path", "").lower().endswith(ext) for ext in _SKIP_EXTS)]
    if not code_results:
        return "No relevant code results found (only non-code files matched). Try a more specific query."

    lines: list[str] = []
    for r in code_results[:10]:
        repo_label = f" [{r['repo']}]" if r.get("repo") else ""
        line = f"- **{r['path']}**{repo_label} (score: {r.get('score', 0)})"
        for snippet in r.get("snippets", [])[:2]:
            line += f"\n  ```\n  {snippet}\n  ```"
        lines.append(line)

    return f"Found {len(code_results)} results (showing top {min(len(code_results), 10)}):\n\n" + "\n".join(lines)
