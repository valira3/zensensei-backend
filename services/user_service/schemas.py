"""
ZenSensei User Service - Request / Response Schemas

All Pydantic v2 models used by the user-service routers.
Kept in a single module to simplify imports and avoid circular deps.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator

from shared.models.user import LifeStage, UserResponse


# ─── Auth ──────────────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    """Payload for POST /auth/register."""

    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(
        ...,
        min_length=12,
        description="Password (min 12 chars, must include upper/lower/digit/symbol)",
    )
    display_name: str = Field(
        ..., min_length=2, max_length=80, description="Publicly visible display name"
    )
    timezone: str = Field(
        default="UTC", description="IANA timezone string, e.g. 'America/New_York'"
    )

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        errors: list[str] = []
        if not any(c.isupper() for c in v):
            errors.append("at least one uppercase letter")
        if not any(c.islower() for c in v):
            errors.append("at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            errors.append("at least one digit")
        if not any(c in "!@#$%^&*()-_=+[]{}|;:',.<>?/`~" for c in v):
            errors.append("at least one special character")
        if errors:
            raise ValueError(f"Password must contain: {', '.join(errors)}")
        return v


class RegisterResponse(BaseModel):
    """Response body for POST /auth/register."""

    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    """Payload for POST /auth/login."""

    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Response body for POST /auth/login."""

    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Payload for POST /auth/refresh."""

    refresh_token: str


class RefreshResponse(BaseModel):
    """Response body for POST /auth/refresh."""

    access_token: str
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    """Payload for POST /auth/logout."""

    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    """Payload for POST /auth/forgot-password."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Payload for POST /auth/reset-password."""

    token: str
    new_password: str = Field(
        ...,
        min_length=12,
        description="New password (same strength requirements as registration)",
    )

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        errors: list[str] = []
        if not any(c.isupper() for c in v):
            errors.append("at least one uppercase letter")
        if not any(c.islower() for c in v):
            errors.append("at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            errors.append("at least one digit")
        if not any(c in "!@#$%^&*()-_=+[]{}|;:',.<>?/`~" for c in v):
            errors.append("at least one special character")
        if errors:
            raise ValueError(f"Password must contain: {', '.join(errors)}")
        return v


# ─── Users ──────────────────────────────────────────────────────────────────────


class UpdateProfileRequest(BaseModel):
    """Payload for PATCH /users/me — all fields optional."""

    display_name: str | None = Field(None, min_length=2, max_length=80)
    bio: str | None = Field(None, max_length=500)
    avatar_url: str | None = Field(None, description="URL to new profile avatar")
    timezone: str | None = None
    notification_preferences: dict[str, Any] | None = None


# ─── Onboarding ────────────────────────────────────────────────────────────


class LifeStageRequest(BaseModel):
    """Payload for POST /onboarding/life-stage."""

    life_stage: LifeStage


class InterestsRequest(BaseModel):
    """Payload for POST /onboarding/interests."""

    interest_areas: list[str] = Field(
        ...,
        min_length=1,
        description="At least one interest area must be provided",
    )


class IntegrationsRequest(BaseModel):
    """Payload for POST /onboarding/integrations."""

    integrations: list[str] = Field(
        default_factory=list,
        description="List of integration provider identifiers to register",
    )


class OnboardingStatusResponse(BaseModel):
    """Response body for onboarding status endpoints."""

    user_id: str
    is_complete: bool
    completed_steps: list[str]
    pending_steps: list[str]
    completion_percentage: float
    life_stage_set: bool
    interests_set: bool
    integrations_connected: bool
