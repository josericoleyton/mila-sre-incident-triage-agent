import logging

from pydantic_ai import RunContext

from src.domain.models import TriageDeps

logger = logging.getLogger(__name__)


async def read_file(ctx: RunContext[TriageDeps], file_path: str, repo: str | None = None) -> str:
    """Read the full content of a file from a configured GitHub repository.

    Use this after search_code to inspect the source of a relevant file.
    Provide the path relative to the repository root (e.g. 'src/Catalog.API/Program.cs').
    Optionally pass the repo (e.g. 'dotnet/eShop') from the search result to target the correct repository.
    """
    logger.info("read_file called with path: %s", file_path)
    content = await ctx.deps.github_client.get_file_content(file_path, repo=repo)
    return content
