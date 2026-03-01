"""
ZenSensei Analytics Service - Schemas

Pydantic models for the Analytics Service.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Events ──────────────────────────────────────────────────────────────────────


class TrackEventRequest(BaseModel):
    """Single event to be tracked."""

    event_type: str = Field(
        ...,
        description="Event type in dot-notation, e.g. task.completed",
        examples=["task.completed", "insight.viewed", "goal.updated"],
    )
    user_id: str = Field(..., description="User who triggered the event")
    source: str = Field(
        default="webapp",
        description="Source system: webapp / mobile / integration_service / etc.",
    )
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary event properties",
    )
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Event timestamp (defaults to server time if omitted)",
    )
    session_id: Optional[str] = None


class TrackEventResponse(BaseModel):
    event_id: str
    tracked: bool = True
    timestamp: datetime


class BatchTrackRequest(BaseModel):
    events: list[TrackEventRequest] = Field(
        ..., min_length=1, max_length=100, description="Batch of events to track"
    )


class BatchTrackResponse(BaseModel):
    tracked_count: int
    failed_count: int
    event_ids: list[str]


# ─── Metrics ─────────────────────────────────────────────────────────────────────


class MetricDataPoint(BaseModel):
    timestamp: datetime
    value: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class MetricSummary(BaseModel):
    metric_name: str
    period: str
    start: datetime
    end: datetime
    count: int
    sum: float
    mean: float
    min: float
    max: float
    p50: Optional[float] = None
    p95: Optional[float] = None
    p99: Optional[float] = None


class MetricsResponse(BaseModel):
    user_id: str
    metric_name: str
    period: str
    data_points: list[MetricDataPoint]
    summary: MetricSummary
    generated_at: datetime


class MetricsDashboardResponse(BaseModel):
    user_id: str
    period: str
    start: datetime
    end: datetime
    metrics: list[MetricSummary]
    generated_at: datetime


# ─── Patterns ─────────────────────────────────────────────────────────────────────


class PatternItem(BaseModel):
    pattern_id: str
    pattern_type: str = Field(
        ...,
        description="Type: temporal / behavioral / correlation / anomaly",
    )
    title: str
    description: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    strength: float = Field(..., ge=0.0, le=1.0, description="Pattern strength 0–1")
    occurrences: int
    first_detected: datetime
    last_detected: datetime
    related_events: list[str] = Field(default_factory=list, description="Event types involved")
    metadata: dict[str, Any] = Field(default_factory=dict)


class PatternsResponse(BaseModel):
    user_id: str
    patterns: list[PatternItem]
    total_count: int
    analysis_window_days: int
    generated_at: datetime


# ─── Reports ─────────────────────────────────────────────────────────────────────


class ReportSection(BaseModel):
    section_id: str
    title: str
    content: str
    data: dict[str, Any] = Field(default_factory=dict)
    charts: list[dict[str, Any]] = Field(default_factory=list)


class ReportResponse(BaseModel):
    report_id: str
    user_id: str
    report_type: str
    title: str
    period_start: datetime
    period_end: datetime
    sections: list[ReportSection]
    summary: str
    generated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerateReportRequest(BaseModel):
    report_type: str = Field(
        ...,
        description="Report type: weekly_summary / monthly_review / goal_progress / financial_summary",
        pattern="^(weekly_summary|monthly_review|goal_progress|financial_summary)$",
    )
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    include_sections: list[str] = Field(
        default_factory=list,
        description="Optional list of section IDs to include. Empty = all.",
    )
