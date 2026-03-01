#!/usr/bin/env python3
"""
ZenSensei Neo4j Migration Script

Creates all Neo4j indexes, constraints, and seed graph nodes.

Usage:
    python scripts/migrate_neo4j.py [--uri bolt://localhost:7687] [--drop-existing]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("migrate_neo4j")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "localdev")

SCHEMA_TAG = "graph-schema-v2025-11"

CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (g:Goal) REQUIRE g.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Task) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Insight) REQUIRE i.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Notification) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (intg:Integration) REQUIRE intg.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (o:Organization) REQUIRE o.id IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS FOR (u:User) ON (u.email)",
    "CREATE INDEX IF NOT EXISTS FOR (u:User) ON (u.life_stage)",
    "CREATE INDEX IF NOT EXISTS FOR (g:Goal) ON (g.user_id)",
    "CREATE INDEX IF NOT EXISTS FOR (g:Goal) ON (g.category)",
    "CREATE INDEX IF NOT EXISTS FOR (g:Goal) ON (g.status)",
    "CREATE INDEX IF NOT EXISTS FOR (t:Task) ON (t.user_id)",
    "CREATE INDEX IF NOT EXISTS FOR (t:Task) ON (t.goal_id)",
    "CREATE INDEX IF NOT EXISTS FOR (t:Task) ON (t.status)",
    "CREATE INDEX IF NOT EXISTS FOR (i:Insight) ON (i.user_id)",
    "CREATE INDEX IF NOT EXISTS FOR (i:Insight) ON (i.insight_type)",
    "CREATE INDEX IF NOT EXISTS FOR (e:Event) ON (e.user_id)",
    "CREATE INDEX IF NOT EXISTS FOR (e:Event) ON (e.start_time)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Notification) ON (n.user_id)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Notification) ON (n.is_read)",
]


def run_migrations(uri: str, user: str, password: str, drop_existing: bool = False) -> None:
    try:
        from neo4j import GraphDatabase
    except ImportError:
        log.error("neo4j driver not installed. Run: pip install neo4j")
        sys.exit(1)

    log.info("Connecting to Neo4j at %s", uri)
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        with driver.session() as session:
            if drop_existing:
                log.warning("Dropping all existing constraints and indexes...")
                session.run("CALL apoc.schema.assert({}, {})")

            log.info("Creating constraints...")
            for cypher in CONSTRAINTS:
                log.debug("  %s", cypher)
                session.run(cypher)
            log.info("Created %d constraints", len(CONSTRAINTS))

            log.info("Creating indexes...")
            for cypher in INDEXES:
                log.debug("  %s", cypher)
                session.run(cypher)
            log.info("Created %d indexes", len(INDEXES))

            session.run(
                """
                MERGE (sm:SchemaMetadata {scope_tag: $tag})
                SET sm.applied_at = datetime(), sm.version = 1
                """,
                tag=SCHEMA_TAG,
            )
            log.info("Schema metadata updated: %s", SCHEMA_TAG)

    finally:
        driver.close()

    log.info("Migration complete!")


def main() -> None:
    parser = argparse.ArgumentParser(description="ZenSensei Neo4j migration")
    parser.add_argument("--uri", default=NEO4J_URI)
    parser.add_argument("--user", default=NEO4J_USER)
    parser.add_argument("--password", default=NEO4J_PASSWORD)
    parser.add_argument("--drop-existing", action="store_true")
    args = parser.parse_args()

    run_migrations(
        uri=args.uri,
        user=args.user,
        password=args.password,
        drop_existing=args.drop_existing,
    )


if __name__ == "__main__":
    main()
