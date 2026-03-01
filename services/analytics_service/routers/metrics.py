"""
ZenSensei Analytics Service - Metrics Router

Endpoints
---------
GET /analytics/metrics/platform            Platform-wide metrics (DAU, MAU, retention)
GET /analytics/metrics/user/{user_id}      Per-user engagement metrics
GET /analytics/metrics/features            Feature adoption rates
GET /analytics/metrics/goals               Goal completion rates across platform
GET /analytics/metrics/integrations        Integration usage stats
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends

from services.analytics_service.schemas import (
    FeatureMetricsResponse,
    GoalMetrics,
    IntegrationMetricsResponse,
    PlatformMetricsResponse,
    UserMetricsResponse,
)
from services.analytics_service.services.metrics_service import (
    MetricsService,
    get_metrics_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get(
    "/platform",
    response_model=PlatformMetricsResponse,
    summary="Platform-wide metrics",
    description=(
        "Returns platform KPIs including DAU, MAU, WAU, DAU/MAU stickiness "
        "ratio, D1/D7/D30/D90 retention rates, and today's activity summary."
    ),
)
async def get_platform_metrics(
    svc: MetricsService = Depends(get_metrics_service),
) -> PlatformMetricsResponse:
    metrics = svc.get_platform_metrics()
    logger.info("platform_metrics_served", dau=metrics.dau, mau=metrics.mau)
    return metrics


@router.get(
    "/user/{user_id}",
    response_model=UserMetricsResponse,
    summary="User engagement metrics",
    description=(
        "Returns comprehensive engagement metrics for a specific user: "
        "session counts, streak, goal and task completion rates, insight "
        "action rate, and a composite engagement score (0–100)."
    ),
)
async def get_user_metrics(
    user_id: str,
    svc: MetricsService = Depends(get_metrics_service),
) -> UserMetricsResponse:
    metrics = svc.get_user_metrics(user_id)
    logger.info(
        "user_metrics_served",
        user_id=user_id,
        engagement_score=metrics.engagement_score,
    )
    return metrics


@router.get(
    "/features",
    response_model=FeatureMetricsResponse,
    summary="Feature adoption rates",
    description=(
        "Returns adoption metrics for every tracked product feature: "
        "users who tried it, monthly active users, adoption rate, "
        "average uses per active user, and trend direction."
    ),
)
async def get_feature_metrics(
    svc: MetricsService = Depends(get_metrics_service),
) -> FeatureMetricsResponse:
    features = svc.feature_adoption_rates()
    return FeatureMetricsResponse(
        features=features,
        total_features_tracked=len(features),
    )


@router.get(
    "/goals",
    response_model=GoalMetrics,
    summary="Goal completion rates",
    description=(
        "Returns aggregate goal statistics across the platform: "
        "total created, completed, active, abandoned; overall completion rate; "
        "average days-to-complete; and per-category breakdown."
    ),
)
async def get_goal_metrics(
    svc: MetricsService = Depends(get_metrics_service),
) -> GoalMetrics:
    return svc.goal_completion_rates()


@router.get(
    "/integrations",
    response_model=IntegrationMetricsResponse,
    summary="Integration usage stats",
    description=(
        "Returns usage statistics for each available integration: "
        "connected users, adoption rate, monthly active users, "
        "average syncs per user per week, and trend."
    ),
)
async def get_integration_metrics(
    svc: MetricsService = Depends(get_metrics_service),
) -> IntegrationMetricsResponse:
    integrations = svc.integration_usage()
    return IntegrationMetricsResponse(
        integrations=integrations,
        total_integrations_available=len(integrations),
    )
