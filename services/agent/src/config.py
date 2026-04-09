import os


LLM_MODEL: str = os.environ.get("LLM_MODEL", "openrouter:google/gemma-4")
LLM_FALLBACK_MODEL: str = os.environ.get("LLM_FALLBACK_MODEL", "openrouter:google/gemini-2.5-flash")
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://redis:6379")
GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
LANGFUSE_PUBLIC_KEY: str = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY: str = os.environ.get("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST: str = os.environ.get("LANGFUSE_HOST", "http://langfuse:3000")
_raw_threshold = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.75"))
CONFIDENCE_THRESHOLD: float = max(0.0, min(1.0, _raw_threshold))
FAILURE_THRESHOLD: int = int(os.environ.get("FAILURE_THRESHOLD", "2"))
COOLDOWN_SECONDS: int = int(os.environ.get("COOLDOWN_SECONDS", "60"))
