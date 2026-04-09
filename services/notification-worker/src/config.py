import os


SLACK_WEBHOOK_URL: str = os.environ.get("SLACK_WEBHOOK_URL", "")
SLACK_BOT_TOKEN: str = os.environ.get("SLACK_BOT_TOKEN", "")
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://redis:6379")
