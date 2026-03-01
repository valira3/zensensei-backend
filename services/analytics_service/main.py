"""
ZenSensei Analytics Service - FastAPI Application Entry Point

Handles user behavior tracking, pattern detection, aggregate statistics,
and reporting. Runs on port 8006.

Registers all shared middleware, mounts routers, and exposes /health and
/ready probes.
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

from services.analytics_service.routers import events, metrics, patterns, reports

logger = structlog.get_logger(__name__)
cfg = get_config()

_START_TIME: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _START_TIME
    _START_TIME = time.time()
    logger.info(
        "analytics_service_starting",
        environment=cfg.environment,
        port=cfg.analytics_service_port,
    )
    yield
    logger.info("analytics_service_stopping")


def create_app() -> FastAPI:
    app = FastAPI(
        title="ZenSensei Analytics Service",
        description=(
            "User behavior tracking, pattern detection, aggregate statistics, "
            "and reporting."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    add_cors_middleware(app, config=cfg)
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=cfg.rate_limit_requests_per_minute,
        burst=cfg.rate_limit_burst,
        exclude_paths=["/health", "/ready"],
    )
    app.add_middleware(LoggingMiddleware, service_name="analytics-service")
    add_error_handler(app, config=cfg)

    app.include_router(events.router, prefix="/analytics/events", tags=["Events"])
    app.include_router(metrics.router, prefix="/analytics/metrics", tags=["Metrics"])
    app.include_router(reports.router, prefix="/analytics/reports", tags=["Reports"])
    app.include_router(patterns.router, prefix="/analytics/patterns", tags=["Patterns"])

    @app.get("/health", tags=["System"], summary="Liveness probe", response_model=dict)
    async def health() -> dict:
        return {"status": "ok", "service": "analytics-service"}

    @app.get("/ready", tags=["System"], summary="Readiness probe", response_model=dict)
    async def ready() -> dict:
        uptime_seconds = round(time.time() - _START_TIME, 2) if _START_TIME else 0
        return {
            "status": "ready",
            "service": "analytics-service",
            "uptime_seconds": uptime_seconds,
            "environment": cfg.environment,
        }

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "services.analytics_service.main:app",
        host="0.0.0.0",
        port=cfg.analytics_service_port,
        reload=cfg.is_development,
        log_level="info",
    )
