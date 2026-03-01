"""
ZenSensei AI Reasoning Service - Decisions Router

Endpoints
---------
POST /decisions/analyze            Analyze a decision (multi-factor)
GET  /decisions/{user_id}/history  Past decision analyses
POST /decisions/compare            Compare multiple options side by side
"""

from __future__ import annotations

from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, Query, status

from services.ai_reasoning_service.schemas import (
    DecisionAnalysis,
    DecisionCompareRequest,
    DecisionCompareResponse,
    DecisionContext,
    DecisionHistoryResponse,
)
from services.ai_reasoning_service.services.decision_analyzer import DecisionAnalyzer
from services.ai_reasoning_service.services.llm_client import LLMClient

logger = structlog.get_logger(__name__)
router = APIRouter()

_shared_llm = LLMClient()
_shared_analyzer = DecisionAnalyzer(llm_client=_shared_llm)


def get_decision_analyzer() -> DecisionAnalyzer:
    return _shared_analyzer


@router.post("/analyze", response_model=DecisionAnalysis, status_code=status.HTTP_201_CREATED, summary="Analyze a decision")
async def analyze_decision(decision_context: DecisionContext, analyzer: DecisionAnalyzer = Depends(get_decision_analyzer)) -> DecisionAnalysis:
    return await analyzer.analyze_decision(user_id=decision_context.user_id, decision_context=decision_context)


@router.get("/{user_id}/history", response_model=DecisionHistoryResponse, summary="Past decision analyses")
async def get_decision_history(user_id: str, page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 20, analyzer: DecisionAnalyzer = Depends(get_decision_analyzer)) -> DecisionHistoryResponse:
    offset = (page - 1) * page_size
    items, total = await analyzer.get_history(user_id=user_id, limit=page_size, offset=offset)
    return DecisionHistoryResponse(user_id=user_id, analyses=items, total=total)


@router.post("/compare", response_model=DecisionCompareResponse, status_code=status.HTTP_201_CREATED, summary="Compare multiple options side by side")
async def compare_options(request: DecisionCompareRequest, analyzer: DecisionAnalyzer = Depends(get_decision_analyzer)) -> DecisionCompareResponse:
    return await analyzer.compare_options(request)
