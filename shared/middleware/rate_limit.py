"""
ZenSensei Shared Middleware - Rate Limiter

Sliding-window rate limiter backed by Redis (ZADD-based sorted set).

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

Redis key pattern: ``zensensei:ratelimit:{client_key}``
  Sorted set — score = request timestamp (float), member = unique request UUID.
  TTL equals the window duration so keys self-expire when idle.

Falls back to an in-process dict when Redis is unavailable, so the
middleware never crashes a request due to a Redis outage.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# ─── In-process fallback store (used when Redis is unavailable) ───────────────
# Maps client_key -> list[request_timestamp_float]
_local_store: dict[str, list[float]] = defaultdict(list)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiting middleware backed by Redis.

    Uses a Redis sorted set (ZADD / ZREMRANGEBYSCORE / ZCARD) for an
    accurate per-client sliding window.  Falls back transparently to an
    in-process list when Redis is unavailable.

    Args:
        app:                  ASGI application.
        requests_per_minute:  Maximum requests allowed in a 60-second window.
        burst:                Additional requests allowed above the base limit
                              (default 0 — no burst headroom).
        window_seconds:       Window size in seconds (default 60).
        key_func:             Callable that extracts a client key from a
                              :class:`Request`.  Defaults to the client IP.
    """

    def __init__(
        self,
        app: ASGIApp,
        requests_per_minute: int = 60,
        burst: int = 0,
        window_seconds: int = 60,
        key_func: Callable[[Request], str] | None = None,
    ) -> None:
        super().__init__(app)
        self._limit = requests_per_minute + burst
        self._window = window_seconds
        self._key_func = key_func or _default_key

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        client_key = self._key_func(request)
        now = time.time()
        window_start = now - self._window

        count, reset_at = await _get_request_count(
            client_key=client_key,
            now=now,
            window_start=window_start,
            window_seconds=self._window,
        )

        remaining = max(0, self._limit - count)
        headers = {
            "X-RateLimit-Limit": str(self._limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(int(reset_at)),
        }

        if count > self._limit:
            retry_after = max(1, int(reset_at - now))
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please slow down.",
                    "retry_after": retry_after,
                },
                headers={**headers, "Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        for key, value in headers.items():
            response.headers[key] = value
        return response


# ─── Redis-backed sliding window ─────────────────────────────────────────────────


async def _get_request_count(
    client_key: str,
    now: float,
    window_start: float,
    window_seconds: int,
) -> tuple[int, float]:
    """
    Record the current request and return ``(count_in_window, reset_timestamp)``.

    Uses Redis ZADD/ZREMRANGEBYSCORE/ZCARD in a pipeline for atomicity.
    Falls back to the in-process store on any Redis error.
    """
    redis_key = f"zensensei:ratelimit:{client_key}"
    reset_at = now + window_seconds

    try:
        from shared.database.redis import get_redis_client
        redis = get_redis_client()
        if redis._client is None:
            await redis.connect()

        raw = redis._client
        member = str(uuid.uuid4())

        pipe = raw.pipeline()
        # Add current request with score = current timestamp
        pipe.zadd(redis_key, {member: now})
        # Remove entries outside the window
        pipe.zremrangebyscore(redis_key, "-inf", window_start)
        # Count remaining entries
        pipe.zcard(redis_key)
        # Reset TTL on the key so it auto-expires after the window
        pipe.expire(redis_key, window_seconds)
        results = await pipe.execute()

        count: int = results[2]  # zcard result
        return count, reset_at

    except Exception as exc:
        logger.warning(
            "Redis rate-limit unavailable, falling back to in-process store: %s", exc
        )
        return _local_rate_limit(client_key, now, window_start, reset_at)


def _local_rate_limit(
    client_key: str,
    now: float,
    window_start: float,
    reset_at: float,
) -> tuple[int, float]:
    """In-process fallback sliding-window counter."""
    timestamps = _local_store[client_key]
    # Prune expired entries
    recent = [ts for ts in timestamps if ts > window_start]
    recent.append(now)
    _local_store[client_key] = recent
    return len(recent), reset_at


def _default_key(request: Request) -> str:
    """Extract the client IP address from the request."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first (leftmost) IP — closest to the actual client
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
