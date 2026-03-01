"""
ZenSensei Analytics Service - Reports Router

Endpoints
---------
GET /analytics/reports/weekly/{user_id}        Weekly personal report
GET /analytics/reports/monthly/{user_id}       Monthly personal deep-dive
GET /analytics/reports/platform/daily          Platform daily KPI report (admin)
GET /analytics/reports/cohort/{cohort_id}      Cohort retention analysis
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends

from services.analytics_service.schemas import (
    CohortAnalysisResponse,
    MonthlyReportResponse,
    PlatformDailyReportResponse,
    WeeklyReportResponse,
)
from services.analytics_service.services.report_generator import (
    ReportGenerator,
    get_report_generator,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get(
    "/weekly/{user_id}",
    response_model=WeeklyReportResponse,
    summary="Weekly personal report",
    description=(
        "Generates a weekly summary for the given user including session stats, "
        "goal and task completions, top behavioral patterns, and chart data."
    ),
)
async def get_weekly_report(
    user_id: str,
    generator: ReportGenerator = Depends(get_report_generator),
) -> WeeklyReportResponse:
    report = generator.generate_weekly_report(user_id)
    logger.info(
        "weekly_report_generated",
        user_id=user_id,
        report_id=report.report_id,
        week_start=report.week_start,
    )
    return report


@router.get(
    "/monthly/{user_id}",
    response_model=MonthlyReportResponse,
    summary="Monthly personal report",
    description=(
        "Generates a monthly deep-dive for the given user including a 28-day "
        "activity heatmap, engagement trend chart, goal breakdown, and narrative."
    ),
)
async def get_monthly_report(
    user_id: str,
    generator: ReportGenerator = Depends(get_report_generator),
) -> MonthlyReportResponse:
    report = generator.generate_monthly_report(user_id)
    logger.info(
        "monthly_report_generated",
        user_id=user_id,
        report_id=report.report_id,
        month=report.month,
    )
    return report


@router.get(
    "/platform/daily",
    response_model=PlatformDailyReportResponse,
    summary="Platform daily report (admin)",
    description=(
        "Generates the platform-wide KPI report for today including user growth, "
        "engagement, product metrics, and an hourly active-users chart."
    ),
)
async def get_platform_daily_report(
    generator: ReportGenerator = Depends(get_report_generator),
) -> PlatformDailyReportResponse:
    report = generator.generate_platform_daily()
    logger.info(
        "platform_daily_report_generated",
        report_id=report.report_id,
        date=report.date,
        dau=report.dau,
    )
    return report


@router.get(
    "/cohort/{cohort_id}",
    response_model=CohortAnalysisResponse,
    summary="Cohort analysis",
    description=(
        "Returns cohort retention and engagement analysis. "
        "Use a year-month string as cohort_id (e.g. '2026-01')."
    ),
)
async def get_cohort_analysis(
    cohort_id: str,
    generator: ReportGenerator = Depends(get_report_generator),
) -> CohortAnalysisResponse:
    report = generator.generate_cohort_report(cohort_id)
    logger.info(
        "cohort_report_generated",
        cohort_id=cohort_id,
        initial_users=report.initial_users,
    )
    return report
