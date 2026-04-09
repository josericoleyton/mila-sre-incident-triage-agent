import logging

from fastapi import FastAPI

from src.adapters.inbound.fastapi_routes import close_publisher, router
from src.json_logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Mila API", version="0.1.0")
app.include_router(router)


@app.on_event("startup")
async def startup():
    logger.info("Service api started")


@app.on_event("shutdown")
async def shutdown():
    await close_publisher()
    logger.info("Service api stopped")


@app.get("/health")
async def health():
    return {"status": "ok"}
