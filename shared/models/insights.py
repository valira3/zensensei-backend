"""
ZenSensei Shared Models - Insights

Pydantic schemas for the Insight domain object.

Insights are AI-generated observations surfaced to the user about their
goals, tasks, or overall productivity patterns.  Each insight carries a
``category`` tag and a confidence ``score`` produced by the reasoning
service.

Schema variants
---------------
``InsightCreate``  – payload emitted by the AI reasoning service
``Insight``        – full internal representation
``InsightRead``    – API response model
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional

from pydantic import Field

from .base import TimestampedModel


class InsightCategory(str, Enum):
    """Broad categories for AI-generated insights."""

    PRODUCTIVITY = "productivity"
    GOAL_ALIGNMENT = "goal_alignment"
    BOTTLENECK = "bottleneck"
    RECOMMENDATION = "recommendation"
    ANOMALY = "anomaly"


class InsightCreate(TimestampedModel):
    """Payload emitted by the AI reasoning service when a new insight is ready."""

    user_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1)
    category: InsightCategory
    score: float = Field(..., ge=0.0, le=1.0, description="AI confidence score [0, 1].")
    source_goal_id: Optional[uuid.UUID] = None
    source_task_id: Optional[uuid.UUID] = None


class Insight(TimestampedModel):
    """Full Insight representation stored in the database."""

    user_id: uuid.UUID
    title: str
    body: str
    category: InsightCategory
    score: float
    source_goal_id: Optional[uuid.UUID] = None
    source_task_id: Optional[uuid.UUID] = None
    is_read: bool = False


InsightRead = Insight
