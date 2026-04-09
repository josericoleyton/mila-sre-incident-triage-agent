"""Structured JSON logging for the API service.

Produces one JSON object per line to stdout with the required fields:
  timestamp (ISO 8601), level, service, event_id, message

Usage:
    from src.json_logging import setup_logging
    setup_logging()
"""

import json
import logging
from datetime import datetime, timezone


SERVICE_NAME = "api"


class StructuredJsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        entry: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "service": SERVICE_NAME,
            "event_id": getattr(record, "event_id", None) or "",
            "message": message,
        }
        if record.exc_info and record.exc_info[1]:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with structured JSON output."""
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredJsonFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers.clear()
