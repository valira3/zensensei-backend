"""
ZenSensei AI Reasoning Service - Recommendations Router

Endpoints
---------
GET  /recommendations/{user_id}               Personalised action recommendations
GET  /recommendations/{user_id}/goals         Goal-specific recommendations
GET  /recommendations/{user_id}/relationships Relationship nudges
POST /recommendations/{user_id}/feedback      Submit recommendation feedback
"""

from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_user
from shared.models.base import BaseResponse

from services.ai_reasoning_service.schemas import (
    RecommendationFeedbackRequest,
    RecommendationListResponse,
)
from services.ai_reasoning_service.services.reasoning_service import (
    ReasoningService,
    get_reasoning_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


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


@router.get(
    "/{user_id}",
    response_class=ORJSONResponse,
    status_code=status.HTTP_200_OK,
)
async def get_recommendations(
    user_id: str,
    current_user: CurrentUser,
    svc: Svc,
    limit: Optional[int] = Query(10, ge=1, le=50),
    category: Optional[str] = Query(None),
) -> ORJSONResponse:
    """Return personalised recommendations. Only accessible by the target user."""
    _assert_owns(current_user, user_id)
    result: RecommendationListResponse = await svc.get_recommendations(
        user_id=user_id,
        limit=limit or 10,
        category=category,
    )
    return ORJSONResponse(BaseResponse(data=result.model_dump()).model_dump())


@router.get(
    "/{user_id}/goals",
    response_class=ORJSONResponse,
    status_code=status.HTTP_200_OK,
)
async def get_goal_recommendations(
    user_id: str,
    current_user: CurrentUser,
    svc: Svc,
    goal_id: Optional[str] = Query(None),
) -> ORJSONResponse:
    """Return goal-specific recommendations. Only accessible by the target user."""
    _assert_owns(current_user, user_id)
    result: RecommendationListResponse = await svc.get_goal_recommendations(
        user_id=user_id,
        goal_id=goal_id,
    )
    return ORJSONResponse(BaseResponse(data=result.model_dump()).model_dump())


@router.get(
    "/{user_id}/relationships",
    response_class=ORJSONResponse,
    status_code=status.HTTP_200_OK,
)
async def get_relationship_recommendations(
    user_id: str,
    current_user: CurrentUser,
    svc: Svc,
) -> ORJSONResponse:
    """Return relationship nudges. Only accessible by the target user."""
    _assert_owns(current_user, user_id)
    result: RecommendationListResponse = await svc.get_relationship_recommendations(
        user_id=user_id,
    )
    return ORJSONResponse(BaseResponse(data=result.model_dump()).model_dump())


@router.post(
    "/{user_id}/feedback",
    response_class=ORJSONResponse,
    status_code=status.HTTP_200_OK,
)
async def submit_feedback(
    user_id: str,
    payload: RecommendationFeedbackRequest,
    current_user: CurrentUser,
    svc: Svc,
) -> ORJSONResponse:
    """Submit feedback on a recommendation. Only accessible by the target user."""
    _assert_owns(current_user, user_id)
    await svc.submit_recommendation_feedback(
        user_id=user_id,
        payload=payload,
    )
    return ORJSONResponse(BaseResponse(data={"accepted": True}).model_dump())
