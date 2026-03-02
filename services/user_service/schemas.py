"""
ZenSensei User Service - Schemas

Pydantic request/response schemas specific to the user service.
These extend or complement the shared models in shared/models/user.py.
"""

from __future__ import annotations

import sys
import os

_shared_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _shared_path not in sys.path:
    sys.path.insert(0, _shared_path)

from datetime import datetime
from typing import Any, Optional

from pydantic import EmailStr, Field, field_validator

from shared.models.base import BaseModel, BaseResponse
from shared.models.user import LifeStage, SubscriptionTier, UserResponse


# ─── Auth Schemas ─────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    """Payload for creating a new user account via /auth/register."""

    email: EmailStr = Field(description="User's primary email address")
    password: str = Field(
        min_length=12,
        max_length=128,
        description="Plain-text password; must meet complexity requirements",
    )
    display_name: str = Field(
        min_length=1,
        max_length=128,
        description="Publicly visible display name",
    )
    life_stage: LifeStage = Field(
        default=LifeStage.EARLY_CAREER,
        description="Current life stage for personalised recommendations",
    )


class LoginRequest(BaseModel):
    """Payload for /auth/login."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """JWT token pair returned on successful authentication."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class RegisterResponse(BaseModel):
    """Returned by /auth/register — token pair plus newly created user profile."""

    tokens: TokenResponse
    user: UserResponse
    email_verified: bool = False


class LoginResponse(BaseModel):
    """Returned by /auth/login — token pair plus user profile."""

    tokens: TokenResponse
    user: UserResponse


class RefreshRequest(BaseModel):
    """Payload for /auth/refresh."""

    refresh_token: str


class RefreshResponse(BaseModel):
    """New access + refresh token pair returned by /auth/refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="New access token lifetime in seconds")


class LogoutRequest(BaseModel):
    """Payload for /auth/logout — invalidates the given refresh token."""

    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    """Payload for /auth/forgot-password."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Payload for /auth/reset-password."""

    token: str = Field(description="Password reset token from email link")
    new_password: str = Field(
        min_length=12,
        max_length=128,
        description="New password; must meet complexity requirements",
    )


class EmailVerificationRequest(BaseModel):
    """Payload for /auth/verify-email."""

    token: str = Field(description="Email verification token")


class ResendVerificationRequest(BaseModel):
    """Payload for /auth/resend-verification."""

    email: str = Field(description="Email address to resend verification to")


class ChangePasswordRequest(BaseModel):
    """Payload for /auth/change-password."""

    current_password: str
    new_password: str


# ─── User Schemas ─────────────────────────────────────────────────────────────


class UserPreferencesResponse(BaseModel):
    """Per-user notification and privacy preferences."""

    user_id: str

    # Notification channels
    push_enabled: bool = True
    email_enabled: bool = True
    sms_enabled: bool = False
    in_app_enabled: bool = True

    # Per-type notifications
    insight_notifications: bool = True
    reminder_notifications: bool = True
    relationship_notifications: bool = True
    goal_milestone_notifications: bool = True
    system_notifications: bool = True
    social_notifications: bool = True

    # Quiet hours (24-hour, local timezone)
    quiet_hours_start: Optional[int] = Field(default=22, ge=0, le=23)
    quiet_hours_end: Optional[int] = Field(default=8, ge=0, le=23)

    # Privacy
    profile_visibility: str = Field(
        default="private",
        description="'public', 'friends', or 'private'",
    )
    data_sharing_enabled: bool = False
    analytics_enabled: bool = True


class UserPreferencesUpdate(BaseModel):
    """Partial update for user preferences — all fields optional."""

    push_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    in_app_enabled: Optional[bool] = None
    insight_notifications: Optional[bool] = None
    reminder_notifications: Optional[bool] = None
    relationship_notifications: Optional[bool] = None
    goal_milestone_notifications: Optional[bool] = None
    system_notifications: Optional[bool] = None
    social_notifications: Optional[bool] = None
    quiet_hours_start: Optional[int] = Field(default=None, ge=0, le=23)
    quiet_hours_end: Optional[int] = Field(default=None, ge=0, le=23)
    profile_visibility: Optional[str] = None
    data_sharing_enabled: Optional[bool] = None
    analytics_enabled: Optional[bool] = None


class SubscriptionResponse(BaseModel):
    """User subscription details."""

    user_id: str
    tier: SubscriptionTier
    is_premium: bool
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    auto_renew: bool = False
    billing_cycle: Optional[str] = Field(
        default=None,
        description="'monthly' or 'annual'",
    )
    features: list[str] = Field(
        default_factory=list,
        description="Feature flags enabled for this tier",
    )


class SubscriptionUpdateRequest(BaseModel):
    """Payload for updating the user's subscription tier."""

    tier: SubscriptionTier
    billing_cycle: Optional[str] = Field(
        default=None,
        description="'monthly' or 'annual'",
    )


class UserStatsResponse(BaseModel):
    """Aggregated statistics for a user profile."""

    user_id: str
    goals_count: int = Field(default=0, ge=0, description="Total goals created")
    active_goals_count: int = Field(default=0, ge=0, description="Goals with ACTIVE status")
    tasks_count: int = Field(default=0, ge=0, description="Total tasks created")
    completed_tasks_count: int = Field(default=0, ge=0, description="Tasks marked COMPLETED")
    insights_count: int = Field(default=0, ge=0, description="AI insights generated")
    current_streak_days: int = Field(default=0, ge=0, description="Consecutive active days")
    longest_streak_days: int = Field(default=0, ge=0, description="Longest recorded streak")
    member_since: Optional[datetime] = None
    last_active_at: Optional[datetime] = None


# ─── Onboarding Schemas ───────────────────────────────────────────────────────


class LifeStageRequest(BaseModel):
    """Payload for POST /onboarding/life-stage."""

    life_stage: LifeStage


class InterestsRequest(BaseModel):
    """Payload for POST /onboarding/interests."""

    interest_areas: list[str] = Field(
        min_length=1,
        description="List of interest area slugs, e.g. ['career', 'finance', 'health']",
    )

    @field_validator("interest_areas")
    @classmethod
    def validate_interests(cls, v: list[str]) -> list[str]:
        valid = {
            "career", "finance", "health", "education", "relationships",
            "personal_growth", "creativity", "travel", "family", "fitness",
            "nutrition", "mindfulness", "productivity", "social", "hobbies",
        }
        invalid = [i for i in v if i not in valid]
        if invalid:
            raise ValueError(f"Unknown interest areas: {invalid}. Valid: {sorted(valid)}")
        return v


class IntegrationsRequest(BaseModel):
    """Payload for POST /onboarding/integrations."""

    integration_ids: list[str] = Field(
        default_factory=list,
        description="Integration slugs to connect, e.g. ['google_calendar', 'gmail']",
    )


class OnboardingStatusResponse(BaseModel):
    """Current onboarding completion state for a user."""

    user_id: str
    is_complete: bool
    completed_steps: list[str] = Field(default_factory=list)
    pending_steps: list[str] = Field(default_factory=list)
    completion_percentage: float = Field(ge=0.0, le=100.0)
    life_stage_set: bool = False
    interests_set: bool = False
    integrations_connected: bool = False


# ─── Envelope helpers ─────────────────────────────────────────────────────────

# Typed response envelopes used by routers
AuthResponse = BaseResponse[RegisterResponse]

# Compatibility aliases used by the auth router
UpdateUserRequest = UserPreferencesUpdate
UpdateSubscriptionRequest = SubscriptionUpdateRequest
