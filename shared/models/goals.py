"""
ZenSensei Shared Models - Goals

Pydantic schemas for the Goal domain object.

A ``Goal`` represents a high-level objective set by a ZenSensei user.  Goals
are hierarchical: a goal may optionally reference a parent goal via
``parent_id``, enabling tree-structured goal breakdowns.

Schema variants
---------------
``GoalCreate``  – payload accepted on POST /goals
``GoalUpdate``  – partial payload accepted on PATCH /goals/{id}
``Goal``        – full internal representation (includes all fields)
``GoalRead``    – API response model (alias of ``Goal`` for clarity)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field

from .base import TimestampedModel


class GoalStatus(str, Enum):
    """Lifecycle states for a Goal."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class GoalPriority(str, Enum):
    """Relative importance of a Goal."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Write schemas
# ---------------------------------------------------------------------------

class GoalCreate(TimestampedModel):
    """Fields required / allowed when creating a new Goal."""

    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    status: GoalStatus = GoalStatus.DRAFT
    priority: GoalPriority = GoalPriority.MEDIUM
    due_date: Optional[datetime] = None
    parent_id: Optional[uuid.UUID] = None
    owner_id: uuid.UUID


class GoalUpdate(TimestampedModel):
    """All fields optional for partial updates."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    status: Optional[GoalStatus] = None
    priority: Optional[GoalPriority] = None
    due_date: Optional[datetime] = None
    parent_id: Optional[uuid.UUID] = None


# ---------------------------------------------------------------------------
# Read / internal schema
# ---------------------------------------------------------------------------

class Goal(TimestampedModel):
    """Full Goal representation stored in the database."""

    title: str
    description: Optional[str] = None
    status: GoalStatus = GoalStatus.DRAFT
    priority: GoalPriority = GoalPriority.MEDIUM
    due_date: Optional[datetime] = None
    parent_id: Optional[uuid.UUID] = None
    owner_id: uuid.UUID


# ``GoalRead`` is intentionally identical to ``Goal``; it exists so that
# callers can import a semantically meaningful name for the response model.
GoalRead = Goal
