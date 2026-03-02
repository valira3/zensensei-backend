"""
ZenSensei Graph Query Service - Nodes Router

Endpoints:
    POST   /nodes                 Create a graph node
    GET    /nodes/types           List all node types with counts
    GET    /nodes/search          Search nodes by type, properties, full-text
    GET    /nodes/{node_id}       Get node by ID
    PUT    /nodes/{node_id}       Update node properties
    DELETE /nodes/{node_id}       Delete node

Note: /nodes/types and /nodes/search must be declared BEFORE /nodes/{node_id}
to avoid the path parameter swallowing those literal path segments.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_user
from shared.models.base import BaseResponse

from services.graph_query_service.schemas import (
    NodeCreateRequest,
    NodeListResponse,
    NodeResponse,
    NodeTypeListResponse,
    NodeUpdateRequest,
)
from services.graph_query_service.services.cache_service import CacheService, get_cache_service
from services.graph_query_service.services.graph_service import GraphService, get_graph_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nodes", tags=["nodes"])


# ─── Dependency helpers ───────────────────────────────────────────────────────


def _graph() -> GraphService:
    return get_graph_service()


def _cache() -> CacheService:
    return get_cache_service()


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _raw_to_node_response(raw: dict[str, Any]) -> NodeResponse:
    return NodeResponse(
        id=raw.get("id", ""),
        type=raw.get("type", raw.get("labels", ["UNKNOWN"])[0] if raw.get("labels") else "UNKNOWN"),
        labels=raw.get("labels", []),
        properties=raw.get("properties", {}),
        schema_scope=raw.get("schema_scope"),
        created_at=raw.get("created_at"),
        updated_at=raw.get("updated_at"),
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=BaseResponse[NodeResponse],
    summary="Create a graph node",
)
async def create_node(
    body: NodeCreateRequest,
    graph: Annotated[GraphService, Depends(_graph)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> ORJSONResponse:
    raw = await graph.create_node(
        node_type=body.type,
        properties=body.properties,
        schema_scope=body.schema_scope,
    )
    if raw is None:
        raise HTTPException(status_code=500, detail="Failed to create node")

    await cache.invalidate_entity("node")
    node = _raw_to_node_response(raw)
    return ORJSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=BaseResponse(data=node, message="Node created").model_dump(),
    )


@router.get(
    "/types",
    response_model=BaseResponse[NodeTypeListResponse],
    summary="List all node types with counts",
)
async def list_node_types(
    graph: Annotated[GraphService, Depends(_graph)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> BaseResponse[NodeTypeListResponse]:
    cached = await cache.get_node_types()
    if cached:
        return BaseResponse(data=NodeTypeListResponse(**cached), message="OK (cached)")

    types_raw = await graph.list_node_types()
    total = sum(t.get("count", 0) for t in types_raw)
    result = NodeTypeListResponse(types=types_raw, total_nodes=total)  # type: ignore[arg-type]
    await cache.set_node_types(result.model_dump())
    return BaseResponse(data=result)


@router.get(
    "/search",
    response_model=BaseResponse[NodeListResponse],
    summary="Search nodes by type, properties, and/or full-text",
)
async def search_nodes(
    graph: Annotated[GraphService, Depends(_graph)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    node_type: Optional[str] = Query(None, description="Filter by node label"),
    full_text: Optional[str] = Query(None, description="Full-text search query"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=200, description="Items per page"),
) -> BaseResponse[NodeListResponse]:
    skip = (page - 1) * page_size
    nodes_raw = await graph.search_nodes(
        node_type=node_type,
        full_text=full_text,
        skip=skip,
        limit=page_size,
    )
    items = [_raw_to_node_response(n) for n in nodes_raw]
    result = NodeListResponse(items=items, total=len(items), page=page, page_size=page_size)
    return BaseResponse(data=result)


@router.get(
    "/{node_id}",
    response_model=BaseResponse[NodeResponse],
    summary="Get a node by ID",
)
async def get_node(
    node_id: str,
    graph: Annotated[GraphService, Depends(_graph)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> BaseResponse[NodeResponse]:
    raw = await graph.get_node(node_id)
    if raw is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    return BaseResponse(data=_raw_to_node_response(raw))


@router.put(
    "/{node_id}",
    response_model=BaseResponse[NodeResponse],
    summary="Update node properties",
)
async def update_node(
    node_id: str,
    body: NodeUpdateRequest,
    graph: Annotated[GraphService, Depends(_graph)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> BaseResponse[NodeResponse]:
    raw = await graph.update_node(node_id, body.properties)
    if raw is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

    await cache.invalidate_entity("node", node_id)
    # Invalidate user context if this node is a PERSON or GOAL
    node_type = raw.get("type", "")
    if node_type in ("PERSON",):
        await cache.invalidate_user(node_id)
    elif node_type in ("GOAL",):
        await cache.invalidate_entity("goal", node_id)

    return BaseResponse(data=_raw_to_node_response(raw), message="Node updated")


@router.delete(
    "/{node_id}",
    status_code=status.HTTP_200_OK,
    response_model=BaseResponse[dict[str, Any]],
    summary="Delete a node (cascades relationships)",
)
async def delete_node(
    node_id: str,
    graph: Annotated[GraphService, Depends(_graph)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> BaseResponse[dict[str, Any]]:
    deleted = await graph.delete_node(node_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

    await cache.invalidate_entity("node", node_id)
    await cache.invalidate_entity("relationship")
    return BaseResponse(data={"node_id": node_id, "deleted": deleted}, message="Node deleted")
