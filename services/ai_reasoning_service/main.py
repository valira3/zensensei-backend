"""
ZenSensei AI Reasoning Service - FastAPI Application Entry Point

Runs on port 8003. Registers all shared middleware, mounts routers,
and exposes /health and /ready probes.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from shared.config import get_config
from shared.middleware import (
    LoggingMiddleware,
    RateLimitMiddleware,
    add_cors_middleware,
    add_error_handler,
)

from services.ai_reasoning_service.routers import decisions, insights, recommendations

logger = structlog.get_logger(__name__)
cfg = get_config()

_START_TIME: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _START_TIME
    _START_TIME = time.time()
    logger.info("ai_reasoning_service_starting", environment=cfg.environment, port=cfg.ai_reasoning_service_port, gemini_model=cfg.gemini_model)
    yield
    logger.info("ai_reasoning_service_stopping")


def create_app() -> FastAPI:
    app = FastAPI(
        title="ZenSensei AI Reasoning Service",
        description="AI-powered insight generation, multi-factor decision analysis, and personalised recommendations. Powered by Gemini with Claude fallback.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )
    add_cors_middleware(app, config=cfg)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=cfg.rate_limit_requests_per_minute, burst=cfg.rate_limit_burst, exclude_paths=["/health", "/ready", "/metrics"])
    app.add_middleware(LoggingMiddleware, service_name="ai-reasoning-service")
    add_error_handler(app, config=cfg)
    app.include_router(insights.router, prefix="/insights", tags=["Insights"])
    app.include_router(decisions.router, prefix="/decisions", tags=["Decisions"])
    app.include_router(recommendations.router, prefix="/recommendations", tags=["Recommendations"])

    @app.get("/health", tags=["System"], summary="Liveness probe", response_model=dict)
    async def health() -> dict:
        return {"status": "ok", "service": "ai-reasoning-service"}

    @app.get("/ready", tags=["System"], summary="Readiness probe", response_model=dict)
    async def ready() -> dict:
        uptime_seconds = round(time.time() - _START_TIME, 2) if _START_TIME else 0
        return {"status": "ready", "service": "ai-reasoning-service", "uptime_seconds": uptime_seconds, "environment": cfg.environment, "gemini_model": cfg.gemini_model}

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run("services.ai_reasoning_service.main:app", host="0.0.0.0", port=cfg.ai_reasoning_service_port, reload=cfg.is_development, log_level="info")
