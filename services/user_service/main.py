"""
ZenSensei User Service - Application Entry Point

FastAPI application factory with:
  - All routers mounted
  - CORS, structured logging, rate limiting, and error handler middleware
  - Health check endpoints (/health, /ready)
  - Startup / shutdown lifecycle hooks for DB connections
"""

from __future__ import annotations

import sys
import os

# Ensure the monorepo root is on the path so both `shared` and
# `services.user_service` are importable when running standalone.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SERVICES_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

for _p in (_REPO_ROOT, _SERVICES_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from shared.middleware import (
    LoggingMiddleware,
    RateLimitMiddleware,
    add_cors_middleware,
    add_error_handler,
)

from services.user_service.config import UserServiceConfig, get_user_service_config
from services.user_service.routers.auth import router as auth_router
from services.user_service.routers.onboarding import router as onboarding_router
from services.user_service.routers.users import router as users_router

# ─── Structlog bootstrap ──────────────────────────────────────────────────────
# Re-configure structlog to include service-level context
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger("user_service")

# ─── Database lifecycle helpers ───────────────────────────────────────────────


async def _connect_databases(cfg: UserServiceConfig) -> None:
    """Attempt to connect to Firestore and Neo4j; log warnings on failure."""
    # Firestore
    try:
        from shared.database.firestore import get_firestore_client
        firestore_client = get_firestore_client()
        await firestore_client.connect()
        logger.info("Firestore connected")
    except Exception as exc:
        logger.warning(
            "Firestore connection failed — using in-memory fallback",
            error=str(exc),
        )

    # Neo4j
    try:
        from shared.database.neo4j import get_neo4j_client
        neo4j_client = get_neo4j_client()
        await neo4j_client.connect()
        logger.info("Neo4j connected")
    except Exception as exc:
        logger.warning(
            "Neo4j connection failed — graph features degraded",
            error=str(exc),
        )


async def _disconnect_databases() -> None:
    """Gracefully close database connections on shutdown."""
    try:
        from shared.database.firestore import get_firestore_client
        await get_firestore_client().close()
        logger.info("Firestore disconnected")
    except Exception as exc:
        logger.warning("Error closing Firestore connection", error=str(exc))

    try:
        from shared.database.neo4j import get_neo4j_client
        await get_neo4j_client().close()
        logger.info("Neo4j disconnected")
    except Exception as exc:
        logger.warning("Error closing Neo4j connection", error=str(exc))


# ─── Application factory ──────────────────────────────────────────────────────


def create_app(config: UserServiceConfig | None = None) -> FastAPI:
    """
    Build and return the configured FastAPI application.

    This function is intentionally separated from module-level startup so
    that tests can call ``create_app()`` with custom config overrides.
    """
    cfg = config or get_user_service_config()

    # ── Lifespan ──────────────────────────────────────────────────────────────
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        """Manage DB connections for the application lifespan."""
        logger.info(
            "ZenSensei User Service starting",
            version=cfg.service_version,
            environment=cfg.environment,
        )
        await _connect_databases(cfg)
        yield
        logger.info("ZenSensei User Service shutting down")
        await _disconnect_databases()

    # ── App instantiation ─────────────────────────────────────────────────────
    app = FastAPI(
        title="ZenSensei User Service",
        description=(
            "Handles user registration, authentication, profiles, "
            "preferences, onboarding, and session management."
        ),
        version=cfg.service_version,
        docs_url="/docs" if cfg.is_development else None,
        redoc_url="/redoc" if cfg.is_development else None,
        openapi_url="/openapi.json" if cfg.is_development else None,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    # ── Middleware (order matters: outermost registered last) ─────────────────
    # 1. CORS — must be first so preflight requests are handled before auth
    add_cors_middleware(app, config=cfg)

    # 2. Structured request/response logging
    app.add_middleware(LoggingMiddleware, service_name=cfg.service_name)

    # 3. Rate limiting — exclude health endpoints
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=cfg.rate_limit_requests_per_minute,
        burst=cfg.rate_limit_burst,
        exclude_paths=["/health", "/ready", "/metrics"],
    )

    # 4. Global error handlers
    add_error_handler(app, config=cfg)

    # ── Routers ───────────────────────────────────────────────────────────────
    api_prefix = f"/api/{cfg.api_version}"
    app.include_router(auth_router, prefix=api_prefix)
    app.include_router(users_router, prefix=api_prefix)
    app.include_router(onboarding_router, prefix=api_prefix)

    # ── Health endpoints ──────────────────────────────────────────────────────

    @app.get("/health", tags=["Health"], response_class=ORJSONResponse)
    async def health_check() -> dict[str, Any]:
        """
        Liveness probe — returns 200 as long as the process is running.
        Used by container orchestrators (Kubernetes, Cloud Run) to detect crashes.
        """
        return {
            "status": "healthy",
            "service": cfg.service_name,
            "version": cfg.service_version,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

    @app.get("/ready", tags=["Health"], response_class=ORJSONResponse)
    async def readiness_check() -> dict[str, Any]:
        """
        Readiness probe — checks that downstream dependencies are reachable.
        Returns 200 if the service can handle traffic, 503 otherwise.
        """
        checks: dict[str, str] = {}
        all_healthy = True

        # Firestore
        try:
            from shared.database.firestore import get_firestore_client
            client = get_firestore_client()
            if client._db is not None:
                fs_ok = await client.health_check()
                checks["firestore"] = "ok" if fs_ok else "degraded"
                if not fs_ok:
                    all_healthy = False
            else:
                checks["firestore"] = "in-memory-fallback"
        except Exception as exc:
            checks["firestore"] = f"error: {exc}"
            all_healthy = False

        # Neo4j
        try:
            from shared.database.neo4j import get_neo4j_client
            neo4j = get_neo4j_client()
            if neo4j._driver is not None:
                neo4j_ok = await neo4j.health_check()
                checks["neo4j"] = "ok" if neo4j_ok else "degraded"
                if not neo4j_ok:
                    all_healthy = False
            else:
                checks["neo4j"] = "not-connected"
        except Exception as exc:
            checks["neo4j"] = f"error: {exc}"
            # Neo4j degradation does not block readiness (non-critical path)

        response_status = "ready" if all_healthy else "degraded"
        http_status = 200 if all_healthy else 503

        from fastapi.responses import ORJSONResponse as _ORJSONResponse
        return _ORJSONResponse(
            status_code=http_status,
            content={
                "status": response_status,
                "service": cfg.service_name,
                "version": cfg.service_version,
                "checks": checks,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    return app


# ─── Module-level application instance ───────────────────────────────────────

app = create_app()

# ─── Dev server entrypoint ────────────────────────────────────────────────────

if __name__ == "__main__":
    _cfg = get_user_service_config()
    uvicorn.run(
        "services.user_service.main:app",
        host="0.0.0.0",
        port=_cfg.user_service_port,
        reload=_cfg.is_development,
        log_level="info" if not _cfg.debug else "debug",
        access_log=False,  # Access logging handled by LoggingMiddleware
    )
