import os


LLM_MODEL: str = os.environ.get("LLM_MODEL", "openrouter:google/gemma-4")
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://redis:6379")
GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
LANGFUSE_PUBLIC_KEY: str = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY: str = os.environ.get("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST: str = os.environ.get("LANGFUSE_HOST", "http://langfuse:3000")
CONFIDENCE_THRESHOLD: float = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.7"))
