import logging

from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"api","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mila API", version="0.1.0")


@app.on_event("startup")
async def startup():
    logger.info("Service api started")


@app.get("/health")
async def health():
    return {"status": "ok"}
