"""Runtime loaders for domain context documents."""

from pathlib import Path

_CONTEXT_DIR = Path(__file__).parent


def load_eshop_context() -> str:
    """Load the eShop system context from the bundled markdown document."""
    return (_CONTEXT_DIR / "eshop_context.md").read_text(encoding="utf-8")
