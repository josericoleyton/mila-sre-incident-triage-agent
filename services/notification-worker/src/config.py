import os


SLACK_WEBHOOK_URL: str = os.environ.get("SLACK_WEBHOOK_URL", "")
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://redis:6379")
