"""
ZenSensei Shared Database - Redis Client

Async Redis client wrapping the ``redis.asyncio`` interface.
Provides get/set/delete helpers, pattern-based invalidation,
and JSON convenience methods.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from shared.config import ZenSenseiConfig, get_config

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Async Redis client with connection pooling.

    Usage::

        client = RedisClient()
        await client.connect()

        await client.set("my-key", {"hello": "world"}, ttl=300)
        value = await client.get("my-key")  # -> {"hello": "world"}
        await client.delete("my-key")

        await client.close()
    """

    def __init__(self, config: ZenSenseiConfig | None = None) -> None:
        self._config = config or get_config()
        self._pool: ConnectionPool | None = None
        self._client: Redis | None = None  # type: ignore[type-arg]

    async def connect(self) -> None:
        """Initialise the connection pool. Call once on service startup."""
        if self._client is not None:
            return

        self._pool = ConnectionPool.from_url(
            self._config.redis_url,
            max_connections=self._config.redis_max_connections,
            socket_timeout=self._config.redis_socket_timeout,
            decode_responses=True,
        )
        self._client = Redis(connection_pool=self._pool)
        logger.info("Redis client initialised", extra={"url": self._config.redis_url})

    async def close(self) -> None:
        """Close the connection pool. Call on service shutdown."""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._pool:
            await self._pool.aclose()
            self._pool = None
        logger.info("Redis client closed")

    def _assert_connected(self) -> Redis:  # type: ignore[type-arg]
        if self._client is None:
            raise RuntimeError("RedisClient.connect() must be called first")
        return self._client

    # ─── Core operations ─────────────────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type(RedisError),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def get(self, key: str) -> Any | None:
        """
        Retrieve a value by key.

        Values are automatically JSON-deserialized if they are valid JSON;
        otherwise the raw string is returned.

        Returns:
            Deserialized value or ``None`` if the key does not exist.
        """
        client = self._assert_connected()
        raw: str | None = await client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    @retry(
        retry=retry_if_exception_type(RedisError),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """
        Store a value under *key*.

        Complex objects are JSON-serialised automatically.

        Args:
            key: Cache key.
            value: Value to store (will be JSON-encoded if not a plain string).
            ttl: Expiry in seconds; ``None`` means no expiry.

        Returns:
            ``True`` on success.
        """
        client = self._assert_connected()
        serialized: str = value if isinstance(value, str) else json.dumps(value)
        result = await client.set(key, serialized, ex=ttl)
        return bool(result)

    @retry(
        retry=retry_if_exception_type(RedisError),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def delete(self, key: str) -> int:
        """
        Delete a key.

        Returns:
            Number of keys removed (0 or 1).
        """
        client = self._assert_connected()
        return await client.delete(key)

    async def exists(self, key: str) -> bool:
        """Return ``True`` if *key* exists in Redis."""
        client = self._assert_connected()
        return bool(await client.exists(key))

    async def expire(self, key: str, ttl: int) -> bool:
        """Set a TTL (seconds) on an existing key. Returns ``True`` if set."""
        client = self._assert_connected()
        return bool(await client.expire(key, ttl))

    # ─── Pattern-based invalidation ─────────────────────────────────────────────

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching *pattern* (supports ``*`` and ``?`` wildcards).

        Uses ``SCAN`` to iterate safely without blocking Redis.

        Args:
            pattern: Key pattern, e.g. ``"user:123:*"``.

        Returns:
            Total number of keys deleted.
        """
        client = self._assert_connected()
        deleted = 0
        async for key in client.scan_iter(match=pattern, count=100):
            deleted += await client.delete(key)
        logger.debug("Invalidated %d keys matching '%s'", deleted, pattern)
        return deleted

    # ─── Health check ────────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Ping Redis and return ``True`` if reachable."""
        try:
            client = self._assert_connected()
            return await client.ping()
        except Exception as exc:
            logger.warning("Redis health check failed: %s", exc)
            return False


# ─── Module-level singleton ────────────────────────────────────────────────────────────

_redis_client: RedisClient | None = None


def get_redis_client() -> RedisClient:
    """Return the module-level Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client
