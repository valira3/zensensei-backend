"""
ZenSensei API Gateway - Health Check Aggregator

Polls all downstream services and returns an aggregated health report.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from shared.config import settings

router = APIRouter()

# Map of service name → base URL
_SERVICES: dict[str, str] = {
    "user-service": settings.USER_SERVICE_URL,
    "graph-query-service": settings.GRAPH_QUERY_SERVICE_URL,
    "ai-reasoning-service": settings.AI_REASONING_SERVICE_URL,
    "integration-service": settings.INTEGRATION_SERVICE_URL,
    "notification-service": settings.NOTIFICATION_SERVICE_URL,
    "analytics-service": settings.ANALYTICS_SERVICE_URL,
}


async def _check_service(name: str, base_url: str, client: httpx.AsyncClient) -> dict[str, Any]:
    """Probe a single service's /health endpoint."""
    url = f"{base_url.rstrip('/')}/health"
    start = time.monotonic()
    try:
        resp = await client.get(url, timeout=5.0)
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        if resp.status_code == 200:
            return {"status": "healthy", "latency_ms": latency_ms}
        return {"status": "degraded", "http_status": resp.status_code, "latency_ms": latency_ms}
    except Exception as exc:  # noqa: BLE001
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"status": "unreachable", "error": str(exc), "latency_ms": latency_ms}


@router.get("/health")
async def gateway_health() -> JSONResponse:
    """Liveness probe — returns 200 immediately without hitting downstream services."""
    return JSONResponse(
        status_code=200,
        content={"status": "healthy", "service": "api-gateway"},
    )


@router.get("/ready")
async def gateway_ready() -> JSONResponse:
    """Readiness probe — polls all downstream services in parallel."""
    async with httpx.AsyncClient() as client:
        tasks = [
            _check_service(name, url, client)
            for name, url in _SERVICES.items()
        ]
        results_list = await asyncio.gather(*tasks)

    services: dict[str, Any] = dict(zip(_SERVICES.keys(), results_list))
    all_healthy = all(s["status"] == "healthy" for s in services.values())
    overall = "ready" if all_healthy else "degraded"
    status_code = 200 if all_healthy else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "service": "api-gateway",
            "services": services,
        },
    )
