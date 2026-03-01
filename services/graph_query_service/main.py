"""
ZenSensei Graph Query Service - FastAPI Application Entry Point

Handles all Neo4j graph operations: CRUD, traversals, schema management,
and Redis caching.

Port: 8002
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

from services.graph_query_service.routers import nodes, queries, relationships, schema
from services.graph_query_service.services.cache_service import get_cache_service
from services.graph_query_service.services.graph_service import get_graph_service
from services.graph_query_service.services.schema_service import get_schema_service

logger = logging.getLogger(__name__)

_config = get_config()

# ─── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Start up: connect Neo4j + Redis.  Shut down: close both cleanly."""
    logger.info("ZenSensei Graph Query Service starting up…")

    # Connect Neo4j (with in-memory fallback)
    graph_svc = get_graph_service()
    await graph_svc.connect()
    logger.info("GraphService backend: %s", graph_svc.backend)

    # Connect Redis (with no-cache fallback)
    cache_svc = get_cache_service()
    await cache_svc.connect()

    # Wire SchemaService with the live GraphService instance
    schema_svc = get_schema_service()
    schema_svc._graph = graph_svc

    logger.info("ZenSensei Graph Query Service ready on port %d", _config.graph_query_service_port)

    yield

    # Shutdown
    logger.info("ZenSensei Graph Query Service shutting down…")
    await cache_svc.close()
    await graph_svc.close()
    logger.info("ZenSensei Graph Query Service stopped")


# ─── Application ──────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    app = FastAPI(
        title="ZenSensei Graph Query Service",
        description=(
            "Handles all Neo4j graph operations: node/relationship CRUD, "
            "complex traversals, schema management, and Redis caching."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    # ── Middleware (order matters: applied bottom-up) ──────────────────────────
    add_cors_middleware(app)
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=_config.rate_limit_requests_per_minute,
        burst=_config.rate_limit_burst,
        exclude_paths=["/health", "/ready", "/metrics", "/ping"],
    )
    app.add_middleware(LoggingMiddleware, service_name="graph-query-service")

    # ── Error handlers ────────────────────────────────────────────────────────
    add_error_handler(app)

    # ── Routers ───────────────────────────────────────────────────────────────
    api_prefix = f"/api/{_config.api_version}"

    app.include_router(nodes.router, prefix=api_prefix)
    app.include_router(relationships.router, prefix=api_prefix)
    app.include_router(queries.router, prefix=api_prefix)
    app.include_router(schema.router, prefix=api_prefix)

    # ── Health / readiness ────────────────────────────────────────────────────

    @app.get("/health", tags=["ops"], summary="Liveness probe")
    async def health() -> ORJSONResponse:
        return ORJSONResponse({"status": "ok", "service": "graph-query-service"})

    @app.get("/ready", tags=["ops"], summary="Readiness probe")
    async def ready() -> ORJSONResponse:
        graph_svc = get_graph_service()
        cache_svc = get_cache_service()

        neo4j_ok = await graph_svc.health_check()
        redis_ok = await cache_svc.health_check()

        ready_status = neo4j_ok  # service is ready even if Redis is down
        status_code = 200 if ready_status else 503

        return ORJSONResponse(
            status_code=status_code,
            content={
                "status": "ready" if ready_status else "degraded",
                "service": "graph-query-service",
                "backend": graph_svc.backend,
                "checks": {
                    "neo4j": "ok" if neo4j_ok else "unavailable (in-memory fallback active)",
                    "redis": "ok" if redis_ok else "unavailable (no-cache mode active)",
                },
            },
        )

    @app.get("/metrics", tags=["ops"], summary="Basic service metrics")
    async def metrics() -> ORJSONResponse:
        from services.graph_query_service.services.cache_service import get_cache_metrics

        return ORJSONResponse(
            {
                "service": "graph-query-service",
                "cache_metrics": get_cache_metrics(),
            }
        )

    return app


app = create_app()

# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "services.graph_query_service.main:app",
        host="0.0.0.0",
        port=_config.graph_query_service_port,
        reload=_config.is_development,
        log_level="info",
    )
