"""
ZenSensei AI Reasoning Service - Insights Router

Endpoints
---------
POST /insights/generate/{user_id}       Generate daily insights for user
GET  /insights/{user_id}                Get user's recent insights (cached/stored)
GET  /insights/{user_id}/{insight_id}   Get a specific insight
POST /insights/{user_id}/{insight_id}/dismiss   Dismiss an insight
POST /insights/{user_id}/{insight_id}/act       Mark insight as acted upon
"""

from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_user
from shared.models.base import BaseResponse

from services.ai_reasoning_service.schemas import (
    InsightActionRequest,
    InsightGenerateRequest,
    InsightListResponse,
    InsightResponse,
)
from services.ai_reasoning_service.services.reasoning_service import (
    ReasoningService,
    get_reasoning_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/insights", tags=["insights"])


# ─── Dependency helpers ───────────────────────────────────────────────────────


def _svc() -> ReasoningService:
    return get_reasoning_service()


CurrentUser = Annotated[dict, Depends(get_current_user)]
Svc = Annotated[ReasoningService, Depends(_svc)]


# ─── Ownership guard ───────────────────────────────────────────────────────────


def _assert_owns(current_user: dict, user_id: str) -> None:
    """Raise 403 if the authenticated user is not the resource owner."""
    if current_user["uid"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )


# ─── Routes ─────────────────────────────────────────────────────────────────


@router.post(
    "/generate/{user_id}",
    response_class=ORJSONResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_insights(
    user_id: str,
    payload: InsightGenerateRequest,
    current_user: CurrentUser,
    svc: Svc,
) -> ORJSONResponse:
    """Trigger insight generation for a user. Only accessible by that user."""
    _assert_owns(current_user, user_id)
    insights: InsightListResponse = await svc.generate_insights(
        user_id=user_id,
        payload=payload,
    )
    return ORJSONResponse(
        BaseResponse(data=insights.model_dump()).model_dump(),
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "/{user_id}",
    response_class=ORJSONResponse,
    status_code=status.HTTP_200_OK,
)
async def list_insights(
    user_id: str,
    current_user: CurrentUser,
    svc: Svc,
    limit: Optional[int] = Query(20, ge=1, le=100),
    offset: Optional[int] = Query(0, ge=0),
    insight_type: Optional[str] = Query(None),
) -> ORJSONResponse:
    """List recent insights for a user. Only accessible by that user."""
    _assert_owns(current_user, user_id)
    result: InsightListResponse = await svc.list_insights(
        user_id=user_id,
        limit=limit or 20,
        offset=offset or 0,
        insight_type=insight_type,
    )
    return ORJSONResponse(BaseResponse(data=result.model_dump()).model_dump())


@router.get(
    "/{user_id}/{insight_id}",
    response_class=ORJSONResponse,
    status_code=status.HTTP_200_OK,
)
async def get_insight(
    user_id: str,
    insight_id: str,
    current_user: CurrentUser,
    svc: Svc,
) -> ORJSONResponse:
    """Get a specific insight. Only accessible by the owning user."""
    _assert_owns(current_user, user_id)
    insight: InsightResponse = await svc.get_insight(
        user_id=user_id,
        insight_id=insight_id,
    )
    return ORJSONResponse(BaseResponse(data=insight.model_dump()).model_dump())


@router.post(
    "/{user_id}/{insight_id}/dismiss",
    response_class=ORJSONResponse,
    status_code=status.HTTP_200_OK,
)
async def dismiss_insight(
    user_id: str,
    insight_id: str,
    current_user: CurrentUser,
    svc: Svc,
) -> ORJSONResponse:
    """Dismiss an insight. Only accessible by the owning user."""
    _assert_owns(current_user, user_id)
    result: InsightResponse = await svc.dismiss_insight(
        user_id=user_id,
        insight_id=insight_id,
    )
    return ORJSONResponse(BaseResponse(data=result.model_dump()).model_dump())


@router.post(
    "/{user_id}/{insight_id}/act",
    response_class=ORJSONResponse,
    status_code=status.HTTP_200_OK,
)
async def act_on_insight(
    user_id: str,
    insight_id: str,
    payload: InsightActionRequest,
    current_user: CurrentUser,
    svc: Svc,
) -> ORJSONResponse:
    """Mark an insight as acted upon. Only accessible by the owning user."""
    _assert_owns(current_user, user_id)
    result: InsightResponse = await svc.act_on_insight(
        user_id=user_id,
        insight_id=insight_id,
        payload=payload,
    )
    return ORJSONResponse(BaseResponse(data=result.model_dump()).model_dump())
