import os


SLACK_BOT_TOKEN: str = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_ID: str = os.environ.get("SLACK_CHANNEL_ID", "")
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://redis:6379")
