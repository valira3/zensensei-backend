"""
ZenSensei Notification Service - Pydantic Schemas

Service-specific request/response models for notifications, preferences,
device registration, templates, and broadcast operations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import Field, field_validator

from shared.models.base import BaseModel, BaseResponse, PaginatedResponse, TimestampMixin
from shared.models.notifications import (
    NotificationChannel,
    NotificationPreferences,
    NotificationType,
)

__all__ = [
    # Notification send / receive
    "NotificationSendRequest",
    "NotificationRecord",
    "NotificationResponse",
    "NotificationListResponse",
    "UnreadCountResponse",
    "BroadcastRequest",
    "BroadcastResponse",
    # Preferences
    "NotificationPreferencesRequest",
    "NotificationPreferencesResponse",
    # Device registration
    "DeviceRegistrationRequest",
    "DeviceRegistrationResponse",
    "DevicePlatform",
    # Templates
    "TemplateCreateRequest",
    "TemplateUpdateRequest",
    "TemplateResponse",
    "TemplateListResponse",
    # Misc
    "MarkReadResponse",
    "DeleteNotificationResponse",
]

# ─── Device Registration ──────────────────────────────────────────────────────


class DevicePlatform(str):
    """Mobile / web push platform identifier."""

    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


class DeviceRegistrationRequest(BaseModel):
    """Register a push notification device token for a user."""

    user_id: str = Field(description="ZenSensei user ID")
    device_token: str = Field(description="FCM or APNs device/registration token")
    platform: str = Field(
        description="Device platform: ios | android | web",
        pattern="^(ios|android|web)$",
    )
    device_name: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Human-readable device label (e.g. 'John's iPhone 15')",
    )


class DeviceRegistrationResponse(BaseModel):
    """Confirmation of device token registration."""

    user_id: str
    device_token: str
    platform: str
    registered: bool = True
    message: str = "Device registered successfully"


# ─── Notification Send / Receive ──────────────────────────────────────────────


class NotificationSendRequest(BaseModel):
    """Payload to send a single notification (internal API)."""

    user_id: str = Field(description="Target user ID")
    notification_type: NotificationType = Field(description="Category of notification")
    channels: list[NotificationChannel] = Field(
        default_factory=lambda: [NotificationChannel.IN_APP],
        description="Delivery channels; defaults to in-app only",
    )
    title: str = Field(min_length=1, max_length=128)
    body: str = Field(min_length=1, max_length=1000)
    action_url: Optional[str] = Field(
        default=None,
        description="Deep-link URL opened on notification tap/click",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key-value metadata attached to the notification",
    )
    scheduled_at: Optional[datetime] = Field(
        default=None,
        description="UTC datetime for scheduled delivery; None = immediate",
    )
    template_id: Optional[str] = Field(
        default=None,
        description="Optional template ID to use for rendering title/body",
    )
    template_variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Variables to inject into the template",
    )


class NotificationRecord(TimestampMixin):
    """Full notification record as stored and returned by the API."""

    id: str
    user_id: str
    notification_type: NotificationType
    channels: list[NotificationChannel]
    title: str
    body: str
    action_url: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
    is_read: bool = False
    read_at: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    delivery_status: dict[str, str] = Field(
        default_factory=dict,
        description="Per-channel delivery status: channel -> 'sent' | 'failed' | 'pending'",
    )


# Alias for external API consumers
NotificationResponse = BaseResponse[NotificationRecord]
NotificationListResponse = PaginatedResponse[NotificationRecord]


class UnreadCountResponse(BaseModel):
    """Count of unread notifications for a user."""

    user_id: str
    unread_count: int = Field(ge=0)


class BroadcastRequest(BaseModel):
    """Send the same notification to multiple users."""

    user_ids: list[str] = Field(
        min_length=1,
        description="List of target user IDs; must contain at least one",
    )
    notification_type: NotificationType
    channels: list[NotificationChannel] = Field(
        default_factory=lambda: [NotificationChannel.IN_APP],
    )
    title: str = Field(min_length=1, max_length=128)
    body: str = Field(min_length=1, max_length=1000)
    action_url: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
    scheduled_at: Optional[datetime] = None
    template_id: Optional[str] = None
    template_variables: dict[str, Any] = Field(default_factory=dict)

    @field_validator("user_ids")
    @classmethod
    def deduplicate_user_ids(cls, v: list[str]) -> list[str]:
        """Remove duplicate user IDs silently."""
        seen: set[str] = set()
        return [uid for uid in v if not (uid in seen or seen.add(uid))]  # type: ignore[func-returns-value]


class BroadcastResponse(BaseModel):
    """Summary result of a broadcast send operation."""

    total_users: int
    queued: int
    failed: int
    notification_ids: list[str] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)


# ─── Preferences ──────────────────────────────────────────────────────────────


class FrequencyCapConfig(BaseModel):
    """Rate-limit configuration for a notification type."""

    max_per_hour: int = Field(default=5, ge=0)
    max_per_day: int = Field(default=20, ge=0)
    max_per_week: int = Field(default=50, ge=0)


class NotificationPreferencesRequest(BaseModel):
    """Update payload for user notification preferences."""

    # Global channel opt-outs
    push_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    in_app_enabled: Optional[bool] = None

    # Per-type opt-outs
    insight_notifications: Optional[bool] = None
    reminder_notifications: Optional[bool] = None
    relationship_notifications: Optional[bool] = None
    goal_milestone_notifications: Optional[bool] = None
    system_notifications: Optional[bool] = None
    social_notifications: Optional[bool] = None

    # Quiet hours (24-hour format in user's local timezone)
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[int] = Field(default=None, ge=0, le=23)
    quiet_hours_end: Optional[int] = Field(default=None, ge=0, le=23)
    timezone: Optional[str] = Field(
        default=None,
        max_length=64,
        description="IANA timezone string, e.g. 'America/New_York'",
    )

    # Preferred channels per type (overrides global)
    preferred_channels: dict[str, list[NotificationChannel]] = Field(
        default_factory=dict,
        description="Map of notification_type -> preferred channels",
    )

    # Frequency caps per type
    frequency_caps: dict[str, FrequencyCapConfig] = Field(
        default_factory=dict,
        description="Map of notification_type -> frequency cap config",
    )

    # Digest settings
    digest_enabled: Optional[bool] = None
    digest_frequency: Optional[str] = Field(
        default=None,
        pattern="^(daily|weekly)$",
        description="'daily' or 'weekly' digest cadence",
    )
    digest_time_hour: Optional[int] = Field(
        default=None,
        ge=0,
        le=23,
        description="Hour of day (user local time) to send digest",
    )


class NotificationPreferencesResponse(BaseModel):
    """Full notification preferences for a user."""

    user_id: str

    # Channel opt-ins
    push_enabled: bool = True
    email_enabled: bool = True
    sms_enabled: bool = False
    in_app_enabled: bool = True

    # Per-type opt-ins
    insight_notifications: bool = True
    reminder_notifications: bool = True
    relationship_notifications: bool = True
    goal_milestone_notifications: bool = True
    system_notifications: bool = True
    social_notifications: bool = True

    # Quiet hours
    quiet_hours_enabled: bool = True
    quiet_hours_start: int = 22
    quiet_hours_end: int = 8
    timezone: str = "UTC"

    # Preferred channels
    preferred_channels: dict[str, list[NotificationChannel]] = Field(default_factory=dict)

    # Frequency caps
    frequency_caps: dict[str, FrequencyCapConfig] = Field(default_factory=dict)

    # Digest
    digest_enabled: bool = False
    digest_frequency: str = "weekly"
    digest_time_hour: int = 9

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


# ─── Notification Templates ───────────────────────────────────────────────────


class TemplateChannelContent(BaseModel):
    """Channel-specific rendered content within a template."""

    title: str = Field(max_length=128)
    body: str = Field(max_length=2000)


class TemplateCreateRequest(BaseModel):
    """Payload to create a new notification template."""

    template_id: str = Field(
        min_length=1,
        max_length=64,
        pattern="^[a-z0-9_-]+$",
        description="Unique slug, e.g. 'weekly_summary' or 'goal_milestone'",
    )
    notification_type: NotificationType
    name: str = Field(min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=512)

    # Per-channel templates (use {{variable}} syntax)
    push: Optional[TemplateChannelContent] = None
    email: Optional[TemplateChannelContent] = None
    in_app: Optional[TemplateChannelContent] = None

    # Available variables documented for UI / API consumers
    variables: list[str] = Field(
        default_factory=list,
        description="Variable names accepted by this template, e.g. ['user_name', 'goal_title']",
    )
    is_active: bool = True


class TemplateUpdateRequest(BaseModel):
    """Partial update payload for a notification template."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=512)
    push: Optional[TemplateChannelContent] = None
    email: Optional[TemplateChannelContent] = None
    in_app: Optional[TemplateChannelContent] = None
    variables: Optional[list[str]] = None
    is_active: Optional[bool] = None


class TemplateResponse(TimestampMixin):
    """Full template record returned by the API."""

    template_id: str
    notification_type: NotificationType
    name: str
    description: Optional[str] = None
    push: Optional[TemplateChannelContent] = None
    email: Optional[TemplateChannelContent] = None
    in_app: Optional[TemplateChannelContent] = None
    variables: list[str] = Field(default_factory=list)
    is_active: bool = True


TemplateListResponse = PaginatedResponse[TemplateResponse]


# ─── Misc operation responses ─────────────────────────────────────────────────


class MarkReadResponse(BaseModel):
    """Confirmation of a mark-read operation."""

    updated_count: int = Field(ge=0)
    message: str = "Notifications marked as read"


class DeleteNotificationResponse(BaseModel):
    """Confirmation of notification deletion."""

    notification_id: str
    deleted: bool = True
    message: str = "Notification deleted"
