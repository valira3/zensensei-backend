"""
ZenSensei Integration Service - Application Entry Point

FastAPI application that manages OAuth flows, data sync with external services,
and webhook handling for all 67 registered integrations.

Run locally:
    uvicorn integration_service.main:app --reload --port 8004

Environment:
    See shared/config.py for all configurable environment variables.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from shared.config import get_config
from shared.middleware.cors import add_cors_middleware
from shared.middleware.error_handler import add_error_handler
from shared.middleware.logging import LoggingMiddleware

from integration_service.integrations import registry
from integration_service.routers.integrations import router as integrations_router
from integration_service.routers.webhooks import router as webhooks_router
from integration_service.services.oauth_service import get_oauth_service
from integration_service.services.sync_engine import get_sync_engine

logger = structlog.get_logger(__name__)
_cfg = get_config()


# ─── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Application lifespan manager.

    Startup:  Connect to Firestore, Pub/Sub, validate the integration registry.
    Shutdown: Gracefully close all connections.
    """
    logger.info(
        "integration_service.startup",
        environment=_cfg.environment,
        port=_cfg.integration_service_port,
        total_integrations=registry.total_count(),
    )

    # ── Startup ───────────────────────────────────────────────────────────────
    oauth_svc = get_oauth_service()
    sync_engine = get_sync_engine()

    try:
        await oauth_svc.connect()
        logger.info("OAuth service connected (Firestore)")
    except Exception as exc:
        logger.warning(
            "OAuth service startup warning (non-fatal in dev)",
            error=str(exc),
        )

    try:
        await sync_engine.connect()
        logger.info("Sync engine connected (Pub/Sub)")
    except Exception as exc:
        logger.warning(
            "Sync engine startup warning (non-fatal in dev)",
            error=str(exc),
        )

    # Log registry summary
    by_cat = {cat.value: len(registry.get_by_category(cat)) for cat in registry.get_categories()}
    logger.info("Integration registry loaded", by_category=by_cat)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("integration_service.shutdown: closing connections")
    try:
        await oauth_svc.close()
        await sync_engine.close()
    except Exception as exc:
        logger.warning("Shutdown error (non-fatal)", error=str(exc))

    logger.info("integration_service.shutdown: complete")


# ─── Application factory ──────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="ZenSensei Integration Service",
        description=(
            "Manages OAuth flows, data sync, and webhook handling for 67 external service "
            "integrations across 9 categories. Transforms third-party data into ZenSensei "
            "knowledge graph nodes."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    # ── Middleware (order matters: outermost first) ────────────────────────────
    add_cors_middleware(app)
    app.add_middleware(LoggingMiddleware, service_name="integration-service")

    # ── Exception handlers ────────────────────────────────────────────────────
    add_error_handler(app)

    # ── Routers ───────────────────────────────────────────────────────────────
    API_PREFIX = f"/api/{_cfg.api_version}"

    app.include_router(integrations_router, prefix=API_PREFIX)
    app.include_router(webhooks_router, prefix=API_PREFIX)

    # ── Health / readiness probes ─────────────────────────────────────────────

    @app.get("/health", tags=["Observability"], include_in_schema=True)
    async def health_check() -> dict:
        """
        Liveness probe.

        Returns 200 as long as the service process is running. Used by
        container orchestrators (Kubernetes, Cloud Run) to detect crashes.
        """
        return {
            "status": "healthy",
            "service": "integration-service",
            "version": app.version,
        }

    @app.get("/ready", tags=["Observability"], include_in_schema=True)
    async def readiness_check() -> dict:
        """
        Readiness probe.

        Verifies that the integration registry is loaded and Firestore is
        reachable. Returns 503 if any dependency is unavailable.
        """
        from fastapi import status as http_status
        from fastapi.responses import ORJSONResponse

        checks: dict[str, bool] = {}

        # Registry check
        checks["registry"] = registry.total_count() == 67

        # Firestore connectivity
        try:
            from shared.database.firestore import get_firestore_client
            fs = get_firestore_client()
            checks["firestore"] = await fs.health_check()
        except Exception:
            checks["firestore"] = False

        all_ready = all(checks.values())
        return ORJSONResponse(
            status_code=http_status.HTTP_200_OK if all_ready else http_status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "ready" if all_ready else "not_ready",
                "service": "integration-service",
                "checks": checks,
                "total_integrations": registry.total_count(),
            },
        )

    @app.get("/", tags=["Observability"], include_in_schema=False)
    async def root() -> dict:
        """Root endpoint returning service metadata."""
        return {
            "service": "ZenSensei Integration Service",
            "version": app.version,
            "docs": "/docs",
            "health": "/health",
            "ready": "/ready",
            "total_integrations": registry.total_count(),
        }

    return app


# ─── Application instance ─────────────────────────────────────────────────────

app = create_app()


# ─── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", _cfg.integration_service_port))
    workers = int(os.environ.get("WORKERS", "1"))

    log_level = "debug" if _cfg.is_development else "info"

    uvicorn.run(
        "integration_service.main:app",
        host="0.0.0.0",
        port=port,
        reload=_cfg.is_development,
        workers=1 if _cfg.is_development else workers,
        log_level=log_level,
        access_log=False,  # Handled by LoggingMiddleware
    )
