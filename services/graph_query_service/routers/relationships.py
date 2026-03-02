"""
ZenSensei Graph Query Service - Relationships Router

Endpoints:
    POST   /relationships                       Create relationship
    GET    /relationships/{rel_id}              Get relationship
    PUT    /relationships/{rel_id}              Update relationship
    DELETE /relationships/{rel_id}              Delete relationship
    GET    /nodes/{node_id}/relationships       All relationships for a node
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_user
from shared.models.base import BaseResponse

from services.graph_query_service.schemas import (
    NodeRelationshipsResponse,
    RelationshipCreateRequest,
    RelationshipResponse,
    RelationshipUpdateRequest,
)
from services.graph_query_service.services.cache_service import CacheService, get_cache_service
from services.graph_query_service.services.graph_service import GraphService, get_graph_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["relationships"])


# ─── Dependency helpers ───────────────────────────────────────────────────────


def _graph() -> GraphService:
    return get_graph_service()


def _cache() -> CacheService:
    return get_cache_service()


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _raw_to_rel_response(raw: dict[str, Any]) -> RelationshipResponse:
    return RelationshipResponse(
        id=raw.get("id", ""),
        type=raw.get("type", ""),
        source_id=raw.get("source_id", ""),
        target_id=raw.get("target_id", ""),
        properties=raw.get("properties", {}),
        created_at=raw.get("created_at"),
        updated_at=raw.get("updated_at"),
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post(
    "/relationships",
    status_code=status.HTTP_201_CREATED,
    response_model=BaseResponse[RelationshipResponse],
    summary="Create a relationship between two nodes",
)
async def create_relationship(
    body: RelationshipCreateRequest,
    graph: Annotated[GraphService, Depends(_graph)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> ORJSONResponse:
    raw = await graph.create_relationship(
        source_id=body.source_id,
        target_id=body.target_id,
        rel_type=body.type,
        properties=body.properties,
    )
    if raw is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"One or both nodes not found: source='{body.source_id}', "
                f"target='{body.target_id}'"
            ),
        )

    await cache.invalidate_entity("relationship")
    rel = _raw_to_rel_response(raw)
    return ORJSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=BaseResponse(data=rel, message="Relationship created").model_dump(),
    )


@router.get(
    "/relationships/{rel_id}",
    response_model=BaseResponse[RelationshipResponse],
    summary="Get a relationship by ID",
)
async def get_relationship(
    rel_id: str,
    graph: Annotated[GraphService, Depends(_graph)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> BaseResponse[RelationshipResponse]:
    raw = await graph.get_relationship(rel_id)
    if raw is None:
        raise HTTPException(status_code=404, detail=f"Relationship '{rel_id}' not found")
    return BaseResponse(data=_raw_to_rel_response(raw))


@router.put(
    "/relationships/{rel_id}",
    response_model=BaseResponse[RelationshipResponse],
    summary="Update relationship properties",
)
async def update_relationship(
    rel_id: str,
    body: RelationshipUpdateRequest,
    graph: Annotated[GraphService, Depends(_graph)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> BaseResponse[RelationshipResponse]:
    raw = await graph.update_relationship(rel_id, body.properties)
    if raw is None:
        raise HTTPException(status_code=404, detail=f"Relationship '{rel_id}' not found")

    await cache.invalidate_entity("relationship", rel_id)
    return BaseResponse(data=_raw_to_rel_response(raw), message="Relationship updated")


@router.delete(
    "/relationships/{rel_id}",
    response_model=BaseResponse[dict[str, Any]],
    summary="Delete a relationship",
)
async def delete_relationship(
    rel_id: str,
    graph: Annotated[GraphService, Depends(_graph)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> BaseResponse[dict[str, Any]]:
    deleted = await graph.delete_relationship(rel_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"Relationship '{rel_id}' not found")

    await cache.invalidate_entity("relationship", rel_id)
    return BaseResponse(data={"rel_id": rel_id, "deleted": deleted}, message="Relationship deleted")


@router.get(
    "/nodes/{node_id}/relationships",
    response_model=BaseResponse[NodeRelationshipsResponse],
    summary="Get all relationships for a node",
)
async def get_node_relationships(
    node_id: str,
    graph: Annotated[GraphService, Depends(_graph)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    direction: Literal["BOTH", "IN", "OUT"] = Query(
        default="BOTH",
        description="Relationship direction relative to the node",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> BaseResponse[NodeRelationshipsResponse]:
    skip = (page - 1) * page_size
    raw_rels = await graph.get_node_relationships(
        node_id=node_id,
        direction=direction,
        skip=skip,
        limit=page_size,
    )
    rels = [_raw_to_rel_response(r) for r in raw_rels]
    result = NodeRelationshipsResponse(
        node_id=node_id,
        relationships=rels,
        total=len(rels),
    )
    return BaseResponse(data=result)
