"""
ZenSensei AI Reasoning Service - Schemas

Pydantic request/response models for the AI Reasoning Service.
All IDs are strings (UUIDs from Firestore/Neo4j).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Shared sub-models ───────────────────────────────────────────────────────────────────


class EvidenceItem(BaseModel):
    """A single piece of evidence supporting an insight or decision."""

    source: str = Field(..., description="Data source (e.g. 'calendar', 'tasks', 'graph')")
    description: str = Field(..., description="Human-readable description of the evidence")
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Evidence weight 0–1")
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecommendationItem(BaseModel):
    """A single actionable recommendation."""

    rec_id: str = Field(..., description="Unique recommendation ID")
    title: str = Field(..., description="Short title for the recommendation")
    description: str = Field(..., description="Detailed description and rationale")
    priority: str = Field(..., description="Priority: high / medium / low")
    effort: str = Field(..., description="Effort: low / medium / high")
    category: str = Field(..., description="Life area: career / health / finance / etc.")
    action_url: Optional[str] = Field(default=None, description="Deep-link to act on the recommendation")
    estimated_impact: Optional[str] = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InsightItem(BaseModel):
    """A single AI-generated insight."""

    insight_id: str
    insight_type: str = Field(
        ...,
        description="Type: pattern / financial / wellness / skill_gap / relationship / goal_risk",
    )
    title: str
    summary: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    severity: str = Field(..., description="Severity: info / suggestion / warning / critical")
    evidence: list[EvidenceItem] = Field(default_factory=list)
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    generated_at: datetime
    expires_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionOption(BaseModel):
    """One option within a decision analysis."""

    option_id: str
    label: str
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    estimated_outcome: Optional[str] = None
    alignment_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Alignment with user goals 0-1")
    risk_level: str = Field(default="medium", description="low / medium / high")


# ─── Insights ──────────────────────────────────────────────────────────────────────


class GenerateInsightsRequest(BaseModel):
    """Request body for generating insights."""

    focus_areas: list[str] = Field(
        default_factory=list,
        description="Optional: focus on specific areas. Empty = all areas.",
        examples=[["career", "health"]],
    )
    max_insights: int = Field(default=5, ge=1, le=20)
    min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    include_low_confidence: bool = Field(
        default=False,
        description="If True, includes insights below min_confidence with a lower confidence flag.",
    )


class InsightResponse(BaseModel):
    """Response wrapping a list of generated insights."""

    user_id: str
    insights: list[InsightItem]
    total_count: int
    generated_at: datetime
    processing_time_ms: Optional[int] = None


class FeedbackRequest(BaseModel):
    """Feedback on a specific insight."""

    feedback: str = Field(
        ...,
        description="User feedback value: helpful / not_helpful / dismissed / acted_upon",
        pattern="^(helpful|not_helpful|dismissed|acted_upon)$",
    )
    notes: Optional[str] = Field(default=None, max_length=500)


class FeedbackResponse(BaseModel):
    insight_id: str
    feedback_recorded: bool = True
    message: str = "Feedback recorded. Thank you!"


# ─── Decisions ──────────────────────────────────────────────────────────────────────


class AnalyzeDecisionRequest(BaseModel):
    """Request body for decision analysis."""

    decision_title: str = Field(..., max_length=200, description="Brief title for the decision")
    decision_description: str = Field(
        ..., max_length=2000, description="Full context of the decision"
    )
    options: list[str] = Field(
        ...,
        min_length=2,
        max_length=5,
        description="List of options to evaluate (2–5 options)",
    )
    context: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Additional context (budget, constraints, timeline)",
    )
    priority_areas: list[str] = Field(
        default_factory=list,
        description="Life areas to prioritise in evaluation (career, health, finance, etc.)",
    )
    risk_tolerance: str = Field(
        default="medium",
        description="User's risk tolerance: low / medium / high",
        pattern="^(low|medium|high)$",
    )


class DecisionAnalysisResponse(BaseModel):
    """Full decision analysis response."""

    decision_id: str
    user_id: str
    decision_title: str
    summary: str = Field(..., description="One-paragraph executive summary")
    options: list[DecisionOption]
    recommended_option: Optional[str] = Field(
        default=None, description="option_id of recommended choice (None if tied)"
    )
    reasoning: str = Field(
        ..., description="Detailed reasoning behind the recommendation"
    )
    key_factors: list[str] = Field(default_factory=list, description="Top factors that drove the recommendation")
    risks: list[str] = Field(default_factory=list, description="Key risks regardless of option chosen")
    confidence: float = Field(..., ge=0.0, le=1.0)
    generated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


# ─── Recommendations ──────────────────────────────────────────────────────────────────


class RecommendationResponse(BaseModel):
    user_id: str
    recommendations: list[RecommendationItem]
    focus_area: str
    total_count: int
    generated_at: datetime


class ActOnRecommendationRequest(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=500)


class ActOnRecommendationResponse(BaseModel):
    rec_id: str
    acted: bool = True
    message: str = "Recommendation marked as acted upon."
