"""
ZenSensei AI Reasoning Service - Schemas

Pydantic request/response models for the AI Reasoning Service API.
All models extend the shared BaseModel to get orjson serialisation,
enum coercion, and consistent config.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from pydantic import Field, field_validator

from shared.models.base import BaseModel, TimestampMixin
from shared.models.insights import InsightImpact, InsightType


# ─── Enums ────────────────────────────────────────────────────────────────────


class FeedbackAction(StrEnum):
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"


class DecisionCategory(StrEnum):
    CAREER = "CAREER"
    FINANCIAL = "FINANCIAL"
    RELATIONSHIP = "RELATIONSHIP"
    HEALTH = "HEALTH"
    PERSONAL_GROWTH = "PERSONAL_GROWTH"
    OTHER = "OTHER"


class RecommendationType(StrEnum):
    GOAL = "GOAL"
    RELATIONSHIP = "RELATIONSHIP"
    WELLNESS = "WELLNESS"
    HABIT = "HABIT"
    TASK = "TASK"
    FINANCIAL = "FINANCIAL"


class RecommendationPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


# ─── Insight Schemas ──────────────────────────────────────────────────────────


class InsightGenerateRequest(BaseModel):
    """Request body for triggering daily insight generation for a user."""

    force_refresh: bool = Field(
        default=False,
        description="Bypass cache and regenerate insights even if fresh ones exist",
    )
    max_insights: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of insights to generate",
    )
    focus_areas: list[InsightType] = Field(
        default_factory=list,
        description="Optional list of insight types to prioritise",
    )


class InsightItem(BaseModel):
    """A single AI-generated insight."""

    insight_id: str
    insight_type: InsightType
    title: str
    description: str
    action: str = Field(description="Suggested next action derived from this insight")
    confidence: float = Field(ge=0.0, le=1.0, description="Model confidence 0–1")
    impact: InsightImpact
    related_node_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class InsightGenerateResponse(BaseModel):
    """Response body after generating daily insights."""

    user_id: str
    insights: list[InsightItem]
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    model_used: str
    from_cache: bool = False
    generation_duration_ms: Optional[float] = None


class InsightListResponse(BaseModel):
    """Paginated list of a user's recent insights."""

    user_id: str
    insights: list[InsightItem]
    total: int
    page: int = 1
    page_size: int = 20


class InsightDetailResponse(BaseModel):
    """Full detail of a single insight including feedback history."""

    insight: InsightItem
    feedback_history: list[dict[str, Any]] = Field(default_factory=list)


class DailySummaryResponse(BaseModel):
    """High-level daily summary with prioritised action items."""

    user_id: str
    date: str = Field(description="ISO date string e.g. 2026-03-01")
    top_priorities: list[InsightItem]
    relationship_nudges: list[InsightItem]
    risk_alerts: list[InsightItem]
    pattern_observations: list[InsightItem]
    total_insights: int
    wellness_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Optional aggregate wellness score 0–100",
    )
    summary_text: str = Field(description="One-paragraph narrative summary for the day")


class FeedbackRequest(BaseModel):
    """Record user feedback on an insight."""

    action: FeedbackAction
    note: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional free-text comment from the user",
    )


class FeedbackResponse(BaseModel):
    """Confirmation of recorded feedback."""

    insight_id: str
    action: FeedbackAction
    recorded_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


# ─── Decision Schemas ─────────────────────────────────────────────────────────


class DecisionOption(BaseModel):
    """One option within a decision being analysed."""

    label: str = Field(min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=1000)
    estimated_cost: Optional[float] = Field(default=None, ge=0)
    estimated_timeline_days: Optional[int] = Field(default=None, ge=0)
    tags: list[str] = Field(default_factory=list)


class DecisionContext(BaseModel):
    """Full context for a decision to be analysed."""

    title: str = Field(min_length=1, max_length=256)
    description: str = Field(min_length=1, max_length=3000)
    category: DecisionCategory = DecisionCategory.OTHER
    options: list[DecisionOption] = Field(
        default_factory=list,
        description="Explicit options being considered (optional for open analysis)",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Constraints or requirements (e.g. 'must complete by June')",
    )
    related_goal_ids: list[str] = Field(
        default_factory=list,
        description="IDs of goals this decision affects",
    )
    user_id: str
    urgency_days: Optional[int] = Field(
        default=None,
        ge=0,
        description="How many days until a decision must be made",
    )


class FactorAnalysis(BaseModel):
    """Analysis of a single decision factor."""

    factor: str
    assessment: str
    score: float = Field(ge=0.0, le=10.0, description="Factor score 0–10")
    evidence: list[str] = Field(default_factory=list)
    recommendation: str


class DecisionAnalysis(BaseModel):
    """Full multi-factor decision analysis result."""

    decision_id: str
    user_id: str
    title: str
    summary: str = Field(description="One-paragraph executive summary")
    recommended_option: Optional[str] = Field(
        default=None,
        description="Label of the recommended option if one clearly stands out",
    )
    confidence: float = Field(ge=0.0, le=1.0)

    # Factor-level breakdowns
    goal_impact: FactorAnalysis
    relationship_effect: FactorAnalysis
    financial_implications: FactorAnalysis
    historical_patterns: FactorAnalysis
    opportunity_cost: FactorAnalysis
    risk_assessment: FactorAnalysis

    overall_score: float = Field(
        ge=0.0, le=10.0, description="Composite decision quality score 0–10"
    )
    action_steps: list[str] = Field(
        default_factory=list, description="Recommended next steps"
    )
    risks: list[str] = Field(default_factory=list)
    upsides: list[str] = Field(default_factory=list)
    model_used: str
    analyzed_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class OptionComparison(BaseModel):
    """Side-by-side comparison result for a single option."""

    label: str
    overall_score: float = Field(ge=0.0, le=10.0)
    goal_alignment: float = Field(ge=0.0, le=10.0)
    financial_score: float = Field(ge=0.0, le=10.0)
    relationship_impact: float = Field(ge=0.0, le=10.0)
    risk_score: float = Field(ge=0.0, le=10.0, description="Lower is riskier")
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    summary: str


class DecisionCompareRequest(BaseModel):
    """Request to compare multiple options side by side."""

    user_id: str
    context_description: str = Field(min_length=1, max_length=2000)
    options: list[DecisionOption] = Field(min_length=2)
    related_goal_ids: list[str] = Field(default_factory=list)


class DecisionCompareResponse(BaseModel):
    """Side-by-side comparison of multiple decision options."""

    user_id: str
    context_description: str
    options: list[OptionComparison]
    recommended: str = Field(description="Label of the top-ranked option")
    reasoning: str = Field(description="Brief reasoning for the recommendation")
    compared_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class DecisionHistoryItem(BaseModel):
    """Summary of a past decision analysis."""

    decision_id: str
    title: str
    category: DecisionCategory
    recommended_option: Optional[str]
    overall_score: float
    analyzed_at: datetime


class DecisionHistoryResponse(BaseModel):
    """Paginated history of past decision analyses."""

    user_id: str
    analyses: list[DecisionHistoryItem]
    total: int


# ─── Recommendation Schemas ───────────────────────────────────────────────────


class RecommendationItem(BaseModel):
    """A single personalised recommendation."""

    rec_id: str
    rec_type: RecommendationType
    title: str
    description: str
    rationale: str = Field(description="Why this recommendation is surfaced now")
    priority: RecommendationPriority
    effort: str = Field(
        description="Estimated effort level: low / medium / high"
    )
    estimated_impact: InsightImpact
    action_url: Optional[str] = Field(
        default=None, description="Deep-link into the app for quick action"
    )
    related_entity_id: Optional[str] = Field(
        default=None, description="ID of the goal, relationship, or habit this relates to"
    )
    acted_at: Optional[datetime] = None


class RecommendationResponse(BaseModel):
    """List of personalised recommendations for a user."""

    user_id: str
    recommendations: list[RecommendationItem]
    focus_area: str
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class ActOnRecommendationRequest(BaseModel):
    """Request body to mark a recommendation as acted upon."""

    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional notes about the action taken",
    )


class ActOnRecommendationResponse(BaseModel):
    """Confirmation that a recommendation was acted upon."""

    rec_id: str
    acted_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
