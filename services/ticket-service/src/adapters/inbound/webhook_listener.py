import hashlib
import hmac
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src import config

logger = logging.getLogger(__name__)


def verify_linear_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def create_app() -> FastAPI:
    app = FastAPI(title="ticket-service-webhooks", docs_url=None, redoc_url=None)

    @app.post("/webhooks/linear")
    async def handle_linear_webhook(request: Request) -> JSONResponse:
        body = await request.body()
        signature = request.headers.get("X-Linear-Signature", "")

        if not signature or not verify_linear_signature(body, signature, config.LINEAR_WEBHOOK_SECRET):
            logger.warning("Invalid Linear webhook signature")
            return JSONResponse(status_code=401, content={"error": "invalid signature"})

        try:
            payload = await request.json()
        except Exception as exc:
            logger.warning("Malformed webhook JSON: %s", exc)
            return JSONResponse(status_code=400, content={"error": "invalid JSON"})

        if not isinstance(payload, dict):
            logger.warning("Unexpected webhook payload type: %s", type(payload).__name__)
            return JSONResponse(status_code=400, content={"error": "expected JSON object"})

        action = payload.get("action", "unknown")
        webhook_type = payload.get("type", "unknown")
        identifier = payload.get("id", "no-id")
        logger.info("Linear webhook received: type=%s action=%s id=%s", webhook_type, action, identifier)

        # Stub: actual webhook event handlers are added in Story 4.3
        return JSONResponse(status_code=200, content={"status": "ok"})

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "ticket-service"}

    return app
