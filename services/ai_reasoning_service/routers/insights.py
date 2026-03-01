"""
ZenSensei AI Reasoning Service - Insights Router

Endpoints
---------
POST /insights/generate/{user_id}       Generate daily insights for user
GET  /insights/{user_id}                Get user's recent insights (cached/stored)
GET  /insights/{user_id}/{insight_id}   Get a specific insight
POST /insights/{insight_id}/feedback    Record user feedback
GET  /insights/summary/{user_id}        Daily summary with priorities
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.ai_reasoning_service.schemas import (
    DailySummaryResponse,
    FeedbackRequest,
    FeedbackResponse,
    InsightDetailResponse,
    InsightGenerateRequest,
    InsightGenerateResponse,
    InsightItem,
    InsightListResponse,
)
from services.ai_reasoning_service.services.insight_engine import InsightEngine
from services.ai_reasoning_service.services.llm_client import LLMClient
from shared.models.insights import InsightType

logger = structlog.get_logger(__name__)

router = APIRouter()

# ─── Dependency injection ─────────────────────────────────────────────────────

_shared_llm = LLMClient()
_shared_engine = InsightEngine(llm_client=_shared_llm)


def get_insight_engine() -> InsightEngine:
    return _shared_engine


# ─── In-memory stores (replace with Firestore in production) ──────────────────
# Maps user_id → list[InsightItem]
_insight_store: dict[str, list[InsightItem]] = {}
# Maps insight_id → list[feedback dict]
_feedback_store: dict[str, list[dict]] = {}


# ─── Routes ───────────────────────────────────────────────────────────────────


@router.post(
    "/generate/{user_id}",
    response_model=InsightGenerateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate daily insights",
    description=(
        "Runs the full insight generation pipeline for the given user: "
        "fetches graph context, loads historical patterns, generates embeddings, "
        "and calls Gemini to produce 3–5 structured insights."
    ),
)
async def generate_insights(
    user_id: str,
    request: InsightGenerateRequest,
    engine: InsightEngine = Depends(get_insight_engine),
) -> InsightGenerateResponse:
    import time

    start = time.perf_counter()

    insights = await engine.generate_daily_insights(
        user_id=user_id,
        max_insights=request.max_insights,
        focus_areas=request.focus_areas if request.focus_areas else None,
    )

    # Persist to store (most-recent at front)
    _insight_store.setdefault(user_id, [])
    if request.force_refresh:
        _insight_store[user_id] = insights + _insight_store[user_id]
    else:
        # Deduplicate: drop previously stored insights for today and add new ones
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        existing = [
            i for i in _insight_store[user_id]
            if i.generated_at.strftime("%Y-%m-%d") != today
        ]
        _insight_store[user_id] = insights + existing

    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    return InsightGenerateResponse(
        user_id=user_id,
        insights=insights,
        model_used=engine._llm._primary_model,
        from_cache=False,
        generation_duration_ms=duration_ms,
    )


@router.get(
    "/summary/{user_id}",
    response_model=DailySummaryResponse,
    summary="Daily summary with priorities",
    description=(
        "Returns a structured daily summary grouping insights by type "
        "and providing a narrative paragraph for the day."
    ),
)
async def get_daily_summary(
    user_id: str,
    engine: InsightEngine = Depends(get_insight_engine),
) -> DailySummaryResponse:
    # Generate fresh insights if none exist for today
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    stored = _insight_store.get(user_id, [])
    today_insights = [i for i in stored if i.generated_at.strftime("%Y-%m-%d") == today]

    if not today_insights:
        today_insights = await engine.generate_daily_insights(
            user_id=user_id, max_insights=5
        )
        _insight_store.setdefault(user_id, [])
        _insight_store[user_id] = today_insights + _insight_store[user_id]

    # Partition by type
    priorities = [i for i in today_insights if i.insight_type == InsightType.PRIORITY]
    relationship_nudges = [i for i in today_insights if i.insight_type == InsightType.RELATIONSHIP]
    risk_alerts = [i for i in today_insights if i.insight_type == InsightType.RISK]
    patterns = [i for i in today_insights if i.insight_type == InsightType.PATTERN]
    goal_insights = [i for i in today_insights if i.insight_type == InsightType.GOAL_PROGRESS]

    # Build narrative summary
    high_count = sum(1 for i in today_insights if i.impact == "HIGH")
    top_title = priorities[0].title if priorities else (today_insights[0].title if today_insights else "")
    narrative = (
        f"Today you have {len(today_insights)} insights to review. "
        f"{high_count} are high-impact. "
        f"{'Top priority: ' + top_title + '. ' if top_title else ''}"
        f"{len(relationship_nudges)} relationship nudge(s) and "
        f"{len(risk_alerts)} risk alert(s) require attention."
    )

    return DailySummaryResponse(
        user_id=user_id,
        date=today,
        top_priorities=priorities[:3],
        relationship_nudges=relationship_nudges[:3],
        risk_alerts=risk_alerts[:3],
        pattern_observations=patterns[:3] + goal_insights[:2],
        total_insights=len(today_insights),
        summary_text=narrative,
    )


@router.get(
    "/{user_id}",
    response_model=InsightListResponse,
    summary="Get user's recent insights",
    description="Returns paginated recent insights for the user, newest first.",
)
async def list_insights(
    user_id: str,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    insight_type: Optional[InsightType] = None,
) -> InsightListResponse:
    stored = _insight_store.get(user_id, [])

    if insight_type:
        stored = [i for i in stored if i.insight_type == insight_type]

    total = len(stored)
    offset = (page - 1) * page_size
    page_items = stored[offset : offset + page_size]

    return InsightListResponse(
        user_id=user_id,
        insights=page_items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{user_id}/{insight_id}",
    response_model=InsightDetailResponse,
    summary="Get specific insight",
    description="Returns a single insight with its full feedback history.",
)
async def get_insight(
    user_id: str,
    insight_id: str,
) -> InsightDetailResponse:
    stored = _insight_store.get(user_id, [])
    match = next((i for i in stored if i.insight_id == insight_id), None)

    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Insight '{insight_id}' not found for user '{user_id}'.",
        )

    feedback_history = _feedback_store.get(insight_id, [])

    return InsightDetailResponse(insight=match, feedback_history=feedback_history)


@router.post(
    "/{insight_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record user feedback",
    description=(
        "Records the user's feedback action on an insight: "
        "accepted, dismissed, helpful, or not_helpful."
    ),
)
async def record_feedback(
    insight_id: str,
    request: FeedbackRequest,
) -> FeedbackResponse:
    feedback_entry = {
        "feedback_id": str(uuid.uuid4()),
        "insight_id": insight_id,
        "action": request.action,
        "note": request.note,
        "recorded_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    _feedback_store.setdefault(insight_id, []).append(feedback_entry)

    logger.info(
        "insight_feedback_recorded",
        insight_id=insight_id,
        action=request.action,
    )

    return FeedbackResponse(
        insight_id=insight_id,
        action=request.action,
    )
