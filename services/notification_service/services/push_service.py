"""
ZenSensei Notification Service - Push Notification Service

Sends push notifications via Firebase Cloud Messaging (FCM).
Falls back to a mock/log-only mode when FCM credentials are not configured.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ─── Device token store (in-memory for development) ──────────────────────────────────

# Structure: { user_id: [ {device_token, platform, device_name, registered_at} ] }
_device_registry: dict[str, list[dict[str, Any]]] = {}

# Reverse index: device_token -> user_id
_token_to_user: dict[str, str] = {}

# ─── FCM client (lazy-initialised) ────────────────────────────────────────────────


def _is_mock_mode() -> bool:
    """Return True when FCM credentials are absent (development mode)."""
    from shared.config import get_config
    cfg = get_config()
    creds_path = cfg.firebase_credentials_path
    return not os.path.exists(creds_path)


@lru_cache(maxsize=1)
def _get_fcm_app() -> Optional[Any]:
    """
    Lazily initialise the Firebase Admin SDK.

    Returns the default firebase_admin App on success, None in mock mode.
    """
    if _is_mock_mode():
        logger.info("PushService: FCM credentials not found — running in mock mode")
        return None

    try:
        import firebase_admin
        from firebase_admin import credentials as fb_creds

        from shared.config import get_config
        cfg = get_config()

        if firebase_admin._DEFAULT_APP_NAME in firebase_admin._apps:
            return firebase_admin.get_app()

        cred = fb_creds.Certificate(cfg.firebase_credentials_path)
        app = firebase_admin.initialize_app(
            cred,
            {"projectId": cfg.firebase_project_id},
        )
        logger.info("PushService: Firebase Admin SDK initialised (project=%s)", cfg.firebase_project_id)
        return app
    except Exception as exc:
        logger.warning("PushService: Failed to init Firebase Admin SDK: %s — falling back to mock", exc)
        return None


# ─── Core push operations ───────────────────────────────────────────────────────────


async def register_device(
    user_id: str,
    device_token: str,
    platform: str,
    device_name: Optional[str] = None,
) -> dict[str, Any]:
    """
    Associate a device token with a user.

    Idempotent: re-registering the same token updates the record.
    """
    if device_token in _token_to_user:
        old_user = _token_to_user[device_token]
        if old_user != user_id:
            # Token migrated to a new user — clean up old association
            _device_registry[old_user] = [
                d for d in _device_registry.get(old_user, [])
                if d["device_token"] != device_token
            ]

    _token_to_user[device_token] = user_id

    devices = _device_registry.setdefault(user_id, [])
    # Remove any existing entry for this token
    _device_registry[user_id] = [d for d in devices if d["device_token"] != device_token]

    record = {
        "device_token": device_token,
        "platform": platform,
        "device_name": device_name or f"{platform.capitalize()} device",
        "registered_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    _device_registry[user_id].append(record)

    logger.debug("PushService: Registered device for user=%s platform=%s", user_id, platform)
    return record


async def unregister_device(device_token: str) -> bool:
    """
    Remove a device token from the registry.

    Returns True if the token was found and removed, False otherwise.
    """
    user_id = _token_to_user.pop(device_token, None)
    if user_id is None:
        logger.debug("PushService: unregister_device — token not found")
        return False

    _device_registry[user_id] = [
        d for d in _device_registry.get(user_id, [])
        if d["device_token"] != device_token
    ]
    logger.debug("PushService: Unregistered device token for user=%s", user_id)
    return True


def get_user_devices(user_id: str) -> list[dict[str, Any]]:
    """Return all registered device records for a user."""
    return _device_registry.get(user_id, [])


async def send_push(
    device_token: str,
    title: str,
    body: str,
    data: Optional[dict[str, Any]] = None,
    badge_count: Optional[int] = None,
    sound: str = "default",
) -> dict[str, Any]:
    """
    Send a push notification to a single device token.

    In mock mode (no FCM credentials), logs the notification and returns a
    synthetic success response.

    Args:
        device_token: FCM registration token or APNs device token.
        title: Notification title.
        body: Notification body text.
        data: Optional key-value data payload.
        badge_count: Optional iOS badge count.
        sound: Notification sound name (default = "default").

    Returns:
        Dict with ``success``, ``message_id``, and delivery metadata.
    """
    app = _get_fcm_app()
    payload_data = {k: str(v) for k, v in (data or {}).items()}

    if app is None:
        # ── Mock mode ──────────────────────────────────────────────────
        mock_id = f"mock-{device_token[:8]}-{int(datetime.now(tz=timezone.utc).timestamp())}"
        logger.info(
            "PushService [MOCK]: send_push token=%.12s… title='%s'",
            device_token,
            title,
        )
        return {
            "success": True,
            "message_id": mock_id,
            "mock": True,
            "token": device_token,
            "title": title,
            "body": body,
        }

    # ── Live FCM ────────────────────────────────────────────────────────
    try:
        from firebase_admin import messaging

        notification = messaging.Notification(title=title, body=body)
        android_config = messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                title=title,
                body=body,
                sound=sound,
            ),
        )
        apns_config = messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    alert=messaging.ApsAlert(title=title, body=body),
                    sound=sound,
                    badge=badge_count,
                )
            )
        )

        message = messaging.Message(
            notification=notification,
            data=payload_data,
            token=device_token,
            android=android_config,
            apns=apns_config,
        )

        message_id = messaging.send(message)
        logger.info("PushService: sent FCM message id=%s to token=%.12s…", message_id, device_token)
        return {
            "success": True,
            "message_id": message_id,
            "mock": False,
            "token": device_token,
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("PushService: FCM send failed for token=%.12s…: %s", device_token, exc)
        return {
            "success": False,
            "error": str(exc),
            "token": device_token,
        }


async def send_push_to_user(
    user_id: str,
    title: str,
    body: str,
    data: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """
    Send a push notification to all registered devices of a user.

    Silently skips users with no registered devices.

    Returns:
        List of per-device send results.
    """
    devices = get_user_devices(user_id)
    if not devices:
        logger.debug("PushService: No devices registered for user=%s", user_id)
        return []

    results = []
    for device in devices:
        result = await send_push(
            device_token=device["device_token"],
            title=title,
            body=body,
            data=data,
        )
        results.append(result)
    return results


async def send_multicast_push(
    device_tokens: list[str],
    title: str,
    body: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Send the same push notification to multiple device tokens at once.

    Uses FCM batch sending when available; falls back to per-token mock responses.

    Returns:
        Summary dict with success_count, failure_count, and responses list.
    """
    if not device_tokens:
        return {"success_count": 0, "failure_count": 0, "responses": []}

    app = _get_fcm_app()
    payload_data = {k: str(v) for k, v in (data or {}).items()}

    if app is None:
        # Mock: succeed everything
        responses = [
            {
                "success": True,
                "message_id": f"mock-{tok[:8]}-{i}",
                "mock": True,
                "token": tok,
            }
            for i, tok in enumerate(device_tokens)
        ]
        logger.info(
            "PushService [MOCK]: multicast_push %d tokens title='%s'",
            len(device_tokens),
            title,
        )
        return {
            "success_count": len(device_tokens),
            "failure_count": 0,
            "responses": responses,
        }

    try:
        from firebase_admin import messaging

        messages = [
            messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data=payload_data,
                token=token,
            )
            for token in device_tokens
        ]

        batch_response = messaging.send_each(messages)
        responses = []
        for i, resp in enumerate(batch_response.responses):
            responses.append({
                "success": resp.success,
                "message_id": resp.message_id if resp.success else None,
                "error": str(resp.exception) if resp.exception else None,
                "token": device_tokens[i],
            })

        return {
            "success_count": batch_response.success_count,
            "failure_count": batch_response.failure_count,
            "responses": responses,
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("PushService: multicast FCM send failed: %s", exc)
        return {
            "success_count": 0,
            "failure_count": len(device_tokens),
            "error": str(exc),
            "responses": [],
        }
