"""
ZenSensei Graph Query Service - Cache Service

Redis-backed caching layer with:
- Deterministic key generation from query + params
- TTL tiers (1 h user data, 24 h static/schema data)
- Pattern-based invalidation on graph mutations
- Hit/miss metric counters (in-process, can be scraped by Prometheus)
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from shared.database.redis import RedisClient, get_redis_client

logger = logging.getLogger(__name__)

# ─── TTL constants (seconds) ────────────────────────────────────────────────────

TTL_USER_DATA = 3_600       # 1 hour — user context, patterns, recommendations
TTL_STATIC_DATA = 86_400    # 24 hours — schema status, node-type lists
TTL_QUERY_DATA = 600        # 10 minutes — arbitrary Cypher results
TTL_PATH_DATA = 1_800       # 30 minutes — shortest-path results

# ─── In-process metrics (thread-safe counters) ──────────────────────────────────

_metrics: dict[str, int] = defaultdict(int)


def _inc(counter: str) -> None:
    _metrics[counter] += 1


def get_cache_metrics() -> dict[str, int]:
    """Return a copy of the current hit/miss counters."""
    return dict(_metrics)


# ─── Cache key helpers ────────────────────────────────────────────────────────────

def _stable_hash(obj: Any) -> str:
    """Return a short, stable SHA-256 hex digest for any JSON-serialisable object."""
    serialised = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(serialised.encode()).hexdigest()[:16]


def build_cache_key(namespace: str, *parts: Any) -> str:
    """
    Build a namespaced, collision-resistant cache key.

    Examples::

        build_cache_key("user_context", user_id)
        # -> "gqs:user_context:abc123"

        build_cache_key("cypher", cypher_string, params_dict)
        # -> "gqs:cypher:<hash>"
    """
    if len(parts) == 1 and isinstance(parts[0], str):
        return f"gqs:{namespace}:{parts[0]}"
    combined = ":".join(str(p) if isinstance(p, str) else _stable_hash(p) for p in parts)
    return f"gqs:{namespace}:{combined}"


# ─── Invalidation patterns per entity ──────────────────────────────────────────────

INVALIDATION_PATTERNS: dict[str, list[str]] = {
    "node": [
        "gqs:node:*",
        "gqs:node_types:*",
        "gqs:subgraph:*",
    ],
    "user": [
        "gqs:user_context:*",
        "gqs:similar_patterns:*",
        "gqs:recommendations:*",
        "gqs:node:*",
    ],
    "goal": [
        "gqs:goal_impact:*",
        "gqs:user_context:*",
        "gqs:recommendations:*",
        "gqs:subgraph:*",
    ],
    "relationship": [
        "gqs:path:*",
        "gqs:subgraph:*",
        "gqs:user_context:*",
    ],
    "schema": [
        "gqs:schema_status:*",
        "gqs:node_types:*",
    ],
}


class CacheService:
    """
    High-level cache operations for the Graph Query Service.

    Falls back silently to a no-op when Redis is unavailable so that
    the service continues to function (just slower).
    """

    def __init__(self, redis: RedisClient | None = None) -> None:
        self._redis: RedisClient | None = redis
        self._available: bool = True  # toggled False after connection failure

    # ─── Connection ───────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Initialise Redis connection."""
        client = self._redis or get_redis_client()
        try:
            await client.connect()
            alive = await client.health_check()
            self._available = alive
            self._redis = client
            if alive:
                logger.info("CacheService: Redis connected and healthy")
            else:
                logger.warning("CacheService: Redis ping failed — operating in no-cache mode")
        except Exception as exc:
            logger.warning("CacheService: Redis unavailable (%s) — no-cache mode", exc)
            self._available = False

    async def close(self) -> None:
        if self._redis and self._available:
            await self._redis.close()

    # ─── Core get/set/delete ──────────────────────────────────────────────────────────

    async def get(self, key: str) -> Any | None:
        """Retrieve cached value; returns None on miss or error."""
        if not self._available or self._redis is None:
            _inc("miss_unavailable")
            return None
        try:
            value = await self._redis.get(key)
            if value is None:
                _inc("miss")
                logger.debug("Cache MISS: %s", key)
            else:
                _inc("hit")
                logger.debug("Cache HIT: %s", key)
            return value
        except Exception as exc:
            logger.warning("CacheService.get failed for key '%s': %s", key, exc)
            _inc("error")
            return None

    async def set(self, key: str, value: Any, ttl: int = TTL_USER_DATA) -> bool:
        """Store a value with a TTL. Returns True on success."""
        if not self._available or self._redis is None:
            return False
        try:
            result = await self._redis.set(key, value, ttl=ttl)
            _inc("set")
            logger.debug("Cache SET: %s (ttl=%ds)", key, ttl)
            return result
        except Exception as exc:
            logger.warning("CacheService.set failed for key '%s': %s", key, exc)
            _inc("error")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a single cache key."""
        if not self._available or self._redis is None:
            return False
        try:
            deleted = await self._redis.delete(key)
            _inc("delete")
            return deleted > 0
        except Exception as exc:
            logger.warning("CacheService.delete failed for key '%s': %s", key, exc)
            return False

    # ─── Invalidation ──────────────────────────────────────────────────────────────

    async def invalidate_entity(self, entity_type: str, entity_id: str | None = None) -> int:
        """
        Invalidate all cache keys related to an entity mutation.

        Args:
            entity_type: One of 'node', 'user', 'goal', 'relationship', 'schema'.
            entity_id: Optional specific entity ID to target a narrower pattern.

        Returns:
            Total number of keys deleted.
        """
        if not self._available or self._redis is None:
            return 0

        patterns = INVALIDATION_PATTERNS.get(entity_type, ["gqs:*"])
        total_deleted = 0
        for pattern in patterns:
            # If we have a specific ID, tighten the pattern
            if entity_id and "*" in pattern:
                narrowed = pattern.replace("*", entity_id + ":*", 1)
                deleted = await self._redis.invalidate_pattern(narrowed)
                if deleted == 0:
                    # Fall back to broad pattern
                    deleted = 0
                total_deleted += deleted
            deleted = await self._redis.invalidate_pattern(pattern)
            total_deleted += deleted

        _inc("invalidate")
        logger.debug(
            "CacheService: invalidated %d keys for entity_type='%s'",
            total_deleted,
            entity_type,
        )
        return total_deleted

    async def invalidate_user(self, user_id: str) -> int:
        """Invalidate all cache entries for a specific user."""
        if not self._available or self._redis is None:
            return 0
        patterns = [
            f"gqs:user_context:{user_id}",
            f"gqs:similar_patterns:{user_id}",
            f"gqs:recommendations:{user_id}",
        ]
        total = 0
        for key in patterns:
            if await self._redis.delete(key):
                total += 1
        _inc("invalidate")
        return total

    # ─── Typed helpers ────────────────────────────────────────────────────────────

    async def get_user_context(self, user_id: str) -> Any | None:
        key = build_cache_key("user_context", user_id)
        return await self.get(key)

    async def set_user_context(self, user_id: str, data: Any) -> bool:
        key = build_cache_key("user_context", user_id)
        return await self.set(key, data, ttl=TTL_USER_DATA)

    async def get_goal_impact(self, goal_id: str) -> Any | None:
        key = build_cache_key("goal_impact", goal_id)
        return await self.get(key)

    async def set_goal_impact(self, goal_id: str, data: Any) -> bool:
        key = build_cache_key("goal_impact", goal_id)
        return await self.set(key, data, ttl=TTL_USER_DATA)

    async def get_similar_patterns(self, user_id: str) -> Any | None:
        key = build_cache_key("similar_patterns", user_id)
        return await self.get(key)

    async def set_similar_patterns(self, user_id: str, data: Any) -> bool:
        key = build_cache_key("similar_patterns", user_id)
        return await self.set(key, data, ttl=TTL_USER_DATA)

    async def get_recommendations(self, user_id: str) -> Any | None:
        key = build_cache_key("recommendations", user_id)
        return await self.get(key)

    async def set_recommendations(self, user_id: str, data: Any) -> bool:
        key = build_cache_key("recommendations", user_id)
        return await self.set(key, data, ttl=TTL_USER_DATA)

    async def get_schema_status(self) -> Any | None:
        key = build_cache_key("schema_status", "global")
        return await self.get(key)

    async def set_schema_status(self, data: Any) -> bool:
        key = build_cache_key("schema_status", "global")
        return await self.set(key, data, ttl=TTL_STATIC_DATA)

    async def get_node_types(self) -> Any | None:
        key = build_cache_key("node_types", "global")
        return await self.get(key)

    async def set_node_types(self, data: Any) -> bool:
        key = build_cache_key("node_types", "global")
        return await self.set(key, data, ttl=TTL_STATIC_DATA)

    async def get_path(self, source_id: str, target_id: str) -> Any | None:
        key = build_cache_key("path", source_id, target_id)
        return await self.get(key)

    async def set_path(self, source_id: str, target_id: str, data: Any) -> bool:
        key = build_cache_key("path", source_id, target_id)
        return await self.set(key, data, ttl=TTL_PATH_DATA)

    async def get_cypher_result(self, cypher: str, params: dict[str, Any]) -> Any | None:
        key = build_cache_key("cypher", cypher, params)
        return await self.get(key)

    async def set_cypher_result(
        self, cypher: str, params: dict[str, Any], data: Any
    ) -> bool:
        key = build_cache_key("cypher", cypher, params)
        return await self.set(key, data, ttl=TTL_QUERY_DATA)

    async def health_check(self) -> bool:
        if not self._available or self._redis is None:
            return False
        return await self._redis.health_check()


# ─── Module-level singleton ─────────────────────────────────────────────────────────

_cache_service: CacheService | None = None


def get_cache_service() -> CacheService:
    """Return the module-level CacheService singleton."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
