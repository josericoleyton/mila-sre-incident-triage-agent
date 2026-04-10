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
@router.post("/api/incidents", status_code=201)
async def create_incident(
    title: str = Form(default=""),
    description: Optional[str] = Form(None),
    component: Optional[str] = Form(None),
    severity: Optional[str] = Form(None),
    reporter_email: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    title = sanitize_text(title) or ""
    description = sanitize_text(description)
    file_content_type: str | None = None
    file_size: int | None = None

    if file and file.filename:
        file_content_type = file.content_type
        contents = await file.read()
        file_size = len(contents)
        await file.seek(0)

    file_name: str | None = file.filename if file and file.filename else None

    try:
        validate_incident(title, file_content_type, file_size, file_name)
    except ValidationError as exc:
        return _error_response(422, exc.message, "VALIDATION_ERROR")

    incident_id = str(uuid.uuid4())

    prompt_injection_detected = check_injection(
        {"title": title, "description": description, "component": component}, incident_id
    )
    
    attachment_url: str | None = None
    if file and file.filename:
        dest_dir = os.path.join(ATTACHMENTS_DIR, incident_id)
        os.makedirs(dest_dir, exist_ok=True)
        safe_filename = os.path.basename(file.filename)
        dest_path = os.path.join(dest_dir, safe_filename)
        with open(dest_path, "wb") as f:
            if file_size is not None:
                f.write(contents)
            else:
                f.write(await file.read())
        attachment_url = dest_path

    payload = {
        "incident_id": incident_id,
        "title": title.strip(),
        "description": description,
        "component": component,
        "severity": severity,
        "attachment_url": attachment_url,
        "reporter_email": reporter_email or None,
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

@router.post("/api/webhooks/otel", status_code=201)
async def otel_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        return _error_response(400, "Invalid JSON payload", "VALIDATION_ERROR")
    
    if "resourceSpans" in body:
        return await _handle_otlp_traces(body)
    
    return await _handle_simple_otel(body)


async def _handle_simple_otel(body: dict) -> dict | JSONResponse:
    """Handle the simple JSON webhook format (Story 2.2 original)."""
    incident_id = str(uuid.uuid4())

    payload = {
        "incident_id": incident_id,
        "title": body.get("error_message", "OTEL Error"),
        "description": body.get("error_message"),
        "component": body.get("service_name"),
        "severity": None,
        "attachment_url": None,
        "reporter_email": None,
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


async def _handle_otlp_traces(body: dict) -> dict | JSONResponse:
    """Parse OTLP-JSON resourceSpans from the OTEL Collector and create incidents."""
    incidents_created: list[str] = []
    publish_errors: list[str] = []

    for resource_span in body.get("resourceSpans", []):
        if not isinstance(resource_span, dict):
            continue

        service_name = _extract_resource_attr(
            resource_span.get("resource", {}), "service.name"
        )

        for scope_span in resource_span.get("scopeSpans", []):
            if not isinstance(scope_span, dict):
                continue
            for span in scope_span.get("spans", []):
                if not isinstance(span, dict):
                    continue

                status = span.get("status") or {}
                span_name = span.get("name", "OTEL Error")
                error_message = status.get("message") or span_name
                trace_id = span.get("traceId", "")
                status_code = _safe_int(_extract_span_attr(span, "http.status_code"))
                http_method = _extract_span_attr(span, "http.method") or _extract_span_attr(span, "http.request.method")
                http_url = _extract_span_attr(span, "url.full") or _extract_span_attr(span, "http.url") or _extract_span_attr(span, "url.path")
                timestamp = _nano_to_iso(span.get("startTimeUnixNano"))

                exception = _extract_exception_from_events(span)

                # Build a meaningful title from exception details
                if exception.get("type") and exception.get("message"):
                    title = f"{exception['type']}: {exception['message']}"
                else:
                    title = error_message

                description = _build_otlp_description(
                    span_name, error_message, exception,
                    http_method, http_url, status_code,
                )

                incident_id = str(uuid.uuid4())
                payload = {
                    "incident_id": incident_id,
                    "title": title,
                    "description": description,
                    "component": service_name,
                    "severity": None,
                    "attachment_url": None,
                    "reporter_email": None,
                    "source_type": "systemIntegration",
                    "trace_data": {
                        "trace_id": trace_id,
                        "status_code": status_code,
                        "timestamp": timestamp,
                        "service_name": service_name,
                        "error_message": title,
                    },
                }

                logger.info(
                    "OTLP incident received incident_id=%s component=%s trace_id=%s source_type=systemIntegration",
                    incident_id, service_name, trace_id,
                )

                try:
                    pub = await get_publisher()
                    event_id = await pub.publish("incidents", "incident.created", payload)
                    logger.info("incident.created (otlp) published incident_id=%s", incident_id, extra={"event_id": event_id})
                    incidents_created.append(incident_id)
                except Exception:
                    logger.exception("Failed to publish otlp incident incident_id=%s", incident_id)
                    publish_errors.append(incident_id)

    if publish_errors and not incidents_created:
        return _error_response(503, "Service temporarily unavailable", "PUBLISH_ERROR")

    if not incidents_created and not publish_errors:
        return {"status": "ok", "data": {"message": "No error spans found"}}

    result: dict = {
        "incident_ids": incidents_created,
        "message": f"{len(incidents_created)} incident(s) created from OTLP traces",
    }
    if publish_errors:
        result["failed_count"] = len(publish_errors)

    status = "partial" if publish_errors else "ok"
    return {"status": status, "data": result}


def _extract_resource_attr(resource: dict, key: str) -> str | None:
    for attr in (resource.get("attributes") or []):
        if not isinstance(attr, dict):
            continue
        if attr.get("key") == key:
            val = attr.get("value") or {}
            return val.get("stringValue") or str(val.get("intValue", "")) or None
    return None


def _extract_span_attr(span: dict, key: str) -> str | None:
    for attr in (span.get("attributes") or []):
        if not isinstance(attr, dict):
            continue
        if attr.get("key") == key:
            val = attr.get("value") or {}
            return str(val.get("stringValue") or val.get("intValue", ""))
    return None


def _extract_event_attr(event: dict, key: str) -> str | None:
    """Extract an attribute value from an OTLP span event."""
    for attr in (event.get("attributes") or []):
        if not isinstance(attr, dict):
            continue
        if attr.get("key") == key:
            val = attr.get("value") or {}
            return val.get("stringValue")
    return None


def _extract_exception_from_events(span: dict) -> dict:
    """Extract exception details from span events (e.g. exception.type, message, stacktrace)."""
    for event in (span.get("events") or []):
        if not isinstance(event, dict):
            continue
        if event.get("name") == "exception":
            return {
                "type": _extract_event_attr(event, "exception.type"),
                "message": _extract_event_attr(event, "exception.message"),
                "stacktrace": _extract_event_attr(event, "exception.stacktrace"),
            }
    return {}


def _build_otlp_description(
    span_name: str,
    error_message: str,
    exception: dict,
    http_method: str | None,
    http_url: str | None,
    status_code: int | None,
) -> str:
    """Build a rich description from OTLP span data for the agent to analyze."""
    parts: list[str] = []

    if exception.get("type") and exception.get("message"):
        parts.append(f"Exception: {exception['type']}: {exception['message']}")
    elif error_message and error_message != span_name:
        parts.append(f"Error: {error_message}")

    if http_method or http_url:
        endpoint = f"{http_method or ''} {http_url or span_name}".strip()
        parts.append(f"Endpoint: {endpoint}")

    if status_code:
        parts.append(f"HTTP Status: {status_code}")

    if exception.get("stacktrace"):
        stacktrace = exception["stacktrace"][:4000]
        parts.append(f"Stack Trace:\n{stacktrace}")

    return "\n\n".join(parts) if parts else error_message


def _safe_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _nano_to_iso(nano_str: str | int | None) -> str | None:
    if nano_str is None:
        return None
    try:
        ts = int(nano_str) / 1_000_000_000
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return None
    

@router.post("/api/webhooks/slack")
async def slack_webhook(request: Request):
    content_type = request.headers.get("content-type", "")
    
    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        raw_payload = form.get("payload")
        if not raw_payload:
            return _error_response(400, "Missing payload field", "VALIDATION_ERROR")
        try:
            body = json.loads(raw_payload)
        except (json.JSONDecodeError, TypeError):
            return _error_response(400, "Invalid JSON in payload field", "VALIDATION_ERROR")
        
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
