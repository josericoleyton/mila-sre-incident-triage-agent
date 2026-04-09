import logging
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from src.adapters.inbound.middleware import check_injection, sanitize_text
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
    # --- sanitization (before validation, so stripped text is what gets validated) ---
    title = sanitize_text(title) or ""
    description = sanitize_text(description)

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

    # --- injection detection ---
    prompt_injection_detected = check_injection(
        {"title": title, "description": description, "component": component}, incident_id
    )

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
        "prompt_injection_detected": prompt_injection_detected,
    }

    logger.info(
        "Incident received incident_id=%s component=%s severity=%s has_attachment=%s source_type=userIntegration",
        incident_id, component, severity, attachment_url is not None,
    )

    try:
        pub = await get_publisher()
        event_id = await pub.publish("incidents", "incident.created", payload)
        logger.info("incident.created published incident_id=%s", incident_id, extra={"event_id": event_id})
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

    logger.info(
        "Incident received incident_id=%s component=%s source_type=systemIntegration",
        incident_id, body.get("service_name"),
    )

    try:
        pub = await get_publisher()
        event_id = await pub.publish("incidents", "incident.created", payload)
        logger.info("incident.created (otel) published incident_id=%s", incident_id, extra={"event_id": event_id})
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
    content_type = request.headers.get("content-type", "")

    # Slack sends interaction payloads as application/x-www-form-urlencoded
    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        raw_payload = form.get("payload")
        if not raw_payload:
            return _error_response(400, "Missing payload field", "VALIDATION_ERROR")
        try:
            body = json.loads(raw_payload)
        except (json.JSONDecodeError, TypeError):
            return _error_response(400, "Invalid JSON in payload field", "VALIDATION_ERROR")

        # Extract incident_id from Slack interactive button action
        incident_id = None
        response_url = body.get("response_url")
        actions = body.get("actions", [])
        for act in actions:
            action_id = act.get("action_id", "")
            if action_id.startswith("reescalate_"):
                incident_id = act.get("value")
                break

        if not incident_id:
            return _error_response(400, "No reescalation action found", "VALIDATION_ERROR")

    else:
        # Fallback: plain JSON (for testing / internal calls)
        try:
            body = await request.json()
        except Exception:
            return _error_response(400, "Invalid JSON payload", "VALIDATION_ERROR")
        incident_id = body.get("incident_id")
        response_url = None

    if not incident_id:
        return _error_response(400, "incident_id is required", "VALIDATION_ERROR")

    payload = {
        "incident_id": incident_id,
        "action": "reescalate",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        pub = await get_publisher()
        event_id = await pub.publish("reescalations", "incident.reescalate", payload)
        logger.info("incident.reescalate published event_id=%s incident_id=%s", event_id, incident_id)
    except Exception:
        logger.exception("Failed to publish incident.reescalate event_id=N/A incident_id=%s", incident_id)
        return _error_response(503, "Service temporarily unavailable", "PUBLISH_ERROR")

    # If Slack provided a response_url, update the original message
    if response_url:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(response_url, json={
                    "replace_original": "true",
                    "text": "🔄 Re-escalation in progress...",
                })
        except Exception:
            logger.warning("Failed to update Slack message via response_url for incident=%s", incident_id)

    return {"status": "ok"}
