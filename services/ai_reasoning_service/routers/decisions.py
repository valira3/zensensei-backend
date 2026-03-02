"""
ZenSensei AI Reasoning Service - Decisions Router

Endpoints
---------
POST /decisions/analyze            Analyze a decision (multi-factor)
GET  /decisions/{user_id}/history  Past decision analyses
POST /decisions/compare            Compare multiple options side by side
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_user
from shared.models.base import BaseResponse

from services.ai_reasoning_service.schemas import (
    DecisionAnalysisRequest,
    DecisionAnalysisResponse,
    DecisionCompareRequest,
    DecisionCompareResponse,
    DecisionHistoryResponse,
)
from services.ai_reasoning_service.services.reasoning_service import (
    ReasoningService,
    get_reasoning_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/decisions", tags=["decisions"])


# ─── Dependency helpers ───────────────────────────────────────────────────────


def _svc() -> ReasoningService:
    return get_reasoning_service()


CurrentUser = Annotated[dict, Depends(get_current_user)]
Svc = Annotated[ReasoningService, Depends(_svc)]


# ─── Routes ─────────────────────────────────────────────────────────────────


@router.post("/analyze", response_class=ORJSONResponse, status_code=status.HTTP_200_OK)
async def analyze_decision(
    payload: DecisionAnalysisRequest,
    current_user: CurrentUser,
    svc: Svc,
) -> ORJSONResponse:
    """Analyze a multi-factor decision for the authenticated user."""
    result: DecisionAnalysisResponse = await svc.analyze_decision(
        user_id=current_user["uid"],
        payload=payload,
    )
    return ORJSONResponse(BaseResponse(data=result.model_dump()).model_dump())


@router.get(
    "/{user_id}/history",
    response_class=ORJSONResponse,
    status_code=status.HTTP_200_OK,
)
async def get_decision_history(
    user_id: str,
    current_user: CurrentUser,
    svc: Svc,
) -> ORJSONResponse:
    """Return past decision analyses. Users can only access their own history."""
    if current_user["uid"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    history: DecisionHistoryResponse = await svc.get_decision_history(user_id=user_id)
    return ORJSONResponse(BaseResponse(data=history.model_dump()).model_dump())


@router.post("/compare", response_class=ORJSONResponse, status_code=status.HTTP_200_OK)
async def compare_decisions(
    payload: DecisionCompareRequest,
    current_user: CurrentUser,
    svc: Svc,
) -> ORJSONResponse:
    """Compare multiple decision options for the authenticated user."""
    result: DecisionCompareResponse = await svc.compare_decisions(
        user_id=current_user["uid"],
        payload=payload,
    )
    return ORJSONResponse(BaseResponse(data=result.model_dump()).model_dump())
