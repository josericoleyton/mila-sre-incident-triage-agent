import logging

from pydantic_ai import RunContext

from src.domain.models import TriageDeps

logger = logging.getLogger(__name__)


def _add_line_numbers(content: str) -> str:
    """Add line numbers to file content for precise reference."""
    lines = content.split("\n")
    width = len(str(len(lines)))
    return "\n".join(f"{i + 1:>{width}}| {line}" for i, line in enumerate(lines))


async def read_file(ctx: RunContext[TriageDeps], file_path: str, repo: str | None = None) -> str:
    """Read the full content of a file from a configured GitHub repository.

    Use this to inspect the source of a relevant file.
    Provide the path relative to the repository root (e.g. 'src/Catalog.API/Apis/CatalogApi.cs').
    Optionally pass the repo from the search result to target the correct repository.
    Output includes line numbers for precise reference in your analysis.
    For large files, consider using read_file_section to read specific line ranges.
    """
    logger.info("read_file called with path: %s", file_path)
    content = await ctx.deps.github_client.get_file_content(file_path, repo=repo)
    if content.startswith(("File not found:", "GITHUB_AUTH_FAILED", "GitHub API")):
        return content
    return f"File: {file_path}\n{'=' * 60}\n{_add_line_numbers(content)}"


async def read_file_section(ctx: RunContext[TriageDeps], file_path: str, start_line: int, end_line: int, repo: str | None = None) -> str:
    """Read a specific line range from a file in a GitHub repository.

    Use this to read only the relevant portion of a large file.
    - file_path: path relative to repo root (e.g. 'src/Catalog.API/Apis/CatalogApi.cs')
    - start_line: first line to read (1-based, inclusive)
    - end_line: last line to read (1-based, inclusive)
    - repo: optional repo identifier from search results
    Output includes line numbers matching the original file.
    """
    logger.info("read_file_section called with path: %s, lines %d-%d", file_path, start_line, end_line)
    content = await ctx.deps.github_client.get_file_content(file_path, repo=repo)
    if content.startswith(("File not found:", "GITHUB_AUTH_FAILED", "GitHub API")):
        return content

    lines = content.split("\n")
    total = len(lines)
    start = max(1, start_line)
    end = min(total, end_line)

    if start > total:
        return f"File {file_path} has only {total} lines; requested start_line={start_line} is out of range."

    selected = lines[start - 1:end]
    width = len(str(end))
    numbered = "\n".join(f"{start + i:>{width}}| {line}" for i, line in enumerate(selected))
    return f"File: {file_path} (lines {start}-{end} of {total})\n{'=' * 60}\n{numbered}"
