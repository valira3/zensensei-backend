"""
ZenSensei Shared Models - Tasks

Task-related Pydantic models for creating, updating, and returning Task
objects through the ZenSensei API.

Schema variants
---------------
``TaskCreate``  – payload accepted on POST /tasks
``TaskUpdate``  – partial payload accepted on PATCH /tasks/{id}
``Task``        – full internal representation
``TaskRead``    – API response model
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field

from .base import TimestampedModel


class TaskStatus(str, Enum):
    """Lifecycle states for a Task."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """Relative importance of a Task."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskCreate(TimestampedModel):
    """Fields required / allowed when creating a new Task."""

    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: Optional[datetime] = None
    goal_id: Optional[uuid.UUID] = None
    assignee_id: Optional[uuid.UUID] = None
    owner_id: uuid.UUID


class TaskUpdate(TimestampedModel):
    """All fields optional for partial updates."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[datetime] = None
    goal_id: Optional[uuid.UUID] = None
    assignee_id: Optional[uuid.UUID] = None


class Task(TimestampedModel):
    """Full Task representation."""

    title: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: Optional[datetime] = None
    goal_id: Optional[uuid.UUID] = None
    assignee_id: Optional[uuid.UUID] = None
    owner_id: uuid.UUID


TaskRead = Task
