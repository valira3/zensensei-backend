"""
ZenSensei Analytics Service - Schemas

Pydantic request/response models for the Analytics Service API.
All models extend the shared BaseModel to get orjson serialisation,
enum coercion, and consistent config.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from pydantic import Field, field_validator

from shared.models.base import BaseModel, TimestampMixin


# ─── Enums ────────────────────────────────────────────────────────────────────


class EventType(StrEnum):
    PAGE_VIEW = "page_view"
    FEATURE_USE = "feature_use"
    GOAL_CREATE = "goal_create"
    GOAL_COMPLETE = "goal_complete"
    TASK_CREATE = "task_create"
    TASK_COMPLETE = "task_complete"
    INSIGHT_VIEW = "insight_view"
    INSIGHT_ACT = "insight_act"
    INTEGRATION_CONNECT = "integration_connect"
    SESSION_START = "session_start"
    SESSION_END = "session_end"


class PatternType(StrEnum):
    TIME_OF_DAY = "time_of_day"
    DAY_OF_WEEK = "day_of_week"
    STREAK = "streak"
    DECLINE = "decline"
    SURGE = "surge"
    CORRELATION = "correlation"


class TrendDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


class ReportPeriod(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# ─── Event Schemas ─────────────────────────────────────────────────────────────────


class EventTrackRequest(BaseModel):
    """Request body to track a single analytics event."""

    user_id: str = Field(description="ID of the user generating the event")
    event_type: EventType = Field(description="Type of event being tracked")
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key-value metadata associated with the event",
    )
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Event timestamp; defaults to server time if omitted",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session identifier for grouping events",
    )


class EventBatchRequest(BaseModel):
    """Request body for batch event ingestion."""

    events: list[EventTrackRequest] = Field(
        min_length=1,
        max_length=500,
        description="List of events to track in a single request (max 500)",
    )


class EventRecord(TimestampMixin):
    """A persisted analytics event record."""

    event_id: str
    user_id: str
    event_type: EventType
    properties: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    session_id: Optional[str] = None
    ingested_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class EventResponse(BaseModel):
    """Confirmation of a tracked event."""

    event_id: str
    status: str = "accepted"
    ingested_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class EventBatchResponse(BaseModel):
    """Confirmation of batch event ingestion."""

    accepted: int
    failed: int
    event_ids: list[str]
    ingested_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class EventHistoryResponse(BaseModel):
    """Paginated event history for a user."""

    user_id: str
    events: list[EventRecord]
    total: int
    page: int = 1
    page_size: int = 50


# ─── Metrics Schemas ──────────────────────────────────────────────────────────────


class RetentionData(BaseModel):
    """Retention rates broken down by period."""

    day_1: float = Field(ge=0.0, le=1.0, description="Day-1 retention rate 0–1")
    day_7: float = Field(ge=0.0, le=1.0, description="Day-7 retention rate 0–1")
    day_30: float = Field(ge=0.0, le=1.0, description="Day-30 retention rate 0–1")
    day_90: float = Field(ge=0.0, le=1.0, description="Day-90 retention rate 0–1")


class PlatformMetricsResponse(BaseModel):
    """Platform-wide KPIs: DAU, MAU, retention, and revenue proxies."""

    dau: int = Field(description="Daily active users (rolling 24 h)")
    mau: int = Field(description="Monthly active users (rolling 30 days)")
    wau: int = Field(description="Weekly active users (rolling 7 days)")
    dau_mau_ratio: float = Field(ge=0.0, le=1.0, description="DAU/MAU stickiness ratio")
    retention: RetentionData
    new_users_today: int
    new_users_this_month: int
    total_registered_users: int
    avg_session_duration_minutes: float
    sessions_today: int
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class UserMetricsResponse(BaseModel):
    """Engagement metrics for a specific user."""

    user_id: str
    total_sessions: int
    sessions_last_7_days: int
    sessions_last_30_days: int
    avg_session_duration_minutes: float
    engagement_score: float = Field(ge=0.0, le=100.0)
    current_streak_days: int
    longest_streak_days: int
    goals_created: int
    goals_completed: int
    goal_completion_rate: float = Field(ge=0.0, le=1.0)
    tasks_created: int
    tasks_completed: int
    task_completion_rate: float = Field(ge=0.0, le=1.0)
    insights_viewed: int
    insights_acted_on: int
    insight_action_rate: float = Field(ge=0.0, le=1.0)
    integrations_connected: int
    last_active_at: Optional[datetime] = None
    member_since: Optional[datetime] = None
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class FeatureMetric(BaseModel):
    """Adoption metrics for a single feature."""

    feature_name: str
    feature_key: str
    users_tried: int
    users_active_last_30_days: int
    adoption_rate: float = Field(ge=0.0, le=1.0)
    avg_uses_per_active_user: float
    trend: TrendDirection


class FeatureMetricsResponse(BaseModel):
    """Feature adoption rates across the platform."""

    features: list[FeatureMetric]
    total_features_tracked: int
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class GoalMetrics(BaseModel):
    """Goal completion stats for the platform."""

    total_goals_created: int
    total_goals_completed: int
    total_goals_active: int
    total_goals_abandoned: int
    overall_completion_rate: float = Field(ge=0.0, le=1.0)
    avg_days_to_complete: float
    completion_by_category: dict[str, float] = Field(default_factory=dict)
    most_common_goal_categories: list[str]
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class IntegrationUsageMetric(BaseModel):
    """Usage stats for a single integration."""

    integration_name: str
    integration_key: str
    connected_users: int
    adoption_rate: float = Field(ge=0.0, le=1.0)
    active_last_30_days: int
    avg_syncs_per_user_per_week: float
    trend: TrendDirection


class IntegrationMetricsResponse(BaseModel):
    """Integration usage stats across the platform."""

    integrations: list[IntegrationUsageMetric]
    total_integrations_available: int
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


# ─── Pattern Schemas ─────────────────────────────────────────────────────────────────


class PatternItem(BaseModel):
    """A single detected behavioral pattern."""

    pattern_id: str
    pattern_type: PatternType
    title: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    strength: float = Field(ge=0.0, le=1.0)
    supporting_data: dict[str, Any] = Field(default_factory=dict)
    first_observed_at: Optional[datetime] = None
    last_observed_at: Optional[datetime] = None


class PatternResponse(BaseModel):
    """All detected patterns for a user."""

    user_id: str
    patterns: list[PatternItem]
    total: int
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class TrendItem(BaseModel):
    """A single detected trend."""

    metric: str
    direction: TrendDirection
    change_percent: float
    period_days: int
    data_points: list[dict[str, Any]] = Field(default_factory=list)
    insight: str


class TrendResponse(BaseModel):
    """Trend analysis for a user."""

    user_id: str
    trends: list[TrendItem]
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class AnomalyItem(BaseModel):
    """A single detected anomaly."""

    anomaly_id: str
    metric: str
    description: str
    severity: str
    observed_value: float
    expected_value: float
    deviation_percent: float
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class AnomalyResponse(BaseModel):
    """Anomaly detection results for a user."""

    user_id: str
    anomalies: list[AnomalyItem]
    total: int
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class PredictionItem(BaseModel):
    """A single behavior prediction."""

    prediction_id: str
    predicted_action: str
    probability: float = Field(ge=0.0, le=1.0)
    timeframe: str
    rationale: str
    suggested_nudge: Optional[str] = None


class PredictionResponse(BaseModel):
    """Behavior predictions for a user."""

    user_id: str
    predictions: list[PredictionItem]
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


# ─── Report Schemas ───────────────────────────────────────────────────────────────────


class ChartDataset(BaseModel):
    """A single dataset within a chart."""

    label: str
    data: list[float]
    color: Optional[str] = None


class ChartData(BaseModel):
    """Chart data structure for frontend rendering."""

    chart_type: str
    title: str
    labels: list[str]
    datasets: list[ChartDataset]
    unit: Optional[str] = None


class WeeklyReportResponse(BaseModel):
    """Weekly personal report for a user."""

    user_id: str
    report_id: str
    week_start: str
    week_end: str
    period: str = ReportPeriod.WEEKLY
    sessions_this_week: int
    avg_session_duration_minutes: float
    streak_days: int
    goals_completed: int
    tasks_completed: int
    insights_acted_on: int
    engagement_score: float = Field(ge=0.0, le=100.0)
    engagement_score_change: float
    achievements: list[str] = Field(default_factory=list)
    improvement_areas: list[str] = Field(default_factory=list)
    top_patterns: list[PatternItem] = Field(default_factory=list)
    activity_chart: ChartData
    goal_progress_chart: ChartData
    summary_text: str
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class MonthlyReportResponse(BaseModel):
    """Monthly personal deep-dive report for a user."""

    user_id: str
    report_id: str
    month: str
    period: str = ReportPeriod.MONTHLY
    sessions_this_month: int
    total_active_days: int
    avg_session_duration_minutes: float
    goals_created: int
    goals_completed: int
    goal_completion_rate: float = Field(ge=0.0, le=1.0)
    tasks_created: int
    tasks_completed: int
    task_completion_rate: float = Field(ge=0.0, le=1.0)
    insights_viewed: int
    insights_acted_on: int
    longest_streak_days: int
    engagement_score: float = Field(ge=0.0, le=100.0)
    engagement_score_change: float
    achievements: list[str] = Field(default_factory=list)
    top_features_used: list[str] = Field(default_factory=list)
    top_patterns: list[PatternItem] = Field(default_factory=list)
    key_trends: list[TrendItem] = Field(default_factory=list)
    activity_heatmap: ChartData
    engagement_trend_chart: ChartData
    goal_breakdown_chart: ChartData
    summary_text: str
    highlights: list[str] = Field(default_factory=list)
    action_recommendations: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class PlatformDailyReportResponse(BaseModel):
    """Platform-wide daily KPI report (admin-facing)."""

    report_id: str
    date: str
    dau: int
    new_signups: int
    churned_users: int
    net_user_growth: int
    total_sessions: int
    avg_session_duration_minutes: float
    total_events: int
    events_by_type: dict[str, int] = Field(default_factory=dict)
    goals_created: int
    goals_completed: int
    tasks_created: int
    tasks_completed: int
    insights_generated: int
    insights_acted_on: int
    new_integrations_connected: int
    active_integrations: int
    hourly_dau_chart: ChartData
    event_breakdown_chart: ChartData
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class CohortMetric(BaseModel):
    """A single cohort retention data point."""

    period: int
    retained_users: int
    retention_rate: float = Field(ge=0.0, le=1.0)


class CohortAnalysisResponse(BaseModel):
    """Cohort analysis report."""

    cohort_id: str
    cohort_name: str
    signup_period: str
    initial_users: int
    retention_data: list[CohortMetric]
    avg_engagement_score: float = Field(ge=0.0, le=100.0)
    avg_goals_per_user: float
    avg_session_duration_minutes: float
    top_features: list[str] = Field(default_factory=list)
    chart: ChartData
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
