"""
ZenSensei Shared Models Package

This package exposes all Pydantic / SQLModel data models used across the
ZenSensei micro-service fleet.  Import from here rather than from the
individual sub-modules so that consumers are insulated from internal
reorganisation.

Public surface
--------------
Base
    ``TimestampedModel`` – abstract base with ``created_at`` / ``updated_at``.
    ``UUIDModel``       – abstract base with a UUID primary key.

Goals
    ``Goal``, ``GoalCreate``, ``GoalUpdate``, ``GoalRead``

Graph
    ``Node``, ``Edge``, ``GraphSnapshot``

Insights
    ``Insight``, ``InsightCreate``, ``InsightRead``

Integrations
    ``Integration``, ``IntegrationCreate``, ``IntegrationRead``

Notifications
    ``Notification``, ``NotificationCreate``, ``NotificationRead``

Tasks
    ``Task``, ``TaskCreate``, ``TaskUpdate``, ``TaskRead``

User
    ``User``, ``UserCreate``, ``UserUpdate``, ``UserRead``, ``UserProfile``
"""

from .base import TimestampedModel, UUIDModel
from .goals import Goal, GoalCreate, GoalRead, GoalUpdate
from .graph import Edge, GraphSnapshot, Node
from .insights import Insight, InsightCreate, InsightRead
from .integrations import Integration, IntegrationCreate, IntegrationRead
from .notifications import Notification, NotificationCreate, NotificationRead
from .tasks import Task, TaskCreate, TaskRead, TaskUpdate
from .user import User, UserCreate, UserProfile, UserRead, UserUpdate

__all__ = [
    # Base
    "TimestampedModel",
    "UUIDModel",
    # Goals
    "Goal",
    "GoalCreate",
    "GoalRead",
    "GoalUpdate",
    # Graph
    "Edge",
    "GraphSnapshot",
    "Node",
    # Insights
    "Insight",
    "InsightCreate",
    "InsightRead",
    # Integrations
    "Integration",
    "IntegrationCreate",
    "IntegrationRead",
    # Notifications
    "Notification",
    "NotificationCreate",
    "NotificationRead",
    # Tasks
    "Task",
    "TaskCreate",
    "TaskRead",
    "TaskUpdate",
    # User
    "User",
    "UserCreate",
    "UserProfile",
    "UserRead",
    "UserUpdate",
]
