"""
ZenSensei Shared Models - User

Defines all user-related Pydantic models and enumerations.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import EmailStr, Field

from .base import TimestampedModel


class UserRole(str, Enum):
    """Application-level role assigned to a user."""

    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class UserStatus(str, Enum):
    """Account lifecycle state."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class UserCreate(TimestampedModel):
    """Payload for registering a new user."""

    email: EmailStr
    display_name: str = Field(..., min_length=1, max_length=120)
    password_hash: str = Field(
        ...,
        description="Bcrypt hash of the user’s password.  Never store plain text.",
    )
    role: UserRole = UserRole.MEMBER
    avatar_url: Optional[str] = None
    timezone: str = Field(default="UTC", max_length=64)
    locale: str = Field(default="en", max_length=10)


class UserUpdate(TimestampedModel):
    """Partial update payload for an existing user."""

    display_name: Optional[str] = Field(None, min_length=1, max_length=120)
    avatar_url: Optional[str] = None
    timezone: Optional[str] = Field(None, max_length=64)
    locale: Optional[str] = Field(None, max_length=10)
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None


class User(TimestampedModel):
    """Full User record including sensitive fields."""

    email: EmailStr
    display_name: str
    password_hash: str
    role: UserRole = UserRole.MEMBER
    status: UserStatus = UserStatus.ACTIVE
    avatar_url: Optional[str] = None
    timezone: str = "UTC"
    locale: str = "en"


class UserRead(TimestampedModel):
    """Safe read model – password_hash is never exposed."""

    email: EmailStr
    display_name: str
    role: UserRole
    status: UserStatus
    avatar_url: Optional[str] = None
    timezone: str
    locale: str


class UserProfile(TimestampedModel):
    """Minimal public profile shown to other users."""

    display_name: str
    avatar_url: Optional[str] = None
