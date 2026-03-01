#!/usr/bin/env python3
"""
ZenSensei Health Check Script

Checks that all 6 microservices and the API Gateway are reachable and healthy.
Exits 0 if all services pass, 1 if any service is unhealthy/unreachable.

Usage:
    python scripts/health_check.py [--gateway http://localhost:4000] [--verbose]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("health_check")


@dataclass
class Service:
    name: str
    url: str
    health_path: str = "/health"
    timeout: float = 5.0
    required: bool = True


SERVICES: list[Service] = [
    Service(name="api-gateway", url=os.getenv("GATEWAY_URL", "http://localhost:4000")),
    Service(name="user-service", url=os.getenv("USER_SERVICE_URL", "http://localhost:8001")),
    Service(name="graph-query-service", url=os.getenv("GRAPH_QUERY_SERVICE_URL", "http://localhost:8002")),
    Service(name="ai-reasoning-service", url=os.getenv("AI_REASONING_SERVICE_URL", "http://localhost:8003")),
    Service(name="integration-service", url=os.getenv("INTEGRATION_SERVICE_URL", "http://localhost:8004")),
    Service(name="notification-service", url=os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8005")),
    Service(name="analytics-service", url=os.getenv("ANALYTICS_SERVICE_URL", "http://localhost:8006")),
]


@dataclass
class CheckResult:
    service_name: str
    url: str
    status: str
    http_status: int | None
    latency_ms: float
    detail: str
    body: dict | None = None


def check_service(client: httpx.Client, service: Service) -> CheckResult:
    url = service.url.rstrip("/") + service.health_path
    start = time.monotonic()
    try:
        resp = client.get(url, timeout=service.timeout)
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        try:
            body: dict | None = resp.json()
        except Exception:
            body = None
        if resp.status_code == 200:
            reported_status = (body or {}).get("status", "ok")
            status = "healthy" if reported_status in ("ok", "healthy") else "degraded"
            detail = reported_status
        else:
            status = "degraded" if resp.status_code < 500 else "unhealthy"
            detail = f"HTTP {resp.status_code}"
        return CheckResult(
            service_name=service.name,
            url=url,
            status=status,
            http_status=resp.status_code,
            latency_ms=latency_ms,
            detail=detail,
            body=body,
        )
    except httpx.ConnectError:
        return CheckResult(
            service_name=service.name, url=url, status="unhealthy",
            http_status=None, latency_ms=0, detail="Connection refused",
        )
    except httpx.TimeoutException:
        return CheckResult(
            service_name=service.name, url=url, status="unhealthy",
            http_status=None, latency_ms=service.timeout * 1000, detail="Timeout",
        )
    except Exception as exc:
        return CheckResult(
            service_name=service.name, url=url, status="error",
            http_status=None, latency_ms=0, detail=str(exc),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="ZenSensei service health checker")
    parser.add_argument("--gateway", default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.gateway:
        SERVICES[0].url = args.gateway

    results: list[CheckResult] = []
    with httpx.Client(follow_redirects=True) as client:
        for service in SERVICES:
            result = check_service(client, service)
            results.append(result)
            print(f"{result.status:10} {result.service_name:30} {result.latency_ms}ms {result.detail}")

    unhealthy = [r for r in results if r.status in ("unhealthy", "error")]
    if unhealthy:
        log.error("Unhealthy services: %s", ", ".join(r.service_name for r in unhealthy))
        sys.exit(1)
    log.info("All services healthy!")
    sys.exit(0)


if __name__ == "__main__":
    main()
