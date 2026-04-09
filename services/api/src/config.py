import os


REDIS_URL: str = os.environ.get("REDIS_URL", "redis://redis:6379")
