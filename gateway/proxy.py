"""
ZenSensei API Gateway - HTTP Proxy Logic

ProxyRouter forwards inbound FastAPI requests to the appropriate
upstream microservice using an httpx.AsyncClient connection pool.

Features
--------
* X-Request-ID and X-Forwarded-For header injection
* Configurable per-route timeouts and retries (tenacity)
* Circuit breaker per upstream service (consecutive failure window)
* Streaming response pass-through
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncGenerator

import httpx
from fastapi import Request
from fastapi.responses import Response, StreamingResponse
from tenacity import (
    AsyncRetrying,
    RetryError,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from gateway.routes import ServiceRoute

logger = logging.getLogger("gateway.proxy")

# ---------------------------------------------------------------------------
# Circuit-Breaker configuration
# ---------------------------------------------------------------------------

CIRCUIT_OPEN_THRESHOLD = 5          # failures before opening the circuit
CIRCUIT_RECOVERY_SECONDS = 30       # seconds before a half-open probe attempt


@dataclass
class _CircuitState:
    failures: int = 0
    opened_at: float = 0.0
    is_open: bool = False


# ---------------------------------------------------------------------------
# ProxyRouter
# ---------------------------------------------------------------------------

class ProxyRouter:
    """
    Manages a single shared :class:`httpx.AsyncClient` and handles all
    upstream proxying logic including header enrichment, retries, and
    circuit breaking.
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._circuits: dict[str, _CircuitState] = defaultdict(_CircuitState)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialise the shared async HTTP client (call on app startup)."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0),
            limits=httpx.Limits(
                max_connections=200,
                max_keepalive_connections=50,
                keepalive_expiry=30,
            ),
            follow_redirects=True,
        )
        logger.info("ProxyRouter HTTP client started")

    async def stop(self) -> None:
        """Gracefully close the shared HTTP client (call on app shutdown)."""
        if self._client:
            await self._client.aclose()
            logger.info("ProxyRouter HTTP client closed")

    # ------------------------------------------------------------------
    # Circuit breaker helpers
    # ------------------------------------------------------------------

    def _is_circuit_open(self, service_name: str) -> bool:
        state = self._circuits[service_name]
        if not state.is_open:
            return False
        elapsed = time.monotonic() - state.opened_at
        if elapsed >= CIRCUIT_RECOVERY_SECONDS:
            # Allow a single probe request (half-open)
            state.is_open = False
            state.failures = 0
            logger.info("Circuit half-open for %s (probing)", service_name)
            return False
        return True

    def _record_success(self, service_name: str) -> None:
        state = self._circuits[service_name]
        state.failures = 0
        state.is_open = False

    def _record_failure(self, service_name: str) -> None:
        state = self._circuits[service_name]
        state.failures += 1
        if state.failures >= CIRCUIT_OPEN_THRESHOLD and not state.is_open:
            state.is_open = True
            state.opened_at = time.monotonic()
            logger.error(
                "Circuit opened for %s after %d consecutive failures",
                service_name,
                state.failures,
            )

    # ------------------------------------------------------------------
    # Public proxy method
    # ------------------------------------------------------------------

    async def proxy(self, request: Request, route: ServiceRoute) -> Response:
        """Forward *request* to the upstream defined by *route*.

        Raises :class:`httpx.HTTPStatusError` for non-2xx upstreams so
        callers can convert to appropriate FastAPI responses.
        """
        if self._client is None:
            raise RuntimeError("ProxyRouter.start() was not called")

        if self._is_circuit_open(route.name):
            logger.warning("Circuit open for %s – rejecting request", route.name)
            return Response(
                content=f'{{"detail":"Service {route.name} is temporarily unavailable"}}',
                status_code=503,
                media_type="application/json",
                headers={"Retry-After": str(CIRCUIT_RECOVERY_SECONDS)},
            )

        # ── Build upstream URL ────────────────────────────────────────────────────────────────────────
        upstream_url = route.base_url.rstrip("/") + str(request.url.path)
        if request.url.query:
            upstream_url += f"?{request.url.query}"

        # ── Enrich headers ────────────────────────────────────────────────────────────────────────
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        client_ip = request.headers.get("X-Forwarded-For") or (
            request.client.host if request.client else "unknown"
        )

        forwarded_headers = dict(request.headers)
        # Strip hop-by-hop headers
        for hop in ("host", "content-length", "transfer-encoding", "connection"):
            forwarded_headers.pop(hop, None)

        forwarded_headers.update(
            {
                "X-Request-ID": request_id,
                "X-Forwarded-For": client_ip,
                "X-Forwarded-Host": request.headers.get("host", ""),
                "X-Gateway-Version": "1.0.0",
            }
        )

        # ── Send with retries ───────────────────────────────────────────────────────────────────────
        body = await request.body()
        upstream_request = self._client.build_request(
            method=request.method,
            url=upstream_url,
            headers=forwarded_headers,
            content=body,
        )

        # Only retry idempotent methods; POST/PUT/DELETE/PATCH must not be
        # retried to prevent duplicate mutations.
        is_retryable_method = request.method.upper() in ("GET", "HEAD")
        max_attempts = 3 if is_retryable_method else 1

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(multiplier=0.3, min=0.3, max=3),
                retry=retry_if_exception_type(
                    (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout)
                ),
                reraise=True,
            ):
                with attempt:
                    upstream_response = await self._client.send(
                        upstream_request,
                        stream=True,
                        timeout=route.timeout_seconds,
                    )

            self._record_success(route.name)

        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            self._record_failure(route.name)
            logger.error(
                "Upstream connection error for %s: %s", route.name, exc
            )
            return Response(
                content=f'{{"detail":"Could not connect to upstream service {route.name}"}}',
                status_code=502,
                media_type="application/json",
            )
        except RetryError as exc:
            self._record_failure(route.name)
            logger.error("All retries exhausted for %s: %s", route.name, exc)
            return Response(
                content=f'{{"detail":"Upstream service {route.name} did not respond after retries"}}',
                status_code=502,
                media_type="application/json",
            )

        # ── Stream response back to client ───────────────────────────────────────────────────
        response_headers = {
            k: v
            for k, v in upstream_response.headers.items()
            if k.lower()
            not in (
                "transfer-encoding",
                "connection",
                "content-encoding",
                "content-length",
            )
        }
        response_headers["X-Request-ID"] = request_id

        async def _stream_body() -> AsyncGenerator[bytes, None]:
            async with upstream_response:
                async for chunk in upstream_response.aiter_bytes():
                    yield chunk

        return StreamingResponse(
            _stream_body(),
            status_code=upstream_response.status_code,
            headers=response_headers,
            media_type=upstream_response.headers.get("content-type", "application/json"),
        )
