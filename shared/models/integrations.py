"""
ZenSensei Shared Models - Integrations

Pydantic schemas for third-party Integration domain objects.

An ``Integration`` records a connection between a ZenSensei user account
and an external service (e.g. Google Calendar, Slack, Jira).  The
``credentials`` field stores an *encrypted* token blob; the plain-text
credential is never held in this model.

Schema variants
---------------
``IntegrationCreate``  – payload accepted when a user connects a new service
``Integration``        – full internal representation
``IntegrationRead``    – safe API response model (credentials omitted)
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional

from pydantic import Field

from .base import TimestampedModel


class IntegrationProvider(str, Enum):
    """Supported third-party integration providers."""

    GOOGLE_CALENDAR = "google_calendar"
    SLACK = "slack"
    JIRA = "jira"
    GITHUB = "github"
    NOTION = "notion"
    TODOIST = "todoist"
    ASANA = "asana"
    LINEAR = "linear"


class IntegrationStatus(str, Enum):
    """Connection lifecycle state."""

    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    REVOKED = "revoked"


class IntegrationCreate(TimestampedModel):
    """Payload for linking a new third-party service."""

    user_id: uuid.UUID
    provider: IntegrationProvider
    credentials: str = Field(
        ...,
        description="AES-256-GCM encrypted credential blob (base64-encoded).",
    )
    scopes: list[str] = Field(default_factory=list)


class Integration(TimestampedModel):
    """Full Integration record including encrypted credentials."""

    user_id: uuid.UUID
    provider: IntegrationProvider
    status: IntegrationStatus = IntegrationStatus.ACTIVE
    credentials: str
    scopes: list[str] = Field(default_factory=list)
    last_synced_at: Optional[str] = None


class IntegrationRead(TimestampedModel):
    """Safe read model – credentials are never exposed to API consumers."""

    user_id: uuid.UUID
    provider: IntegrationProvider
    status: IntegrationStatus
    scopes: list[str]
    last_synced_at: Optional[str] = None
