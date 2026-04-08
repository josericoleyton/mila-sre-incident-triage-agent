import os


REDIS_URL: str = os.environ.get("REDIS_URL", "redis://redis:6379")
SLACK_REPORTER_USER_ID: str = os.environ.get("SLACK_REPORTER_USER_ID", "")
