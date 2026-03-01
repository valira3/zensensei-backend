"""
ZenSensei AI Reasoning Service - Recommendations Router

Endpoints
---------
GET  /recommendations/{user_id}               Personalised action recommendations
GET  /recommendations/{user_id}/goals         Goal-specific recommendations
GET  /recommendations/{user_id}/relationships Relationship nurture suggestions
GET  /recommendations/{user_id}/wellness      Wellness recommendations
POST /recommendations/{rec_id}/act            Mark recommendation as acted upon
"""

from __future__ import annotations

from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, Query, status

from services.ai_reasoning_service.schemas import (
    ActOnRecommendationRequest,
    ActOnRecommendationResponse,
    RecommendationResponse,
)
from services.ai_reasoning_service.services.llm_client import LLMClient
from services.ai_reasoning_service.services.recommendation_engine import (
    RecommendationEngine,
)

logger = structlog.get_logger(__name__)

router = APIRouter()

# ─── Dependency injection ───────────────────────────────────────────────────────────────

_shared_llm = LLMClient()
_shared_rec_engine = RecommendationEngine(llm_client=_shared_llm)


def get_rec_engine() -> RecommendationEngine:
    return _shared_rec_engine


# ─── Routes ─────────────────────────────────────────────────────────────────────


@router.get(
    "/{user_id}",
    response_model=RecommendationResponse,
    summary="Get personalised action recommendations",
    description=(
        "Returns a prioritised list of personalised recommendations across all "
        "life areas (goals, relationships, wellness, habits, finances) based on "
        "the user's knowledge graph and historical patterns."
    ),
)
async def get_recommendations(
    user_id: str,
    count: Annotated[int, Query(ge=1, le=20, description="Number of recommendations")] = 5,
    engine: RecommendationEngine = Depends(get_rec_engine),
) -> RecommendationResponse:
    return await engine.generate_recommendations(
        user_id=user_id, focus_area="ALL", count=count
    )


@router.get(
    "/{user_id}/goals",
    response_model=RecommendationResponse,
    summary="Goal-specific recommendations",
    description=(
        "Returns recommendations focused on goal progress, blockers, "
        "upcoming deadlines, and stalled objectives."
    ),
)
async def get_goal_recommendations(
    user_id: str,
    engine: RecommendationEngine = Depends(get_rec_engine),
) -> RecommendationResponse:
    return await engine.goal_recommendations(user_id=user_id)


@router.get(
    "/{user_id}/relationships",
    response_model=RecommendationResponse,
    summary="Relationship nurture suggestions",
    description=(
        "Returns suggestions for who to reach out to and why, "
        "sorted by days since last meaningful interaction."
    ),
)
async def get_relationship_recommendations(
    user_id: str,
    engine: RecommendationEngine = Depends(get_rec_engine),
) -> RecommendationResponse:
    return await engine.relationship_recommendations(user_id=user_id)


@router.get(
    "/{user_id}/wellness",
    response_model=RecommendationResponse,
    summary="Wellness recommendations",
    description=(
        "Returns health and balance recommendations based on habit tracking, "
        "behavioural patterns, and identified energy-dip periods."
    ),
)
async def get_wellness_recommendations(
    user_id: str,
    engine: RecommendationEngine = Depends(get_rec_engine),
) -> RecommendationResponse:
    return await engine.wellness_recommendations(user_id=user_id)


@router.post(
    "/{rec_id}/act",
    response_model=ActOnRecommendationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mark recommendation as acted upon",
    description=(
        "Records that the user has acted on a specific recommendation. "
        "Updates the recommendation's status to acted and timestamps the action."
    ),
)
async def act_on_recommendation(
    rec_id: str,
    request: ActOnRecommendationRequest,
    engine: RecommendationEngine = Depends(get_rec_engine),
) -> ActOnRecommendationResponse:
    await engine.mark_acted(rec_id=rec_id, notes=request.notes)
    return ActOnRecommendationResponse(rec_id=rec_id)
