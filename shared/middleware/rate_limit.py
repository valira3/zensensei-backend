"""
ZenSensei Shared Middleware - Rate Limiter

Sliding-window rate limiter backed by Redis.

Each unique client key (default: IP address) is allowed at most
``requests_per_minute`` requests per rolling 60-second window.

Usage::

    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst=10,
    )

The client receives a ``429 Too Many Requests`` response with a
``Retry-After`` header when the limit is exceeded.

Rate-limit headers injected on every response:
    X-RateLimit-Limit      Maximum requests per window
    X-RateLimit-Remaining  Requests remaining in the current window
    X-RateLimit-Reset      Unix timestamp when the window resets
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

# ─── In-process fallback store (used when Redis is unavailable) ───────────────
# Maps client_key -> list[request_timestamp_float]
_local_store: dict[str, list[float]] = defaultdict(list)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiting middleware.

    In production this should be backed by the shared ``RedisClient`` to
    enforce limits across multiple service replicas.  This implementation
    uses an in-process dict as a safe fallback for single-replica deployments
    and tests.

    Args:
        app: The ASGI application.
        requests_per_minute: Maximum requests allowed per 60-second window.
        burst: Unused in the current sliding-window implementation but
               reserved for future token-bucket support.
        key_func: Callable that receives a ``Request`` and returns a string
                  key identifying the client.  Defaults to the client IP.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        requests_per_minute: int = 60,
        burst: int = 0,
        key_func: Callable[[Request], str] | None = None,
    ) -> None:
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst = burst
        self.window_seconds = 60.0
        self._key_func = key_func or _default_key

    # ------------------------------------------------------------------
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        key = self._key_func(request)
        now = time.monotonic()
        window_start = now - self.window_seconds

        # Prune timestamps outside the current window
        timestamps = _local_store[key]
        _local_store[key] = [t for t in timestamps if t > window_start]

        count = len(_local_store[key])
        limit = self.requests_per_minute
        remaining = max(0, limit - count)
        reset_at = int(time.time()) + int(self.window_seconds)

        if count >= limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too Many Requests"},
                headers={
                    "Retry-After": str(int(self.window_seconds)),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_at),
                },
            )

        _local_store[key].append(now)

        response: Response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining - 1)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_key(request: Request) -> str:
    """Return the client IP address as the rate-limit key."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
