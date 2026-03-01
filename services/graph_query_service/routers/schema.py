"""
ZenSensei Graph Query Service - Schema Router

Endpoints:
    POST   /schema/init                 Initialize indexes and constraints
    GET    /schema/status               Graph statistics and schema state
    POST   /schema/seed                 Seed sample data
    DELETE /schema/fixtures/{scope}     Delete fixtures by scope tag
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, status

from shared.auth import get_current_user
from shared.models.base import BaseResponse

from services.graph_query_service.schemas import (
    FixtureDeleteResponse,
    LabelCount,
    RelTypeCount,
    SchemaInitResponse,
    SchemaStatusResponse,
    SeedDataResponse,
)
from services.graph_query_service.services.cache_service import CacheService, get_cache_service
from services.graph_query_service.services.schema_service import SchemaService, get_schema_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schema", tags=["schema"])


# ─── Dependency helpers ───────────────────────────────────────────────────────


def _schema() -> SchemaService:
    return get_schema_service()


def _cache() -> CacheService:
    return get_cache_service()


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post(
    "/init",
    response_model=BaseResponse[SchemaInitResponse],
    summary="Initialize graph schema: create indexes and uniqueness constraints",
)
async def init_schema(
    schema: Annotated[SchemaService, Depends(_schema)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> BaseResponse[SchemaInitResponse]:
    raw = await schema.initialize_schema()
    await cache.invalidate_entity("schema")
    result = SchemaInitResponse(**raw)
    return BaseResponse(data=result, message="Schema initialized")


@router.get(
    "/status",
    response_model=BaseResponse[SchemaStatusResponse],
    summary="Get graph statistics and schema state",
)
async def get_schema_status(
    schema: Annotated[SchemaService, Depends(_schema)],
    cache: Annotated[CacheService, Depends(_cache)],
) -> BaseResponse[SchemaStatusResponse]:
    cached = await cache.get_schema_status()
    if cached:
        return BaseResponse(data=SchemaStatusResponse(**cached), message="OK (cached)")

    raw = await schema.get_status()

    node_counts = [
        LabelCount(label=c.get("label", c.get("type", "")), count=int(c.get("count", 0)))
        for c in raw.get("node_counts", [])
    ]
    rel_counts = [
        RelTypeCount(type=c.get("type", ""), count=int(c.get("count", 0)))
        for c in raw.get("relationship_counts", [])
    ]
    result = SchemaStatusResponse(
        node_counts=node_counts,
        relationship_counts=rel_counts,
        total_nodes=raw.get("total_nodes", 0),
        total_relationships=raw.get("total_relationships", 0),
        indexes_initialized=raw.get("indexes_initialized", False),
        constraints_initialized=raw.get("constraints_initialized", False),
    )
    await cache.set_schema_status(result.model_dump())
    return BaseResponse(data=result)


@router.post(
    "/seed",
    status_code=status.HTTP_201_CREATED,
    response_model=BaseResponse[SeedDataResponse],
    summary="Seed comprehensive sample data (all 10 node types)",
)
async def seed_data(
    schema: Annotated[SchemaService, Depends(_schema)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> BaseResponse[SeedDataResponse]:
    raw = await schema.seed_sample_data()
    # Bust all caches after seeding
    await cache.invalidate_entity("node")
    await cache.invalidate_entity("relationship")
    await cache.invalidate_entity("schema")
    result = SeedDataResponse(**raw)
    return BaseResponse(
        data=result,
        message=f"Seeded {result.nodes_created} nodes and {result.relationships_created} relationships",
    )


@router.delete(
    "/fixtures/{scope:path}",
    response_model=BaseResponse[FixtureDeleteResponse],
    summary="Delete all fixture nodes tagged with the given scope",
)
async def delete_fixtures(
    scope: Annotated[str, Path(
        description="Scope tag used during seeding, e.g. 'fixtures:demo'",
        min_length=1,
        max_length=256,
    )],
    schema: Annotated[SchemaService, Depends(_schema)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> BaseResponse[FixtureDeleteResponse]:
    raw = await schema.delete_fixtures(scope)
    await cache.invalidate_entity("node")
    await cache.invalidate_entity("relationship")
    await cache.invalidate_entity("schema")
    result = FixtureDeleteResponse(**raw)
    return BaseResponse(data=result, message=f"Deleted {result.deleted} nodes with scope '{scope}'")
