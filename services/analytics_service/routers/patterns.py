"""
ZenSensei Analytics Service - Patterns Router

Endpoints
---------
GET /analytics/patterns/{user_id}                  Detected behavioral patterns
GET /analytics/patterns/{user_id}/trends           Trend analysis
GET /analytics/patterns/{user_id}/anomalies        Anomaly detection
GET /analytics/patterns/{user_id}/predictions      Behavior predictions
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends

from services.analytics_service.schemas import (
    AnomalyResponse,
    PatternResponse,
    PredictionResponse,
    TrendResponse,
)
from services.analytics_service.services.pattern_detector import (
    PatternDetector,
    get_pattern_detector,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get(
    "/{user_id}",
    response_model=PatternResponse,
    summary="Detected user patterns",
    description=(
        "Returns behavioral patterns detected for the user. "
        "Pattern types include: time_of_day, day_of_week, streak, decline, "
        "surge, and correlation. Each pattern has a confidence score (0–1) "
        "and strength indicator."
    ),
)
async def get_patterns(
    user_id: str,
    detector: PatternDetector = Depends(get_pattern_detector),
) -> PatternResponse:
    from datetime import datetime, timezone

    patterns = detector.detect_patterns(user_id)
    logger.info("patterns_detected", user_id=user_id, count=len(patterns))
    return PatternResponse(
        user_id=user_id,
        patterns=patterns,
        total=len(patterns),
        computed_at=datetime.now(tz=timezone.utc),
    )


@router.get(
    "/{user_id}/trends",
    response_model=TrendResponse,
    summary="Trend analysis",
    description=(
        "Returns upward/downward/stable trend analysis for the user's key metrics "
        "including task completions, engagement score, goal completion rate, "
        "session duration, and insight action rate."
    ),
)
async def get_trends(
    user_id: str,
    detector: PatternDetector = Depends(get_pattern_detector),
) -> TrendResponse:
    from datetime import datetime, timezone

    trends = detector.detect_trends(user_id)
    logger.info("trends_computed", user_id=user_id, count=len(trends))
    return TrendResponse(
        user_id=user_id,
        trends=trends,
        computed_at=datetime.now(tz=timezone.utc),
    )


@router.get(
    "/{user_id}/anomalies",
    response_model=AnomalyResponse,
    summary="Anomaly detection",
    description=(
        "Detects unusual deviations in the user's behavior relative to their "
        "historical baseline."
    ),
)
async def get_anomalies(
    user_id: str,
    detector: PatternDetector = Depends(get_pattern_detector),
) -> AnomalyResponse:
    from datetime import datetime, timezone

    anomalies = detector.detect_anomalies(user_id)
    logger.info("anomalies_detected", user_id=user_id, count=len(anomalies))
    return AnomalyResponse(
        user_id=user_id,
        anomalies=anomalies,
        total=len(anomalies),
        computed_at=datetime.now(tz=timezone.utc),
    )


@router.get(
    "/{user_id}/predictions",
    response_model=PredictionResponse,
    summary="Behavior predictions",
    description=(
        "Predicts the user's next likely actions based on detected patterns "
        "and historical behavior."
    ),
)
async def get_predictions(
    user_id: str,
    detector: PatternDetector = Depends(get_pattern_detector),
) -> PredictionResponse:
    from datetime import datetime, timezone

    predictions = detector.predict_behavior(user_id)
    logger.info("predictions_generated", user_id=user_id, count=len(predictions))
    return PredictionResponse(
        user_id=user_id,
        predictions=predictions,
        computed_at=datetime.now(tz=timezone.utc),
    )
