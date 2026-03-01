"""
ZenSensei AI Reasoning Service - FastAPI Application Entry Point

Runs on port 8003.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

logger = structlog.get_logger(__name__)

_START_TIME: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _START_TIME
    _START_TIME = time.time()
    logger.info("ai_reasoning_service_starting")
    yield
    logger.info("ai_reasoning_service_stopping")


def create_app() -> FastAPI:
    app = FastAPI(
        title="ZenSensei AI Reasoning Service",
        description="AI-powered insight generation and personalised recommendations.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    @app.get("/health", tags=["System"])
    async def health() -> dict:
        return {"status": "ok", "service": "ai-reasoning-service"}

    @app.get("/ready", tags=["System"])
    async def ready() -> dict:
        uptime_seconds = round(time.time() - _START_TIME, 2) if _START_TIME else 0
        return {
            "status": "ready",
            "service": "ai-reasoning-service",
            "uptime_seconds": uptime_seconds,
        }

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "services.ai_reasoning_service.main:app",
        host="0.0.0.0",
        port=8003,
        reload=True,
    )
