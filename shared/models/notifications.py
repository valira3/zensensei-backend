"""
ZenSensei Shared Models - Notifications

Pydantic schemas for the Notification domain object.

A ``Notification`` is an in-app or push alert sent to a user in response
to a system event (e.g. a task becoming overdue, an AI insight being
generated, or a goal status change).

Schema variants
---------------
``NotificationCreate``  – payload emitted by any service that wants to alert
                          a user
``Notification``        – full internal representation
``NotificationRead``    – API response model
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import Field

from .base import TimestampedModel


class NotificationChannel(str, Enum):
    """Delivery channel for a notification."""

    IN_APP = "in_app"
    EMAIL = "email"
    PUSH = "push"
    SLACK = "slack"


class NotificationPriority(str, Enum):
    """Urgency level."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationCreate(TimestampedModel):
    """Payload for creating a new notification."""

    user_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1)
    channel: NotificationChannel = NotificationChannel.IN_APP
    priority: NotificationPriority = NotificationPriority.NORMAL
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary context data attached to this notification.",
    )
    action_url: Optional[str] = None


class Notification(TimestampedModel):
    """Full Notification record."""

    user_id: uuid.UUID
    title: str
    body: str
    channel: NotificationChannel
    priority: NotificationPriority
    payload: Dict[str, Any] = Field(default_factory=dict)
    action_url: Optional[str] = None
    is_read: bool = False
    read_at: Optional[str] = None


NotificationRead = Notification
