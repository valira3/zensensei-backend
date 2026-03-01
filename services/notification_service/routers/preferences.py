"""
ZenSensei Notification Service - Preferences Router

Endpoints:
  GET /notifications/preferences/{user_id}  - Get user notification preferences
  PUT /notifications/preferences/{user_id}  - Update user notification preferences

Also exposes device registration endpoints:
  POST /notifications/devices/register     - Register a push device token
  DELETE /notifications/devices/unregister - Remove a push device token
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_active_user

from services.notification_service.schemas import (
    DeviceRegistrationRequest,
    DeviceRegistrationResponse,
    NotificationPreferencesRequest,
    NotificationPreferencesResponse,
)
import services.notification_service.services.notification_service as notif_svc
from services.notification_service.services.push_service import (
    register_device,
    unregister_device,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["preferences"])

# ─── Preferences endpoints ────────────────────────────────────────────────────


@router.get(
    "/preferences/{user_id}",
    summary="Get notification preferences for a user",
    response_class=ORJSONResponse,
)
async def get_preferences(
    user_id: str,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """
    Return the full notification preferences object for *user_id*.

    If no preferences have been saved yet, the response contains defaults.
    """
    prefs = await notif_svc.get_preferences(user_id)
    return ORJSONResponse(
        {
            "success": True,
            "data": _serialize_prefs(prefs),
        }
    )


@router.put(
    "/preferences/{user_id}",
    summary="Update notification preferences for a user",
    response_class=ORJSONResponse,
)
async def update_preferences(
    user_id: str,
    request: NotificationPreferencesRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """
    Partial-update the notification preferences for *user_id*.

    Only fields present in the request body (non-null) are applied.
    Returns the full updated preferences object.
    """
    updates = request.model_dump(exclude_none=True)

    # Validate frequency_cap entries if present
    if "frequency_caps" in updates:
        for notif_type_str, cap_data in updates["frequency_caps"].items():
            if isinstance(cap_data, dict):
                from services.notification_service.schemas import FrequencyCapConfig
                try:
                    FrequencyCapConfig(**cap_data)
                except Exception as exc:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Invalid frequency_cap for '{notif_type_str}': {exc}",
                    ) from exc

    updated = await notif_svc.update_preferences(user_id, updates)
    return ORJSONResponse(
        {
            "success": True,
            "message": "Preferences updated",
            "data": _serialize_prefs(updated),
        }
    )


# ─── Device registration ──────────────────────────────────────────────────────


@router.post(
    "/devices/register",
    summary="Register a push notification device token",
    status_code=status.HTTP_201_CREATED,
    response_class=ORJSONResponse,
)
async def register_push_device(
    request: DeviceRegistrationRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """
    Associate a device push token with a user account.

    Idempotent — re-registering the same token updates the record.
    """
    record = await register_device(
        user_id=request.user_id,
        device_token=request.device_token,
        platform=request.platform,
        device_name=request.device_name,
    )
    return ORJSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "data": DeviceRegistrationResponse(
                user_id=request.user_id,
                device_token=request.device_token,
                platform=request.platform,
            ).model_dump(),
        },
    )


@router.delete(
    "/devices/unregister",
    summary="Unregister a push notification device token",
    response_class=ORJSONResponse,
)
async def unregister_push_device(
    device_token: str,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """
    Remove a device token from the push notification registry.

    Returns 404 if the token is not found.
    """
    removed = await unregister_device(device_token)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device token not found: {device_token[:16]}…",
        )
    return ORJSONResponse(
        {
            "success": True,
            "message": "Device token unregistered",
        }
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _serialize_prefs(prefs: dict[str, Any]) -> dict[str, Any]:
    """Convert any datetime values in a preferences dict to ISO strings."""
    from datetime import datetime
    result = dict(prefs)
    for key, val in result.items():
        if isinstance(val, datetime):
            result[key] = val.isoformat()
    return result
