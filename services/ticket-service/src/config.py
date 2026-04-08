import os


LINEAR_API_KEY: str = os.environ.get("LINEAR_API_KEY", "")
LINEAR_TEAM_ID: str = os.environ.get("LINEAR_TEAM_ID", "")
LINEAR_WEBHOOK_SECRET: str = os.environ.get("LINEAR_WEBHOOK_SECRET", "")
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://redis:6379")
