"""
ZenSensei Shared Database - Neo4j Client

Async Neo4j driver wrapper with connection pooling, session management,
and a simple health-check endpoint.
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncGraphDatabase, AsyncDriver

from shared.config import ZenSenseiConfig, get_config

logger = logging.getLogger(__name__)


class Neo4jClient:
    """
    Thin async Neo4j wrapper.

    Usage::

        client = Neo4jClient()
        await client.connect()

        results = await client.run_query(
            "MATCH (n:Person {id: $id}) RETURN n",
            {"id": "user-123"},
        )
        await client.close()
    """

    def __init__(self, config: ZenSenseiConfig | None = None) -> None:
        self._config = config or get_config()
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        """Open the Neo4j driver. Call once on service startup."""
        if self._driver is not None:
            return

        self._driver = AsyncGraphDatabase.driver(
            self._config.neo4j_uri,
            auth=(self._config.neo4j_user, self._config.neo4j_password),
            max_connection_pool_size=self._config.neo4j_max_connection_pool_size,
            connection_timeout=self._config.neo4j_connection_timeout,
        )
        logger.info("Neo4j driver initialised", extra={"uri": self._config.neo4j_uri})

    async def close(self) -> None:
        """Close the Neo4j driver. Call on service shutdown."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j driver closed")

    def _assert_connected(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError("Neo4jClient.connect() must be called first")
        return self._driver

    async def run_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str = "neo4j",
    ) -> list[dict[str, Any]]:
        """
        Run a Cypher query and return all result records as dicts.

        Args:
            query: Cypher query string.
            parameters: Optional query parameters.
            database: Neo4j database name (default ``"neo4j"``).

        Returns:
            List of result records, each as a ``{key: value}`` dict.
        """
        driver = self._assert_connected()
        async with driver.session(database=database) as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return records

    async def run_query_single(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str = "neo4j",
    ) -> dict[str, Any] | None:
        """
        Run a Cypher query and return only the first result record.

        Returns ``None`` if no records were returned.
        """
        records = await self.run_query(query, parameters, database)
        return records[0] if records else None

    async def run_write_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str = "neo4j",
    ) -> list[dict[str, Any]]:
        """
        Run a write (CREATE/MERGE/SET/DELETE) Cypher query in a write transaction.

        Prefer this over ``run_query`` for mutations to avoid read-replica routing.
        """
        driver = self._assert_connected()
        async with driver.session(database=database) as session:
            result = await session.execute_write(
                lambda tx: tx.run(query, parameters or {})
            )
            records = await result.data()
            return records

    async def health_check(self) -> bool:
        """Return True if Neo4j is reachable."""
        try:
            driver = self._assert_connected()
            await driver.verify_connectivity()
            return True
        except Exception:
            return False


# ─── Singleton helper ────────────────────────────────────────────────────────────

_neo4j_client: Neo4jClient | None = None


def get_neo4j_client() -> Neo4jClient:
    """Return a module-level singleton Neo4jClient."""
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient()
    return _neo4j_client
