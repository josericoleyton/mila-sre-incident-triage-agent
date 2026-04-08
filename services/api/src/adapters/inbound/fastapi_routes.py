import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from src.adapters.outbound.redis_publisher import RedisPublisher
from src.config import SLACK_REPORTER_USER_ID
from src.domain.services import ValidationError, validate_incident

logger = logging.getLogger(__name__)

router = APIRouter()

ATTACHMENTS_DIR = "/shared/attachments"

publisher: RedisPublisher | None = None


async def get_publisher() -> RedisPublisher:
    global publisher
    if publisher is None:
        publisher = RedisPublisher()
    return publisher


async def close_publisher() -> None:
    global publisher
    if publisher is not None:
        await publisher.close()
        publisher = None


def _error_response(status_code: int, message: str, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "message": message, "code": code},
    )


# --------------------------------------------------------------------------
# POST /api/incidents  — user-submitted incident
# --------------------------------------------------------------------------
@router.post("/api/incidents", status_code=201)
async def create_incident(
    title: str = Form(default=""),
    description: Optional[str] = Form(None),
    component: Optional[str] = Form(None),
    severity: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    # --- validation ---
    file_content_type: str | None = None
    file_size: int | None = None

    if file and file.filename:
        file_content_type = file.content_type
        contents = await file.read()
        file_size = len(contents)
        await file.seek(0)  # reset for later save

    try:
        validate_incident(title, file_content_type, file_size)
    except ValidationError as exc:
        return _error_response(422, exc.message, "VALIDATION_ERROR")

    incident_id = str(uuid.uuid4())

    # --- file storage ---
    attachment_url: str | None = None
    if file and file.filename:
        dest_dir = os.path.join(ATTACHMENTS_DIR, incident_id)
        os.makedirs(dest_dir, exist_ok=True)
        safe_filename = os.path.basename(file.filename)
        dest_path = os.path.join(dest_dir, safe_filename)
        with open(dest_path, "wb") as f:
            if file_size is not None:
                f.write(contents)  # already read above
            else:
                f.write(await file.read())
        attachment_url = dest_path

    # --- publish to Redis ---
    payload = {
        "incident_id": incident_id,
        "title": title.strip(),
        "description": description,
        "component": component,
        "severity": severity,
        "attachment_url": attachment_url,
        "reporter_slack_user_id": SLACK_REPORTER_USER_ID or None,
        "source_type": "userIntegration",
    }

    try:
        pub = await get_publisher()
        event_id = await pub.publish("incidents", "incident.created", payload)
        logger.info("incident.created published event_id=%s incident_id=%s", event_id, incident_id)
    except Exception:
        logger.exception("Failed to publish incident.created event_id=N/A incident_id=%s", incident_id)
        return _error_response(503, "Service temporarily unavailable", "PUBLISH_ERROR")

    return {
        "status": "ok",
        "data": {"incident_id": incident_id, "message": "Incident received"},
    }


# --------------------------------------------------------------------------
# POST /api/webhooks/otel  — OTEL collector error webhook
# --------------------------------------------------------------------------
@router.post("/api/webhooks/otel", status_code=201)
async def otel_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        return _error_response(400, "Invalid JSON payload", "VALIDATION_ERROR")

    incident_id = str(uuid.uuid4())

    payload = {
        "incident_id": incident_id,
        "title": body.get("error_message", "OTEL Error"),
        "description": body.get("error_message"),
        "component": body.get("service_name"),
        "severity": None,
        "attachment_url": None,
        "reporter_slack_user_id": None,
        "source_type": "systemIntegration",
        "trace_data": {
            "trace_id": body.get("trace_id"),
            "status_code": body.get("status_code"),
            "timestamp": body.get("timestamp"),
            "service_name": body.get("service_name"),
        },
    }

    try:
        pub = await get_publisher()
        event_id = await pub.publish("incidents", "incident.created", payload)
        logger.info("incident.created (otel) published event_id=%s incident_id=%s", event_id, incident_id)
    except Exception:
        logger.exception("Failed to publish otel incident.created event_id=N/A incident_id=%s", incident_id)
        return _error_response(503, "Service temporarily unavailable", "PUBLISH_ERROR")

    return {
        "status": "ok",
        "data": {"incident_id": incident_id, "message": "Incident received"},
    }


# --------------------------------------------------------------------------
# POST /api/webhooks/slack  — Slack interaction callback (re-escalation)
# --------------------------------------------------------------------------
@router.post("/api/webhooks/slack")
async def slack_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        return _error_response(400, "Invalid JSON payload", "VALIDATION_ERROR")

    incident_id = body.get("incident_id")
    action = body.get("action", "reescalate")

    if not incident_id:
        return _error_response(400, "incident_id is required", "VALIDATION_ERROR")

    payload = {
        "incident_id": incident_id,
        "action": action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        pub = await get_publisher()
        event_id = await pub.publish("reescalations", "incident.reescalate", payload)
        logger.info("incident.reescalate published event_id=%s incident_id=%s", event_id, incident_id)
    except Exception:
        logger.exception("Failed to publish incident.reescalate event_id=N/A incident_id=%s", incident_id)
        return _error_response(503, "Service temporarily unavailable", "PUBLISH_ERROR")

    return {"status": "ok"}
