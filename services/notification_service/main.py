"""
ZenSensei Notification Service - FastAPI Application Entry Point

Handles push notifications, email delivery, in-app notifications,
and per-user notification preferences.

Port: 8005
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

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

from services.notification_service.routers import notifications, preferences, templates

logger = logging.getLogger(__name__)

_config = get_config()

# ─── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: seed mock data, warm service singletons.  Shutdown: log stop."""
    logger.info("ZenSensei Notification Service starting up…")

    # Seed in-memory mock notifications for demo/development
    if _config.is_development:
        from services.notification_service.services.notification_service import (
            _seed_mock_notifications,
        )
        _seed_mock_notifications()
        logger.info("Notification Service: in-memory mock data seeded")

    # Warm the push and email service singletons so the first request isn't slow
    from services.notification_service.services.push_service import _get_fcm_app
    from services.notification_service.services.email_service import _get_sendgrid_client

    _get_fcm_app()
    _get_sendgrid_client()

    logger.info(
        "ZenSensei Notification Service ready on port %d",
        _config.notification_service_port,
    )

    yield

    logger.info("ZenSensei Notification Service shutting down…")
    logger.info("ZenSensei Notification Service stopped")


# ─── Application factory ──────────────────────────────────────────────────────


def create_app() -> FastAPI:
    app = FastAPI(
        title="ZenSensei Notification Service",
        description=(
            "Handles push notifications, email delivery, in-app notifications, "
            "and per-user notification preferences for ZenSensei."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    # ── Middleware (applied bottom-up) ─────────────────────────────────────
    add_cors_middleware(app)
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=_config.rate_limit_requests_per_minute,
        burst=_config.rate_limit_burst,
        exclude_paths=["/health", "/ready", "/metrics", "/ping"],
    )
    app.add_middleware(LoggingMiddleware, service_name="notification-service")

    # ── Error handlers ─────────────────────────────────────────────────────
    add_error_handler(app)

    # ── Routers ───────────────────────────────────────────────────────────
    api_prefix = f"/api/{_config.api_version}"

    app.include_router(notifications.router, prefix=api_prefix)
    app.include_router(preferences.router, prefix=api_prefix)
    app.include_router(templates.router, prefix=api_prefix)

    # ── Health / readiness ─────────────────────────────────────────────────

    @app.get("/health", tags=["ops"], summary="Liveness probe")
    async def health() -> ORJSONResponse:
        return ORJSONResponse(
            {"status": "ok", "service": "notification-service"}
        )

    @app.get("/ready", tags=["ops"], summary="Readiness probe")
    async def ready() -> ORJSONResponse:
        from services.notification_service.services.push_service import _is_mock_mode as push_mock
        from services.notification_service.services.email_service import _is_mock_mode as email_mock

        push_mode = "mock" if push_mock() else "live"
        email_mode = "mock" if email_mock() else "live"

        return ORJSONResponse(
            {
                "status": "ready",
                "service": "notification-service",
                "checks": {
                    "push": push_mode,
                    "email": email_mode,
                    "in_app": "ok",
                },
            }
        )

    @app.get("/metrics", tags=["ops"], summary="Basic service metrics")
    async def metrics() -> ORJSONResponse:
        from services.notification_service.services.notification_service import (
            _notifications,
            _preferences,
            _device_registry,
        )

        total_notifications = len(_notifications)
        unread = sum(1 for n in _notifications.values() if not n["is_read"])
        users_with_prefs = len(_preferences)
        registered_devices = sum(len(v) for v in _device_registry.values())

        return ORJSONResponse(
            {
                "service": "notification-service",
                "notifications": {
                    "total": total_notifications,
                    "unread": unread,
                },
                "users_with_preferences": users_with_prefs,
                "registered_devices": registered_devices,
            }
        )

    @app.get("/ping", tags=["ops"], summary="Simple ping")
    async def ping() -> ORJSONResponse:
        return ORJSONResponse({"ping": "pong"})

    return app


app = create_app()

# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "services.notification_service.main:app",
        host="0.0.0.0",
        port=_config.notification_service_port,
        reload=_config.is_development,
        log_level="info",
    )
