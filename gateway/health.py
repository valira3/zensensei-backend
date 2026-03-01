"""
ZenSensei API Gateway - Health Check Aggregator

Polls all six downstream services in parallel and returns a unified
health payload indicating which services are healthy or degraded.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from gateway.routes import ROUTES, ServiceRoute

logger = logging.getLogger("gateway.health")

_PROBE_TIMEOUT = 5.0  # seconds


async def _probe_service(
    client: httpx.AsyncClient,
    route: ServiceRoute,
) -> dict[str, Any]:
    """Probe a single upstream service health endpoint."""
    url = route.base_url.rstrip("/") + route.health_path
    start = time.monotonic()
    try:
        resp = await client.get(url, timeout=_PROBE_TIMEOUT)
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        if resp.status_code == 200:
            try:
                payload = resp.json()
            except Exception:
                payload = {}
            return {
                "name": route.name,
                "status": "healthy",
                "latency_ms": latency_ms,
                "url": url,
                "upstream_status": payload.get("status", "ok"),
            }
        else:
            return {
                "name": route.name,
                "status": "degraded",
                "latency_ms": latency_ms,
                "url": url,
                "http_status": resp.status_code,
                "detail": f"Upstream returned HTTP {resp.status_code}",
            }
    except httpx.ConnectError:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {
            "name": route.name,
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "url": url,
            "detail": "Connection refused",
        }
    except httpx.TimeoutException:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {
            "name": route.name,
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "url": url,
            "detail": "Health probe timed out",
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        logger.error("Health probe failed for %s: %s", route.name, exc)
        return {
            "name": route.name,
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "url": url,
            "detail": str(exc),
        }


async def check_all_services() -> dict[str, Any]:
    """Probe all registered services concurrently."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [_probe_service(client, route) for route in ROUTES]
        results: list[dict[str, Any]] = await asyncio.gather(*tasks)

    services: dict[str, Any] = {r["name"]: r for r in results}

    statuses = [r["status"] for r in results]
    if all(s == "healthy" for s in statuses):
        overall = "healthy"
    elif all(s == "unhealthy" for s in statuses):
        overall = "unhealthy"
    else:
        overall = "degraded"

    return {
        "status": overall,
        "services": services,
        "total": len(results),
        "healthy": statuses.count("healthy"),
        "degraded": statuses.count("degraded"),
        "unhealthy": statuses.count("unhealthy"),
    }
