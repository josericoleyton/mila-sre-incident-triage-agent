import logging

from pydantic_ai import RunContext

from src.domain.models import TriageDeps

logger = logging.getLogger(__name__)


async def search_code(ctx: RunContext[TriageDeps], query: str) -> str:
    """Search the eShop GitHub repository for code matching the query.

    Use this to find source files relevant to the incident being triaged.
    You can refine your search by calling this tool multiple times with different queries.
    If you get an authentication error, STOP searching — do not retry.
    """
    logger.info("search_code called with query: %s", query)
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

    lines: list[str] = []
    for r in results[:10]:
        line = f"- **{r['path']}** (score: {r.get('score', 0)})"
        for snippet in r.get("snippets", [])[:2]:
            line += f"\n  ```\n  {snippet}\n  ```"
        lines.append(line)

    return f"Found {len(results)} results (showing top {min(len(results), 10)}):\n\n" + "\n".join(lines)
