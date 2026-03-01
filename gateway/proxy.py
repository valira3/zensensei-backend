"""
ZenSensei API Gateway - HTTP Proxy Logic

ProxyRouter forwards inbound FastAPI requests to the appropriate
upstream microservice using an httpx.AsyncClient connection pool.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
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

CIRCUIT_OPEN_THRESHOLD = 5
CIRCUIT_RECOVERY_SECONDS = 30


@dataclass
class _CircuitState:
    failures: int = 0
    opened_at: float = 0.0
    is_open: bool = False


class ProxyRouter:
    """Manages a shared httpx.AsyncClient and handles all upstream proxying."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._circuits: dict[str, _CircuitState] = defaultdict(_CircuitState)

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
            follow_redirects=True,
        )

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()

    def _is_circuit_open(self, service_name: str) -> bool:
        state = self._circuits[service_name]
        if not state.is_open:
            return False
        elapsed = time.monotonic() - state.opened_at
        if elapsed >= CIRCUIT_RECOVERY_SECONDS:
            state.is_open = False
            state.failures = 0
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

    async def forward(self, request: Request, route: ServiceRoute) -> Response:
        if self._client is None:
            raise RuntimeError("ProxyRouter.start() was not called")

        if self._is_circuit_open(route.name):
            return Response(
                content=f'{{"detail":"Service {route.name} is temporarily unavailable"}}',
                status_code=503,
                media_type="application/json",
            )

        upstream_url = route.base_url.rstrip("/") + str(request.url.path)
        if request.url.query:
            upstream_url += f"?{request.url.query}"

        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        client_ip = request.headers.get("X-Forwarded-For") or (
            request.client.host if request.client else "unknown"
        )

        forwarded_headers = dict(request.headers)
        for hop in ("host", "content-length", "transfer-encoding", "connection"):
            forwarded_headers.pop(hop, None)
        forwarded_headers.update({
            "X-Request-ID": request_id,
            "X-Forwarded-For": client_ip,
            "X-Gateway-Version": "1.0.0",
        })

        body = await request.body()
        upstream_request = self._client.build_request(
            method=request.method,
            url=upstream_url,
            headers=forwarded_headers,
            content=body,
        )

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=0.3, min=0.3, max=3),
                retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout)),
                reraise=True,
            ):
                with attempt:
                    upstream_response = await self._client.send(
                        upstream_request, stream=True, timeout=route.timeout_seconds
                    )
            self._record_success(route.name)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            self._record_failure(route.name)
            return Response(
                content=f'{{"detail":"Could not connect to {route.name}"}}',
                status_code=502,
                media_type="application/json",
            )

        response_headers = {
            k: v for k, v in upstream_response.headers.items()
            if k.lower() not in ("transfer-encoding", "connection", "content-length")
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
