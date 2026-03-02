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
    summary="Graph statistics and schema state",
)
async def get_schema_status(
    schema: Annotated[SchemaService, Depends(_schema)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> BaseResponse[SchemaStatusResponse]:
    raw = await schema.get_schema_status()
    label_counts = [
        LabelCount(label=lc["label"], count=lc["count"]) for lc in raw.get("label_counts", [])
    ]
    rel_type_counts = [
        RelTypeCount(type=rt["type"], count=rt["count"])
        for rt in raw.get("rel_type_counts", [])
    ]
    result = SchemaStatusResponse(
        total_nodes=raw.get("total_nodes", 0),
        total_relationships=raw.get("total_relationships", 0),
        label_counts=label_counts,
        rel_type_counts=rel_type_counts,
        indexes=raw.get("indexes", []),
        constraints=raw.get("constraints", []),
    )
    return BaseResponse(data=result)


@router.post(
    "/seed",
    response_model=BaseResponse[SeedDataResponse],
    summary="Seed sample data into the graph",
)
async def seed_data(
    schema: Annotated[SchemaService, Depends(_schema)],
    cache: Annotated[CacheService, Depends(_cache)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> BaseResponse[SeedDataResponse]:
    raw = await schema.seed_data()
    await cache.invalidate_entity("schema")
    result = SeedDataResponse(**raw)
    return BaseResponse(data=result, message="Sample data seeded")


@router.delete(
    "/fixtures/{scope}",
    response_model=BaseResponse[FixtureDeleteResponse],
    summary="Delete fixtures by scope tag",
)
async def delete_fixtures(
    scope: str = Path(..., description="Fixture scope tag to delete"),
    schema: Annotated[SchemaService, Depends(_schema)] = ...,  # type: ignore[assignment]
    cache: Annotated[CacheService, Depends(_cache)] = ...,  # type: ignore[assignment]
    current_user: Annotated[dict[str, Any], Depends(get_current_user)] = ...,  # type: ignore[assignment]
) -> BaseResponse[FixtureDeleteResponse]:
    raw = await schema.delete_fixtures(scope)
    await cache.invalidate_entity("schema")
    result = FixtureDeleteResponse(**raw)
    return BaseResponse(data=result, message=f"Fixtures deleted for scope '{scope}'")
