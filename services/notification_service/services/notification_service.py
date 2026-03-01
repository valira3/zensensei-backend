"""
ZenSensei Notification Service - Core Business Logic

Orchestrates notification routing, preference checking, quiet-hour enforcement,
smart delivery scheduling, and in-memory storage for development.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from shared.models.notifications import NotificationChannel, NotificationType

logger = logging.getLogger(__name__)

# ─── In-memory stores (development fallback) ─────────────────────────────────────────────

# { notification_id: NotificationRecord-dict }
_notifications: dict[str, dict[str, Any]] = {}

# { user_id: NotificationPreferences-dict }
_preferences: dict[str, dict[str, Any]] = {}

# Frequency tracking: { user_id: { notification_type: [delivered_at ISO strings] } }
_frequency_log: dict[str, dict[str, list[str]]] = {}


# ─── Seed data ───────────────────────────────────────────────────────────────────

def _seed_mock_notifications() -> None:
    """Populate in-memory store with realistic mock notifications for demo."""
    from services.notification_service.services.notification_service import _notifications

    now = datetime.now(tz=timezone.utc)
    mock_user = "user_demo_001"

    mock_data: list[dict[str, Any]] = [
        {
            "id": "notif_001",
            "user_id": mock_user,
            "notification_type": NotificationType.INSIGHT,
            "channels": [NotificationChannel.IN_APP],
            "title": "Sleep affects your focus score",
            "body": (
                "ZenSensei detected that on days you sleep less than 7 hours, "
                "your focus score drops by an average of 23%."
            ),
            "action_url": "/insights/sleep-focus-correlation",
            "data": {"insight_id": "ins_001", "correlation": "0.73"},
            "is_read": False,
            "read_at": None,
            "scheduled_at": None,
            "delivered_at": now.isoformat(),
            "delivery_status": {"in_app": "sent"},
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "notif_002",
            "user_id": mock_user,
            "notification_type": NotificationType.GOAL_MILESTONE,
            "channels": [NotificationChannel.IN_APP, NotificationChannel.PUSH],
            "title": "50% progress on 'Run a 5K'",
            "body": "You've reached the halfway point on your running goal. Keep up the momentum!",
            "action_url": "/goals/run-5k",
            "data": {"goal_id": "goal_001", "progress_pct": 50},
            "is_read": True,
            "read_at": now.isoformat(),
            "scheduled_at": None,
            "delivered_at": now.isoformat(),
            "delivery_status": {"in_app": "sent", "push": "sent"},
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "notif_003",
            "user_id": mock_user,
            "notification_type": NotificationType.REMINDER,
            "channels": [NotificationChannel.IN_APP],
            "title": "Daily meditation reminder",
            "body": "You haven't logged your meditation session today. 5 minutes is all it takes!",
            "action_url": "/log/meditation",
            "data": {"habit_id": "habit_002", "streak": 6},
            "is_read": False,
            "read_at": None,
            "scheduled_at": None,
            "delivered_at": now.isoformat(),
            "delivery_status": {"in_app": "sent"},
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "notif_004",
            "user_id": mock_user,
            "notification_type": NotificationType.SYSTEM,
            "channels": [NotificationChannel.IN_APP, NotificationChannel.EMAIL],
            "title": "Welcome to ZenSensei!",
            "body": "Your AI coach is ready. Complete your profile to unlock personalised insights.",
            "action_url": "/onboarding",
            "data": {"step": "profile_setup"},
            "is_read": True,
            "read_at": now.isoformat(),
            "scheduled_at": None,
            "delivered_at": now.isoformat(),
            "delivery_status": {"in_app": "sent", "email": "sent"},
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "notif_005",
            "user_id": mock_user,
            "notification_type": NotificationType.RELATIONSHIP,
            "channels": [NotificationChannel.IN_APP],
            "title": "Connection found: Exercise → Mood",
            "body": (
                "ZenSensei noticed a strong positive link between your morning workouts "
                "and elevated mood scores throughout the day."
            ),
            "action_url": "/graph/exercise-mood",
            "data": {"entity_a": "Exercise", "entity_b": "Mood", "strength": "0.81"},
            "is_read": False,
            "read_at": None,
            "scheduled_at": None,
            "delivered_at": now.isoformat(),
            "delivery_status": {"in_app": "sent"},
            "created_at": now,
            "updated_at": now,
        },
    ]

    for item in mock_data:
        _notifications[item["id"]] = item


# ─── Default preferences ───────────────────────────────────────────────────────────────


def _default_preferences(user_id: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "push_enabled": True,
        "email_enabled": True,
        "sms_enabled": False,
        "in_app_enabled": True,
        "insight_notifications": True,
        "reminder_notifications": True,
        "relationship_notifications": True,
        "goal_milestone_notifications": True,
        "system_notifications": True,
        "social_notifications": True,
        "quiet_hours_enabled": True,
        "quiet_hours_start": 22,
        "quiet_hours_end": 8,
        "timezone": "UTC",
        "preferred_channels": {},
        "frequency_caps": {},
        "digest_enabled": False,
        "digest_frequency": "weekly",
        "digest_time_hour": 9,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


# ─── Preference helpers ─────────────────────────────────────────────────────────────


def _get_preferences(user_id: str) -> dict[str, Any]:
    """Return stored preferences or defaults."""
    return _preferences.get(user_id) or _default_preferences(user_id)


async def get_preferences(user_id: str) -> dict[str, Any]:
    """Return the notification preferences for a user."""
    return _get_preferences(user_id)


async def update_preferences(user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge *updates* into the user's preferences and persist."""
    current = _get_preferences(user_id)
    current.update({k: v for k, v in updates.items() if v is not None})
    current["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
    _preferences[user_id] = current
    return current


# ─── Preference / quiet-hour checks ───────────────────────────────────────────────────


async def check_preferences(user_id: str, notification_type: NotificationType) -> bool:
    """
    Return True if the user has opted in to this notification type on at least
    one channel.

    Checks both global channel opt-outs and per-type opt-outs.
    """
    prefs = _get_preferences(user_id)

    type_flag_map = {
        NotificationType.INSIGHT: "insight_notifications",
        NotificationType.REMINDER: "reminder_notifications",
        NotificationType.RELATIONSHIP: "relationship_notifications",
        NotificationType.GOAL_MILESTONE: "goal_milestone_notifications",
        NotificationType.SYSTEM: "system_notifications",
        NotificationType.SOCIAL: "social_notifications",
    }

    flag = type_flag_map.get(notification_type)
    if flag and not prefs.get(flag, True):
        logger.debug(
            "check_preferences: user=%s opted out of %s", user_id, notification_type
        )
        return False

    # At least one channel must be enabled
    any_channel = any([
        prefs.get("push_enabled", True),
        prefs.get("email_enabled", True),
        prefs.get("in_app_enabled", True),
    ])
    return any_channel


async def check_quiet_hours(user_id: str) -> bool:
    """
    Return True if the user is currently in quiet hours (notification should
    be suppressed or delayed).

    Handles midnight-crossing quiet windows (e.g. 22:00–08:00).
    """
    prefs = _get_preferences(user_id)
    if not prefs.get("quiet_hours_enabled", True):
        return False

    now_hour = datetime.now(tz=timezone.utc).hour  # simplified — use user TZ in production
    start = prefs.get("quiet_hours_start", 22)
    end = prefs.get("quiet_hours_end", 8)

    if start <= end:
        # Normal window e.g. 09:00–17:00
        in_quiet = start <= now_hour <= end
    else:
        # Midnight-crossing window e.g. 22:00–08:00
        in_quiet = now_hour >= start or now_hour <= end

    if in_quiet:
        logger.debug("check_quiet_hours: user=%s is in quiet hours (hour=%d)", user_id, now_hour)
    return in_quiet


async def smart_delivery(user_id: str) -> datetime:
    """
    Determine the optimal delivery time for a notification based on the user's
    activity patterns and quiet-hour configuration.

    Heuristic: if currently in quiet hours, schedule at quiet_hours_end; otherwise
    send immediately.

    In a production system this would use ML-derived activity windows stored in
    the analytics service.

    Returns:
        UTC datetime of the recommended delivery time.
    """
    prefs = _get_preferences(user_id)
    now = datetime.now(tz=timezone.utc)

    in_quiet = await check_quiet_hours(user_id)
    if not in_quiet:
        return now

    # Schedule at the end of quiet hours (next occurrence)
    end_hour = prefs.get("quiet_hours_end", 8)
    scheduled = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if scheduled <= now:
        # Already past today's quiet-end — schedule for tomorrow
        from datetime import timedelta
        scheduled = scheduled + timedelta(days=1)

    logger.debug(
        "smart_delivery: user=%s in quiet hours, scheduled at %s", user_id, scheduled
    )
    return scheduled


# ─── Effective channels ──────────────────────────────────────────────────────────────


def _resolve_channels(
    user_id: str,
    requested_channels: list[NotificationChannel],
    notification_type: NotificationType,
) -> list[NotificationChannel]:
    """
    Intersect the requested channels with the user's preferences.

    Respects:
    - Global per-channel opt-outs.
    - Per-type preferred channel overrides.
    """
    prefs = _get_preferences(user_id)
    channel_flags = {
        NotificationChannel.PUSH: prefs.get("push_enabled", True),
        NotificationChannel.EMAIL: prefs.get("email_enabled", True),
        NotificationChannel.SMS: prefs.get("sms_enabled", False),
        NotificationChannel.IN_APP: prefs.get("in_app_enabled", True),
    }

    # Check if user has per-type preferred channels
    preferred = prefs.get("preferred_channels", {}).get(str(notification_type))
    effective_requested = preferred if preferred else requested_channels

    return [ch for ch in effective_requested if channel_flags.get(ch, False)]


# ─── Core send operations ─────────────────────────────────────────────────────────────


async def send_notification(
    user_id: str,
    notification_type: NotificationType,
    channels: list[NotificationChannel],
    title: str,
    body: str,
    action_url: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
    skip_preference_check: bool = False,
) -> Optional[dict[str, Any]]:
    """
    Route a notification to the appropriate delivery channel(s) for one user.

    Checks preferences and quiet hours before dispatching.

    Returns:
        The stored notification record, or None if suppressed.
    """
    if not skip_preference_check:
        allowed = await check_preferences(user_id, notification_type)
        if not allowed:
            logger.info(
                "send_notification: suppressed (user preference) user=%s type=%s",
                user_id, notification_type,
            )
            return None

    effective_channels = _resolve_channels(user_id, channels, notification_type)
    if not effective_channels:
        logger.info(
            "send_notification: no effective channels for user=%s type=%s",
            user_id, notification_type,
        )
        return None

    now = datetime.now(tz=timezone.utc)
    notif_id = f"notif_{uuid.uuid4().hex[:12]}"
    delivery_status: dict[str, str] = {}

    # ── Dispatch to each channel ──────────────────────────────────────────────────
    for channel in effective_channels:
        try:
            if channel == NotificationChannel.IN_APP:
                delivery_status["in_app"] = "sent"

            elif channel == NotificationChannel.PUSH:
                from services.notification_service.services.push_service import send_push_to_user
                results = await send_push_to_user(user_id, title, body, data)
                delivery_status["push"] = "sent" if any(r.get("success") for r in results) else "failed"

            elif channel == NotificationChannel.EMAIL:
                # Email requires the user's email address — looked up via user service in production
                # For dev, skip if no email address provided in data
                user_email = (data or {}).get("user_email")
                if user_email:
                    from services.notification_service.services.email_service import send_email
                    result = await send_email(
                        to=user_email,
                        subject=title,
                        text_body=body,
                    )
                    delivery_status["email"] = "sent" if result.get("success") else "failed"
                else:
                    delivery_status["email"] = "skipped_no_address"

            elif channel == NotificationChannel.SMS:
                # SMS not yet implemented
                delivery_status["sms"] = "pending"

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "send_notification: channel dispatch failed channel=%s user=%s: %s",
                channel, user_id, exc,
            )
            delivery_status[channel.value.lower()] = "failed"

    # ── Store notification ─────────────────────────────────────────────────────
    record: dict[str, Any] = {
        "id": notif_id,
        "user_id": user_id,
        "notification_type": notification_type,
        "channels": effective_channels,
        "title": title,
        "body": body,
        "action_url": action_url,
        "data": data or {},
        "is_read": False,
        "read_at": None,
        "scheduled_at": None,
        "delivered_at": now.isoformat(),
        "delivery_status": delivery_status,
        "created_at": now,
        "updated_at": now,
    }
    _notifications[notif_id] = record

    # Track for frequency caps
    _frequency_log.setdefault(user_id, {}).setdefault(str(notification_type), []).append(
        now.isoformat()
    )

    logger.info(
        "send_notification: stored id=%s user=%s type=%s channels=%s",
        notif_id, user_id, notification_type, effective_channels,
    )
    return record


async def batch_send(
    user_ids: list[str],
    notification_type: NotificationType,
    channels: list[NotificationChannel],
    title: str,
    body: str,
    action_url: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Send the same notification to multiple users (broadcast).

    Returns a summary of successes and failures.
    """
    queued = 0
    failed = 0
    notification_ids: list[str] = []
    errors: list[dict[str, str]] = []

    for user_id in user_ids:
        try:
            record = await send_notification(
                user_id=user_id,
                notification_type=notification_type,
                channels=channels,
                title=title,
                body=body,
                action_url=action_url,
                data=data,
            )
            if record:
                queued += 1
                notification_ids.append(record["id"])
            else:
                # Suppressed by preferences — not a failure
                queued += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append({"user_id": user_id, "error": str(exc)})
            logger.error("batch_send: failed for user=%s: %s", user_id, exc)

    return {
        "total_users": len(user_ids),
        "queued": queued,
        "failed": failed,
        "notification_ids": notification_ids,
        "errors": errors,
    }


# ─── Notification fetch / mutation ────────────────────────────────────────────────────────


async def get_notifications(
    user_id: str,
    notification_type: Optional[NotificationType] = None,
    is_read: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """
    Return a paginated list of notifications for a user.

    Filters by type and read status if provided.
    Results are sorted newest-first.
    """
    all_user_notifs = [n for n in _notifications.values() if n["user_id"] == user_id]

    if notification_type is not None:
        all_user_notifs = [n for n in all_user_notifs if n["notification_type"] == notification_type]
    if is_read is not None:
        all_user_notifs = [n for n in all_user_notifs if n["is_read"] == is_read]

    # Sort newest-first
    all_user_notifs.sort(
        key=lambda n: n.get("delivered_at") or n["created_at"].isoformat()
        if isinstance(n["created_at"], datetime) else n["created_at"],
        reverse=True,
    )

    total = len(all_user_notifs)
    start = (page - 1) * page_size
    end = start + page_size
    items = all_user_notifs[start:end]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_unread_count(user_id: str) -> int:
    """Return the number of unread notifications for a user."""
    return sum(
        1 for n in _notifications.values()
        if n["user_id"] == user_id and not n["is_read"]
    )


async def mark_read(notification_id: str) -> Optional[dict[str, Any]]:
    """
    Mark a single notification as read.

    Returns the updated record, or None if not found.
    """
    record = _notifications.get(notification_id)
    if not record:
        return None

    now = datetime.now(tz=timezone.utc)
    record["is_read"] = True
    record["read_at"] = now.isoformat()
    record["updated_at"] = now
    logger.debug("mark_read: notification_id=%s", notification_id)
    return record


async def mark_all_read(user_id: str) -> int:
    """
    Mark all notifications for a user as read.

    Returns the number of notifications updated.
    """
    now = datetime.now(tz=timezone.utc)
    updated = 0
    for record in _notifications.values():
        if record["user_id"] == user_id and not record["is_read"]:
            record["is_read"] = True
            record["read_at"] = now.isoformat()
            record["updated_at"] = now
            updated += 1
    logger.debug("mark_all_read: user=%s updated=%d", user_id, updated)
    return updated


async def delete_notification(notification_id: str) -> bool:
    """
    Delete a notification by ID.

    Returns True if found and deleted, False otherwise.
    """
    if notification_id in _notifications:
        del _notifications[notification_id]
        logger.debug("delete_notification: notification_id=%s", notification_id)
        return True
    return False
