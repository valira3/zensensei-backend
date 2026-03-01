"""
ZenSensei Graph Query Service - Queries Router

Complex graph traversal and analytics endpoints:
    GET  /graph/user-context/{user_id}          Full user subgraph
    GET  /graph/goal-impact/{goal_id}           Goal impact analysis
    GET  /graph/similar-patterns/{user_id}      Similar behaviour patterns
    GET  /graph/subgraph/{node_id}              Bounded subgraph
    POST /graph/cypher                          Arbitrary Cypher (admin only)
    GET  /graph/path/{source_id}/{target_id}    Shortest path
    GET  /graph/recommendations/{user_id}       Graph-based recommendations
"""

from __future__ import annotations

import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from shared.auth import get_current_user
from shared.models.base import BaseResponse

from services.graph_query_service.schemas import (
    CypherQueryRequest,
    CypherQueryResponse,
    GoalImpactResponse,
    PathNode,
    PathRelationship,
    PathResponse,
    RecommendationEntry,
    RecommendationsResponse,
    SimilarPatternEntry,
    SimilarPatternsResponse,
    SubgraphResponse,
    UserContextResponse,
    UserContextStats,
)
from services.graph_query_service.services.cache_service import CacheService, get_cache_service
from services.graph_query_service.services.graph_service import GraphService, get_graph_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph-queries"])

_MAX_SUBGRAPH_DEPTH = 5


# ─── Dependency helpers ───────────────────────────────────────────────────────


def _graph() -> GraphService:
    return get_graph_service()


def _cache() -> CacheService:
    return get_cache_service()


# ─── User Context ─────────────────────────────────────────────────────────────


@router.get(
    "/user-context/{user_id}",
    response_model=BaseResponse[UserContextResponse],
    summary="Full user graph context: goals, tasks, events, insights, habits",
)
async def get_user_context(
    user_id: str,
    graph: Annotated[GraphService, Depends(_graph)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    refresh: bool = Query(False, description="Bypass cache and force fresh query"),
) -> BaseResponse[UserContextResponse]:
    if not refresh:
        cached = await cache.get_user_context(user_id)
        if cached:
            ctx = UserContextResponse(**cached, cached=True)
            return BaseResponse(data=ctx, message="OK (cached)")

    raw = await graph.get_user_context(user_id)
    stats_raw = raw.get("stats", {})
    ctx = UserContextResponse(
        user_id=user_id,
        user=raw.get("user"),
        goals=raw.get("goals", []),
        tasks=raw.get("tasks", []),
        events=raw.get("events", []),
        insights=raw.get("insights", []),
        milestones=raw.get("milestones", []),
        habits=raw.get("habits", []),
        relationships=[],
        stats=UserContextStats(
            goal_count=stats_raw.get("goal_count", len(raw.get("goals", []))),
            task_count=stats_raw.get("task_count", len(raw.get("tasks", []))),
            event_count=stats_raw.get("event_count", len(raw.get("events", []))),
            insight_count=stats_raw.get("insight_count", len(raw.get("insights", []))),
            milestone_count=stats_raw.get("milestone_count", len(raw.get("milestones", []))),
            habit_count=stats_raw.get("habit_count", len(raw.get("habits", []))),
            relationship_count=len(raw.get("relationships", [])),
        ),
        cached=False,
    )
    await cache.set_user_context(user_id, ctx.model_dump())
    return BaseResponse(data=ctx)


# ─── Goal Impact ──────────────────────────────────────────────────────────────


@router.get(
    "/goal-impact/{goal_id}",
    response_model=BaseResponse[GoalImpactResponse],
    summary="Analyse what a goal affects across the graph",
)
async def get_goal_impact(
    goal_id: str,
    graph: Annotated[GraphService, Depends(_graph)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    refresh: bool = Query(False),
) -> BaseResponse[GoalImpactResponse]:
    if not refresh:
        cached = await cache.get_goal_impact(goal_id)
        if cached:
            return BaseResponse(data=GoalImpactResponse(**cached, cached=True), message="OK (cached)")

    raw = await graph.get_goal_impact(goal_id)
    impact = GoalImpactResponse(
        goal_id=goal_id,
        goal=raw.get("goal"),
        tasks=raw.get("tasks", []),
        milestones=raw.get("milestones", []),
        sub_goals=raw.get("sub_goals", []),
        insights=raw.get("insights", []),
        dependent_goals=raw.get("dependent_goals", []),
        owner_ids=raw.get("owner_ids", []),
        affected_nodes=raw.get("affected_nodes", []),
        impact_score=raw.get("impact_score", 0.0),
        cached=False,
    )
    await cache.set_goal_impact(goal_id, impact.model_dump())
    return BaseResponse(data=impact)


# ─── Similar Patterns ─────────────────────────────────────────────────────────


@router.get(
    "/similar-patterns/{user_id}",
    response_model=BaseResponse[SimilarPatternsResponse],
    summary="Find users with similar goal/task behaviour patterns",
)
async def get_similar_patterns(
    user_id: str,
    graph: Annotated[GraphService, Depends(_graph)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    limit: int = Query(10, ge=1, le=50),
    refresh: bool = Query(False),
) -> BaseResponse[SimilarPatternsResponse]:
    if not refresh:
        cached = await cache.get_similar_patterns(user_id)
        if cached:
            return BaseResponse(
                data=SimilarPatternsResponse(**cached, cached=True), message="OK (cached)"
            )

    raw_patterns = await graph.get_similar_patterns(user_id, limit=limit)
    patterns = [
        SimilarPatternEntry(
            user_id=p.get("user_id", ""),
            display_name=p.get("display_name"),
            shared_categories=int(p.get("shared_categories", 0)),
            shared_goal_count=int(p.get("shared_goal_count", 0)),
            shared_task_pattern_count=int(p.get("shared_task_pattern_count", 0)),
            similarity_score=float(p.get("similarity_score", 0)),
        )
        for p in raw_patterns
    ]
    result = SimilarPatternsResponse(user_id=user_id, patterns=patterns, cached=False)
    await cache.set_similar_patterns(user_id, result.model_dump())
    return BaseResponse(data=result)


# ─── Subgraph ─────────────────────────────────────────────────────────────────


@router.get(
    "/subgraph/{node_id}",
    response_model=BaseResponse[SubgraphResponse],
    summary="Get subgraph up to depth N from a root node",
)
async def get_subgraph(
    node_id: str,
    graph: Annotated[GraphService, Depends(_graph)],
    depth: int = Query(2, ge=1, le=_MAX_SUBGRAPH_DEPTH, description="Traversal depth (max 5)"),
) -> BaseResponse[SubgraphResponse]:
    raw = await graph.get_subgraph(node_id, depth)
    from shared.models.graph import GraphNode, GraphRelationship, NodeType, RelationshipType

    nodes = []
    for n in raw.get("nodes", []):
        try:
            labels = n.get("labels", ["UNKNOWN"])
            node_type_str = labels[0] if labels else "UNKNOWN"
            try:
                ntype = NodeType(node_type_str)
            except ValueError:
                ntype = NodeType.PERSON  # fallback
            props = n.get("properties", {})
            nodes.append(
                GraphNode(
                    id=n.get("id") or props.get("id", ""),
                    type=ntype,
                    properties=props,
                    schema_scope=n.get("schema_scope"),
                )
            )
        except Exception:
            pass

    rels = []
    for r in raw.get("relationships", []):
        try:
            rel_type_str = r.get("type", "KNOWS")
            try:
                rtype = RelationshipType(rel_type_str)
            except ValueError:
                rtype = RelationshipType.KNOWS
            rels.append(
                GraphRelationship(
                    id=r.get("id", ""),
                    type=rtype,
                    source_id=r.get("source_id", ""),
                    target_id=r.get("target_id", ""),
                    properties=r.get("properties", {}),
                )
            )
        except Exception:
            pass

    result = SubgraphResponse(nodes=nodes, relationships=rels)
    return BaseResponse(data=result)


# ─── Cypher (admin only) ──────────────────────────────────────────────────────


@router.post(
    "/cypher",
    response_model=BaseResponse[CypherQueryResponse],
    summary="Execute arbitrary Cypher query (admin role required)",
)
async def run_cypher(
    body: CypherQueryRequest,
    graph: Annotated[GraphService, Depends(_graph)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> BaseResponse[CypherQueryResponse]:
    # Enforce admin role
    roles: list[str] = current_user.get("roles", []) or []
    if "admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to execute arbitrary Cypher",
        )

    t0 = time.perf_counter()
    try:
        records = await graph.run_cypher(body.cypher, body.params, body.database)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cypher execution failed: {exc}")

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    result = CypherQueryResponse(
        records=records,
        row_count=len(records),
        execution_time_ms=elapsed_ms,
    )
    return BaseResponse(data=result)


# ─── Shortest Path ────────────────────────────────────────────────────────────


@router.get(
    "/path/{source_id}/{target_id}",
    response_model=BaseResponse[PathResponse],
    summary="Find shortest path between two nodes (max 6 hops)",
)
async def get_shortest_path(
    source_id: str,
    target_id: str,
    graph: Annotated[GraphService, Depends(_graph)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> BaseResponse[PathResponse]:
    cached = await cache.get_path(source_id, target_id)
    if cached:
        return BaseResponse(data=PathResponse(**cached, cached=True), message="OK (cached)")

    raw = await graph.get_shortest_path(source_id, target_id)
    path_nodes = [
        PathNode(
            id=n.get("id", ""),
            labels=n.get("labels", []),
            name=n.get("name"),
        )
        for n in raw.get("path_nodes", [])
    ]
    path_rels = [
        PathRelationship(
            id=r.get("id"),
            type=r.get("type", ""),
            source_id=r.get("source_id", ""),
            target_id=r.get("target_id", ""),
        )
        for r in raw.get("path_relationships", [])
    ]
    result = PathResponse(
        source_id=source_id,
        target_id=target_id,
        found=raw.get("found", False),
        path_length=raw.get("path_length"),
        path_nodes=path_nodes,
        path_relationships=path_rels,
        cached=False,
    )
    if result.found:
        await cache.set_path(source_id, target_id, result.model_dump())
    return BaseResponse(data=result)


# ─── Recommendations ──────────────────────────────────────────────────────────


@router.get(
    "/recommendations/{user_id}",
    response_model=BaseResponse[RecommendationsResponse],
    summary="Graph-based personalised recommendations for a user",
)
async def get_recommendations(
    user_id: str,
    graph: Annotated[GraphService, Depends(_graph)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    limit: int = Query(10, ge=1, le=50),
    refresh: bool = Query(False),
) -> BaseResponse[RecommendationsResponse]:
    if not refresh:
        cached = await cache.get_recommendations(user_id)
        if cached:
            return BaseResponse(
                data=RecommendationsResponse(**cached, cached=True), message="OK (cached)"
            )

    raw_recs = await graph.get_recommendations(user_id, limit=limit)
    recs = [
        RecommendationEntry(
            id=r.get("id", ""),
            title=r.get("title", ""),
            category=r.get("category"),
            endorsement_count=int(r.get("endorsement_count", 1)),
            supporting_insights=r.get("supporting_insights") or [],
            recommendation_type=r.get("recommendation_type", "goal"),
            score=float(r.get("score", r.get("endorsement_count", 0))),
        )
        for r in raw_recs
    ]
    result = RecommendationsResponse(user_id=user_id, recommendations=recs, cached=False)
    await cache.set_recommendations(user_id, result.model_dump())
    return BaseResponse(data=result)
