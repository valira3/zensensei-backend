"""
ZenSensei Graph Query Service - Graph Service

Core Neo4j operations layer.  All public methods transparently fall back
to an in-memory dict-based graph when Neo4j is unavailable, ensuring the
service remains functional in local / test environments with no infrastructure.

Design decisions
----------------
- All Cypher is parameterised — no f-string / format interpolation of user data.
- Traversal depth is always bounded (max 5 hops) to prevent runaway queries.
- Node labels are validated against NodeType before being injected into queries.
- The in-memory fallback implements the same interface as the Neo4j path.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from shared.database.neo4j import Neo4jClient, get_neo4j_client
from shared.models.graph import NodeType, RelationshipType

from services.graph_query_service import cypher_queries as Q

logger = logging.getLogger(__name__)

# ─── Constants ──────────────────────────────────────────────────────────────────

_VALID_LABEL_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_VALID_REL_TYPE_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
MAX_SUBGRAPH_DEPTH = 5


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _validate_label(label: str) -> str:
    """Raise ValueError if label is not a safe Neo4j identifier."""
    if not _VALID_LABEL_RE.match(label):
        raise ValueError(f"Invalid node label: {label!r}")
    return label


def _validate_rel_type(rel_type: str) -> str:
    """Raise ValueError if rel_type is not a safe Neo4j identifier."""
    if not _VALID_REL_TYPE_RE.match(rel_type):
        raise ValueError(f"Invalid relationship type: {rel_type!r}")
    return rel_type


# ─── In-Memory Graph Fallback ────────────────────────────────────────────────────────


class InMemoryGraph:
    """
    Minimal in-memory graph store that mirrors the Neo4j interface.

    Suitable for development, tests, and CI without a running Neo4j instance.
    Not intended for production use.
    """

    def __init__(self) -> None:
        # id -> node dict
        self._nodes: dict[str, dict[str, Any]] = {}
        # id -> rel dict
        self._rels: dict[str, dict[str, Any]] = {}

    # ── Nodes ───────────────────────────────────────────────────────────────────────────

    def create_node(
        self,
        node_id: str,
        node_type: str,
        properties: dict[str, Any],
        schema_scope: str | None,
    ) -> dict[str, Any]:
        node: dict[str, Any] = {
            "id": node_id,
            "labels": [node_type],
            "properties": {**properties, "id": node_id},
            "schema_scope": schema_scope,
            "created_at": _now_iso(),
        }
        self._nodes[node_id] = node
        return node

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._nodes.get(node_id)

    def update_node(self, node_id: str, properties: dict[str, Any]) -> dict[str, Any] | None:
        node = self._nodes.get(node_id)
        if node is None:
            return None
        node["properties"].update(properties)
        node["updated_at"] = _now_iso()
        return node

    def delete_node(self, node_id: str) -> int:
        if node_id not in self._nodes:
            return 0
        del self._nodes[node_id]
        # Cascade-delete relationships
        to_delete = [
            rid for rid, r in self._rels.items()
            if r["source_id"] == node_id or r["target_id"] == node_id
        ]
        for rid in to_delete:
            del self._rels[rid]
        return 1

    def search_nodes(
        self,
        node_type: str | None = None,
        props: dict[str, Any] | None = None,
        full_text: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        results = []
        for node in self._nodes.values():
            if node_type and node_type not in node["labels"]:
                continue
            if props:
                node_props = node["properties"]
                if not all(node_props.get(k) == v for k, v in props.items()):
                    continue
            if full_text:
                ft = full_text.lower()
                text_blob = json_flatten(node["properties"])
                if ft not in text_blob:
                    continue
            results.append(node)
        return results[skip: skip + limit]

    def list_node_types(self) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for node in self._nodes.values():
            for lbl in node.get("labels", []):
                counts[lbl] = counts.get(lbl, 0) + 1
        return [{"type": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]

    # ── Relationships ─────────────────────────────────────────────────────────────────

    def create_relationship(
        self,
        rel_id: str,
        rel_type: str,
        source_id: str,
        target_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any] | None:
        if source_id not in self._nodes or target_id not in self._nodes:
            return None
        rel: dict[str, Any] = {
            "id": rel_id,
            "type": rel_type,
            "source_id": source_id,
            "target_id": target_id,
            "properties": properties,
            "created_at": _now_iso(),
        }
        self._rels[rel_id] = rel
        return rel

    def get_relationship(self, rel_id: str) -> dict[str, Any] | None:
        return self._rels.get(rel_id)

    def update_relationship(
        self, rel_id: str, properties: dict[str, Any]
    ) -> dict[str, Any] | None:
        rel = self._rels.get(rel_id)
        if rel is None:
            return None
        rel["properties"].update(properties)
        rel["updated_at"] = _now_iso()
        return rel

    def delete_relationship(self, rel_id: str) -> int:
        if rel_id not in self._rels:
            return 0
        del self._rels[rel_id]
        return 1

    def get_node_relationships(
        self,
        node_id: str,
        direction: str = "BOTH",
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        results = []
        for rel in self._rels.values():
            if direction == "BOTH":
                if rel["source_id"] == node_id or rel["target_id"] == node_id:
                    results.append(rel)
            elif direction == "OUT" and rel["source_id"] == node_id:
                results.append(rel)
            elif direction == "IN" and rel["target_id"] == node_id:
                results.append(rel)
        return results[skip: skip + limit]

    # ── Graph Queries ─────────────────────────────────────────────────────────────────

    def user_context(self, user_id: str) -> dict[str, Any]:
        user = self._nodes.get(user_id)
        if user is None:
            return {}

        # BFS up to depth 2
        visited: set[str] = {user_id}
        goals, tasks, events, insights, milestones, habits = [], [], [], [], [], []
        relationships: list[dict[str, Any]] = []

        def collect(nid: str, depth: int) -> None:
            if depth > 2:
                return
            for rel in self._rels.values():
                neighbour_id: str | None = None
                if rel["source_id"] == nid:
                    neighbour_id = rel["target_id"]
                elif rel["target_id"] == nid:
                    neighbour_id = rel["source_id"]
                if neighbour_id and neighbour_id not in visited:
                    visited.add(neighbour_id)
                    relationships.append(rel)
                    neighbour = self._nodes.get(neighbour_id, {})
                    labels = neighbour.get("labels", [])
                    props = neighbour.get("properties", {})
                    if "GOAL" in labels:
                        goals.append(props)
                    elif "TASK" in labels:
                        tasks.append(props)
                    elif "EVENT" in labels:
                        events.append(props)
                    elif "INSIGHT" in labels:
                        insights.append(props)
                    elif "MILESTONE" in labels:
                        milestones.append(props)
                    elif "HABIT" in labels:
                        habits.append(props)
                    if depth < 2:
                        collect(neighbour_id, depth + 1)

        collect(user_id, 1)
        return {
            "user": user.get("properties", {}),
            "goals": goals,
            "tasks": tasks,
            "events": events,
            "insights": insights,
            "milestones": milestones,
            "habits": habits,
            "relationships": relationships,
        }

    def goal_impact(self, goal_id: str) -> dict[str, Any]:
        goal = self._nodes.get(goal_id)
        if goal is None:
            return {}
        tasks, milestones, sub_goals, insights, dependent_goals, affected = [], [], [], [], [], []
        owner_ids: list[str] = []
        for rel in self._rels.values():
            if rel["source_id"] == goal_id:
                n = self._nodes.get(rel["target_id"], {})
                labels = n.get("labels", [])
                props = n.get("properties", {})
                if "TASK" in labels:
                    tasks.append(props)
                elif "MILESTONE" in labels:
                    milestones.append(props)
                elif "GOAL" in labels:
                    sub_goals.append(props)
                elif "INSIGHT" in labels:
                    insights.append(props)
            elif rel["target_id"] == goal_id:
                n = self._nodes.get(rel["source_id"], {})
                labels = n.get("labels", [])
                props = n.get("properties", {})
                if "PERSON" in labels:
                    owner_ids.append(n.get("id", ""))
                elif "GOAL" in labels:
                    dependent_goals.append(props)
        return {
            "goal": goal.get("properties", {}),
            "tasks": tasks,
            "milestones": milestones,
            "sub_goals": sub_goals,
            "insights": insights,
            "owner_ids": owner_ids,
            "dependent_goals": dependent_goals,
            "affected_nodes": affected,
        }

    def similar_patterns(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        # Simplified: find users who share any goal category
        user_goals = [
            n["properties"]
            for n in self._nodes.values()
            if "GOAL" in n.get("labels", [])
            and n["properties"].get("user_id") == user_id
        ]
        user_categories = {g.get("category") for g in user_goals}
        if not user_categories:
            return []

        other_scores: dict[str, dict[str, Any]] = {}
        for node in self._nodes.values():
            if "GOAL" not in node.get("labels", []):
                continue
            p = node["properties"]
            oid = p.get("user_id")
            if not oid or oid == user_id:
                continue
            cat = p.get("category")
            if cat in user_categories:
                if oid not in other_scores:
                    other_scores[oid] = {
                        "user_id": oid,
                        "display_name": None,
                        "shared_categories": 0,
                        "shared_goal_count": 0,
                        "shared_task_pattern_count": 0,
                        "similarity_score": 0.0,
                    }
                other_scores[oid]["shared_categories"] += 1
                other_scores[oid]["shared_goal_count"] += 1
                other_scores[oid]["similarity_score"] += 3.0

        return sorted(other_scores.values(), key=lambda x: -x["similarity_score"])[:limit]

    def shortest_path(
        self, source_id: str, target_id: str
    ) -> list[tuple[str, str | None]] | None:
        """BFS — returns list of (node_id, rel_id_or_None) tuples."""
        if source_id not in self._nodes or target_id not in self._nodes:
            return None
        if source_id == target_id:
            return [(source_id, None)]

        from collections import deque

        queue: deque[list[tuple[str, str | None]]] = deque()
        queue.append([(source_id, None)])
        visited = {source_id}

        while queue:
            path = queue.popleft()
            current = path[-1][0]
            if len(path) > 7:  # max 6 hops
                continue
            for rel in self._rels.values():
                nbr: str | None = None
                if rel["source_id"] == current:
                    nbr = rel["target_id"]
                elif rel["target_id"] == current:
                    nbr = rel["source_id"]
                if nbr and nbr not in visited:
                    new_path = path + [(nbr, rel["id"])]
                    if nbr == target_id:
                        return new_path
                    visited.add(nbr)
                    queue.append(new_path)
        return None

    def recommendations(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return goals from similar users that the target user does not yet have."""
        patterns = self.similar_patterns(user_id, limit=20)
        user_goal_titles = {
            n["properties"].get("title", "")
            for n in self._nodes.values()
            if "GOAL" in n.get("labels", [])
            and n["properties"].get("user_id") == user_id
        }
        seen: set[str] = set()
        recs = []
        for pattern in patterns:
            oid = pattern["user_id"]
            for node in self._nodes.values():
                if "GOAL" not in node.get("labels", []):
                    continue
                p = node["properties"]
                if p.get("user_id") != oid:
                    continue
                title = p.get("title", "")
                if title in user_goal_titles or title in seen:
                    continue
                seen.add(title)
                recs.append({
                    "id": p.get("id", ""),
                    "title": title,
                    "category": p.get("category"),
                    "endorsement_count": 1,
                    "supporting_insights": [],
                    "recommendation_type": "goal",
                    "score": pattern["similarity_score"],
                })
                if len(recs) >= limit:
                    return recs
        return recs

    def get_subgraph(self, root_id: str, depth: int) -> dict[str, Any]:
        """BFS subgraph up to *depth* hops from root."""
        depth = min(depth, MAX_SUBGRAPH_DEPTH)
        visited_nodes: dict[str, dict[str, Any]] = {}
        visited_rels: dict[str, dict[str, Any]] = {}
        frontier = {root_id}
        for _ in range(depth):
            next_frontier: set[str] = set()
            for nid in frontier:
                if nid in self._nodes:
                    visited_nodes[nid] = self._nodes[nid]
                for rel in self._rels.values():
                    nbr: str | None = None
                    if rel["source_id"] == nid:
                        nbr = rel["target_id"]
                    elif rel["target_id"] == nid:
                        nbr = rel["source_id"]
                    if nbr and nbr not in visited_nodes:
                        visited_rels[rel["id"]] = rel
                        next_frontier.add(nbr)
            frontier = next_frontier
        for nid in frontier:
            if nid in self._nodes:
                visited_nodes[nid] = self._nodes[nid]
        return {
            "nodes": list(visited_nodes.values()),
            "relationships": list(visited_rels.values()),
        }

    def count_nodes_by_label(self) -> list[dict[str, Any]]:
        return self.list_node_types()

    def count_rels_by_type(self) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for rel in self._rels.values():
            rt = rel.get("type", "UNKNOWN")
            counts[rt] = counts.get(rt, 0) + 1
        return [{"type": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]

    def total_nodes(self) -> int:
        return len(self._nodes)

    def total_rels(self) -> int:
        return len(self._rels)

    def delete_by_scope(self, scope: str) -> int:
        to_delete = [nid for nid, n in self._nodes.items() if n.get("schema_scope") == scope]
        for nid in to_delete:
            self.delete_node(nid)
        return len(to_delete)


def json_flatten(obj: Any) -> str:
    """Convert dict/list/any to lowercase string for full-text matching."""
    import json as _json
    try:
        return _json.dumps(obj, default=str).lower()
    except Exception:
        return str(obj).lower()


# ─── GraphService ────────────────────────────────────────────────────────────────


class GraphService:
    """
    High-level graph operations.  Uses Neo4j when available, falls back to
    the in-memory graph transparently.
    """

    def __init__(
        self,
        neo4j: Neo4jClient | None = None,
        fallback: InMemoryGraph | None = None,
    ) -> None:
        self._neo4j: Neo4jClient | None = neo4j
        self._mem: InMemoryGraph = fallback or InMemoryGraph()
        self._neo4j_ok: bool = False

    # ─── Connection ───────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        client = self._neo4j or get_neo4j_client()
        try:
            await client.connect()
            ok = await client.health_check()
            self._neo4j_ok = ok
            self._neo4j = client
            if ok:
                logger.info("GraphService: Neo4j connected and healthy")
            else:
                logger.warning("GraphService: Neo4j ping failed — using in-memory graph")
        except Exception as exc:
            logger.warning("GraphService: Neo4j unavailable (%s) — using in-memory graph", exc)
            self._neo4j_ok = False

    async def close(self) -> None:
        if self._neo4j and self._neo4j_ok:
            await self._neo4j.close()

    async def health_check(self) -> bool:
        if self._neo4j_ok and self._neo4j:
            return await self._neo4j.health_check()
        return True  # in-memory is always available

    @property
    def backend(self) -> str:
        return "neo4j" if self._neo4j_ok else "in-memory"

    # ─── Node CRUD ────────────────────────────────────────────────────────────────

    async def create_node(
        self,
        node_type: str,
        properties: dict[str, Any],
        schema_scope: str | None = None,
        node_id: str | None = None,
    ) -> dict[str, Any]:
        label = _validate_label(node_type.upper())
        nid = node_id or str(uuid.uuid4())
        created_at = _now_iso()

        if self._neo4j_ok and self._neo4j:
            try:
                cypher = Q.CREATE_NODE_TYPED.format(label=label)
                result = await self._neo4j.run_query_single(
                    cypher,
                    params={
                        "id": nid,
                        "properties": {**properties, "id": nid},
                        "created_at": created_at,
                        "schema_scope": schema_scope,
                    },
                )
                if result:
                    node = result.get("node", {})
                    return _neo4j_node_to_dict(node, label)
            except Exception as exc:
                logger.error("Neo4j create_node failed: %s — falling back", exc)

        return self._mem.create_node(nid, label, properties, schema_scope)

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        if self._neo4j_ok and self._neo4j:
            try:
                result = await self._neo4j.run_query_single(
                    Q.GET_NODE_BY_ID, {"id": node_id}
                )
                if result:
                    node = result.get("node", {})
                    labels = result.get("labels", [])
                    return _neo4j_node_to_dict(node, labels[0] if labels else "UNKNOWN")
            except Exception as exc:
                logger.error("Neo4j get_node failed: %s — falling back", exc)

        return self._mem.get_node(node_id)

    async def update_node(
        self, node_id: str, properties: dict[str, Any]
    ) -> dict[str, Any] | None:
        updated_at = _now_iso()
        if self._neo4j_ok and self._neo4j:
            try:
                result = await self._neo4j.run_query_single(
                    Q.UPDATE_NODE,
                    {"id": node_id, "properties": properties, "updated_at": updated_at},
                )
                if result:
                    node = result.get("node", {})
                    labels = result.get("labels", [])
                    return _neo4j_node_to_dict(node, labels[0] if labels else "UNKNOWN")
            except Exception as exc:
                logger.error("Neo4j update_node failed: %s — falling back", exc)

        return self._mem.update_node(node_id, properties)

    async def delete_node(self, node_id: str) -> int:
        if self._neo4j_ok and self._neo4j:
            try:
                result = await self._neo4j.run_query_single(
                    Q.DELETE_NODE, {"id": node_id}
                )
                return int(result.get("deleted", 0)) if result else 0
            except Exception as exc:
                logger.error("Neo4j delete_node failed: %s — falling back", exc)

        return self._mem.delete_node(node_id)

    async def search_nodes(
        self,
        node_type: str | None = None,
        props: dict[str, Any] | None = None,
        full_text: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if self._neo4j_ok and self._neo4j:
            try:
                if full_text:
                    results = await self._neo4j.run_query(
                        Q.SEARCH_NODES_FULLTEXT,
                        {
                            "query": full_text,
                            "type": node_type or "",
                            "skip": skip,
                            "limit": limit,
                        },
                    )
                    return [_neo4j_node_to_dict(r.get("node", {}), node_type or "UNKNOWN") for r in results]
                elif node_type:
                    label = _validate_label(node_type.upper())
                    cypher = Q.SEARCH_NODES_BY_TYPE.format(label=label)
                    results = await self._neo4j.run_query(
                        cypher,
                        {"props": props or {}, "skip": skip, "limit": limit},
                    )
                    return [_neo4j_node_to_dict(r.get("node", {}), label) for r in results]
            except Exception as exc:
                logger.error("Neo4j search_nodes failed: %s — falling back", exc)

        return self._mem.search_nodes(node_type, props, full_text, skip, limit)

    async def list_node_types(self) -> list[dict[str, Any]]:
        if self._neo4j_ok and self._neo4j:
            try:
                return await self._neo4j.run_query(Q.LIST_NODE_TYPES_SIMPLE)
            except Exception as exc:
                logger.error("Neo4j list_node_types failed: %s — falling back", exc)

        return self._mem.list_node_types()

    # ─── Relationship CRUD ──────────────────────────────────────────────────────────

    async def create_relationship(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
        rel_id: str | None = None,
    ) -> dict[str, Any] | None:
        rtype = _validate_rel_type(rel_type.upper())
        rid = rel_id or str(uuid.uuid4())
        props = properties or {}
        created_at = _now_iso()

        if self._neo4j_ok and self._neo4j:
            try:
                cypher = Q.CREATE_RELATIONSHIP_TYPED.format(rel_type=rtype)
                result = await self._neo4j.run_query_single(
                    cypher,
                    {
                        "id": rid,
                        "source_id": source_id,
                        "target_id": target_id,
                        "properties": props,
                        "created_at": created_at,
                    },
                )
                if result:
                    return _neo4j_rel_to_dict(result.get("rel", {}), result)
            except Exception as exc:
                logger.error("Neo4j create_relationship failed: %s — falling back", exc)

        return self._mem.create_relationship(rid, rtype, source_id, target_id, props)

    async def get_relationship(self, rel_id: str) -> dict[str, Any] | None:
        if self._neo4j_ok and self._neo4j:
            try:
                result = await self._neo4j.run_query_single(
                    Q.GET_RELATIONSHIP_BY_ID, {"id": rel_id}
                )
                if result:
                    return _neo4j_rel_to_dict(result.get("rel", {}), result)
            except Exception as exc:
                logger.error("Neo4j get_relationship failed: %s — falling back", exc)

        return self._mem.get_relationship(rel_id)

    async def update_relationship(
        self, rel_id: str, properties: dict[str, Any]
    ) -> dict[str, Any] | None:
        updated_at = _now_iso()
        if self._neo4j_ok and self._neo4j:
            try:
                result = await self._neo4j.run_query_single(
                    Q.UPDATE_RELATIONSHIP,
                    {"id": rel_id, "properties": properties, "updated_at": updated_at},
                )
                if result:
                    return _neo4j_rel_to_dict(result.get("rel", {}), result)
            except Exception as exc:
                logger.error("Neo4j update_relationship failed: %s — falling back", exc)

        return self._mem.update_relationship(rel_id, properties)

    async def delete_relationship(self, rel_id: str) -> int:
        if self._neo4j_ok and self._neo4j:
            try:
                result = await self._neo4j.run_query_single(
                    Q.DELETE_RELATIONSHIP, {"id": rel_id}
                )
                return int(result.get("deleted", 0)) if result else 0
            except Exception as exc:
                logger.error("Neo4j delete_relationship failed: %s — falling back", exc)

        return self._mem.delete_relationship(rel_id)

    async def get_node_relationships(
        self,
        node_id: str,
        direction: str = "BOTH",
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if self._neo4j_ok and self._neo4j:
            try:
                results = await self._neo4j.run_query(
                    Q.GET_NODE_RELATIONSHIPS,
                    {
                        "node_id": node_id,
                        "direction": direction.upper(),
                        "skip": skip,
                        "limit": limit,
                    },
                )
                return [_neo4j_rel_to_dict(r.get("rel", {}), r) for r in results]
            except Exception as exc:
                logger.error("Neo4j get_node_relationships failed: %s — falling back", exc)

        return self._mem.get_node_relationships(node_id, direction, skip, limit)

    # ─── Complex Queries ────────────────────────────────────────────────────────────

    async def get_user_context(self, user_id: str) -> dict[str, Any]:
        if self._neo4j_ok and self._neo4j:
            try:
                result = await self._neo4j.run_query_single(
                    Q.USER_CONTEXT_STRUCTURED, {"user_id": user_id}
                )
                if result:
                    return _parse_user_context(result, user_id)
            except Exception as exc:
                logger.error("Neo4j user_context failed: %s — falling back", exc)

        return self._mem.user_context(user_id)

    async def get_goal_impact(self, goal_id: str) -> dict[str, Any]:
        if self._neo4j_ok and self._neo4j:
            try:
                result = await self._neo4j.run_query_single(
                    Q.GOAL_IMPACT_QUERY, {"goal_id": goal_id}
                )
                if result:
                    return _parse_goal_impact(result, goal_id)
            except Exception as exc:
                logger.error("Neo4j goal_impact failed: %s — falling back", exc)

        return self._mem.goal_impact(goal_id)

    async def get_similar_patterns(
        self, user_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        if self._neo4j_ok and self._neo4j:
            try:
                results = await self._neo4j.run_query(
                    Q.SIMILAR_PATTERNS_QUERY, {"user_id": user_id, "limit": limit}
                )
                return results
            except Exception as exc:
                logger.error("Neo4j similar_patterns failed: %s — falling back", exc)

        return self._mem.similar_patterns(user_id, limit)

    async def get_subgraph(self, root_id: str, depth: int = 2) -> dict[str, Any]:
        depth = min(depth, MAX_SUBGRAPH_DEPTH)
        if self._neo4j_ok and self._neo4j:
            try:
                results = await self._neo4j.run_query_single(
                    Q.SUBGRAPH_QUERY, {"root_id": root_id, "depth": depth}
                )
                if results:
                    return {
                        "nodes": results.get("nodes", []),
                        "relationships": results.get("relationships", []),
                    }
            except Exception as exc:
                logger.error("Neo4j subgraph failed: %s — falling back", exc)

        return self._mem.get_subgraph(root_id, depth)

    async def run_cypher(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        database: str = "neo4j",
    ) -> list[dict[str, Any]]:
        if self._neo4j_ok and self._neo4j:
            return await self._neo4j.run_query(cypher, params, database)
        raise RuntimeError("Arbitrary Cypher execution requires a live Neo4j connection")

    async def get_shortest_path(
        self, source_id: str, target_id: str
    ) -> dict[str, Any]:
        if self._neo4j_ok and self._neo4j:
            try:
                results = await self._neo4j.run_query(
                    Q.SHORTEST_PATH_QUERY,
                    {"source_id": source_id, "target_id": target_id},
                )
                if results:
                    r = results[0]
                    return {
                        "found": True,
                        "path_length": r.get("path_length"),
                        "path_nodes": r.get("path_nodes", []),
                        "path_relationships": r.get("path_relationships", []),
                    }
                return {"found": False, "path_length": None, "path_nodes": [], "path_relationships": []}
            except Exception as exc:
                logger.error("Neo4j shortest_path failed: %s — falling back", exc)

        raw = self._mem.shortest_path(source_id, target_id)
        if raw is None:
            return {"found": False, "path_length": None, "path_nodes": [], "path_relationships": []}
        path_nodes = [
            {"id": nid, "labels": self._mem._nodes.get(nid, {}).get("labels", []), "name": None}
            for nid, _ in raw
        ]
        path_rels = [
            {"id": rid, "type": self._mem._rels[rid]["type"],
             "source_id": raw[i][0], "target_id": raw[i + 1][0]}
            for i, (_, rid) in enumerate(raw[:-1])
            if rid and rid in self._mem._rels
        ]
        return {
            "found": True,
            "path_length": len(raw) - 1,
            "path_nodes": path_nodes,
            "path_relationships": path_rels,
        }

    async def get_recommendations(
        self, user_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        if self._neo4j_ok and self._neo4j:
            try:
                return await self._neo4j.run_query(
                    Q.RECOMMENDATION_QUERY, {"user_id": user_id, "limit": limit}
                )
            except Exception as exc:
                logger.error("Neo4j recommendations failed: %s — falling back", exc)

        return self._mem.recommendations(user_id, limit)

    # ─── Statistics ─────────────────────────────────────────────────────────────────

    async def count_nodes_by_label(self) -> list[dict[str, Any]]:
        if self._neo4j_ok and self._neo4j:
            try:
                return await self._neo4j.run_query(Q.COUNT_NODES_BY_LABEL)
            except Exception as exc:
                logger.error("Neo4j count_nodes failed: %s — falling back", exc)
        return self._mem.count_nodes_by_label()

    async def count_rels_by_type(self) -> list[dict[str, Any]]:
        if self._neo4j_ok and self._neo4j:
            try:
                return await self._neo4j.run_query(Q.COUNT_RELS_BY_TYPE)
            except Exception as exc:
                logger.error("Neo4j count_rels failed: %s — falling back", exc)
        return self._mem.count_rels_by_type()

    async def total_nodes(self) -> int:
        counts = await self.count_nodes_by_label()
        return sum(c.get("count", 0) for c in counts)

    async def total_rels(self) -> int:
        counts = await self.count_rels_by_type()
        return sum(c.get("count", 0) for c in counts)

    async def delete_by_scope(self, scope: str) -> int:
        if self._neo4j_ok and self._neo4j:
            try:
                result = await self._neo4j.run_query_single(
                    Q.DELETE_FIXTURES_BY_SCOPE, {"scope": scope}
                )
                return int(result.get("deleted", 0)) if result else 0
            except Exception as exc:
                logger.error("Neo4j delete_by_scope failed: %s — falling back", exc)
        return self._mem.delete_by_scope(scope)


# ─── Result parsers ───────────────────────────────────────────────────────────────


def _neo4j_node_to_dict(node: Any, primary_label: str) -> dict[str, Any]:
    """Normalise a Neo4j node result into a plain dict."""
    if isinstance(node, dict):
        props = node
    else:
        try:
            props = dict(node)
        except Exception:
            props = {}
    return {
        "id": props.get("id", ""),
        "type": primary_label,
        "labels": [primary_label],
        "properties": props,
        "schema_scope": props.get("schema_scope"),
        "created_at": props.get("created_at"),
        "updated_at": props.get("updated_at"),
    }


def _neo4j_rel_to_dict(rel: Any, row: dict[str, Any]) -> dict[str, Any]:
    """Normalise a Neo4j relationship result row into a plain dict."""
    if isinstance(rel, dict):
        props = rel
    else:
        try:
            props = dict(rel)
        except Exception:
            props = {}
    return {
        "id": props.get("id") or row.get("element_id", ""),
        "type": row.get("rel_type", props.get("type", "")),
        "source_id": row.get("source_id", ""),
        "target_id": row.get("target_id", ""),
        "properties": props,
        "created_at": props.get("created_at"),
        "updated_at": props.get("updated_at"),
    }


def _parse_user_context(result: dict[str, Any], user_id: str) -> dict[str, Any]:
    user_raw = result.get("user", {})
    if hasattr(user_raw, "items"):
        user_props = dict(user_raw)
    else:
        user_props = user_raw or {}

    return {
        "user": user_props,
        "goals": _ensure_list(result.get("goals")),
        "tasks": _ensure_list(result.get("tasks")),
        "events": _ensure_list(result.get("events")),
        "insights": _ensure_list(result.get("insights")),
        "milestones": _ensure_list(result.get("milestones")),
        "habits": _ensure_list(result.get("habits")),
        "relationships": [],
        "stats": {
            "goal_count": result.get("goal_count", 0),
            "task_count": result.get("task_count", 0),
            "event_count": result.get("event_count", 0),
            "insight_count": result.get("insight_count", 0),
            "milestone_count": len(_ensure_list(result.get("milestones"))),
            "habit_count": len(_ensure_list(result.get("habits"))),
        },
    }


def _parse_goal_impact(result: dict[str, Any], goal_id: str) -> dict[str, Any]:
    goal_raw = result.get("goal", {})
    goal_props = dict(goal_raw) if hasattr(goal_raw, "items") else goal_raw or {}
    tasks = _ensure_list(result.get("tasks"))
    milestones = _ensure_list(result.get("milestones"))
    sub_goals = _ensure_list(result.get("sub_goals"))
    insights = _ensure_list(result.get("insights"))
    dependent_goals = _ensure_list(result.get("dependent_goals"))
    affected = _ensure_list(result.get("affected_nodes"))
    impact_score = float(
        len(tasks) * 1.0 + len(milestones) * 1.5 + len(sub_goals) * 2.0 + len(affected) * 0.5
    )
    return {
        "goal": goal_props,
        "tasks": tasks,
        "milestones": milestones,
        "sub_goals": sub_goals,
        "insights": insights,
        "owner_ids": _ensure_list(result.get("owner_ids")),
        "dependent_goals": dependent_goals,
        "affected_nodes": affected,
        "impact_score": impact_score,
    }


def _ensure_list(val: Any) -> list[Any]:
    if val is None:
        return []
    if isinstance(val, list):
        return [dict(v) if hasattr(v, "items") else v for v in val if v is not None]
    return [val]


# ─── Module-level singleton ─────────────────────────────────────────────────────────

_graph_service: GraphService | None = None


def get_graph_service() -> GraphService:
    """Return the module-level GraphService singleton."""
    global _graph_service
    if _graph_service is None:
        _graph_service = GraphService()
    return _graph_service
