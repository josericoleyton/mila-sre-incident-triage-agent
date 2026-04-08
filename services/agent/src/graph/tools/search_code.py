import logging

from pydantic_ai import RunContext

from src.domain.models import TriageDeps

logger = logging.getLogger(__name__)


async def search_code(ctx: RunContext[TriageDeps], query: str) -> str:
    """Search the eShop GitHub repository for code matching the query.

    Use this to find source files relevant to the incident being triaged.
    You can refine your search by calling this tool multiple times with different queries.
    """
    logger.info("search_code called with query: %s", query)
    results = await ctx.deps.github_client.search_code(query)

    if not results:
        return "No results found for the query."

    if len(results) == 1 and "error" in results[0]:
        return results[0]["error"]

    lines: list[str] = []
    for r in results[:10]:
        line = f"- **{r['path']}** (score: {r.get('score', 0)})"
        for snippet in r.get("snippets", [])[:2]:
            line += f"\n  ```\n  {snippet}\n  ```"
        lines.append(line)

    return f"Found {len(results)} results (showing top {min(len(results), 10)}):\n\n" + "\n".join(lines)
