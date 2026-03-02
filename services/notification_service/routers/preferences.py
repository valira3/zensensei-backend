"""
ZenSensei Notification Service - Preferences Router

Endpoints:
  GET  /preferences/{user_id}  - Get notification preferences
  PUT  /preferences/{user_id}  - Update notification preferences
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_active_user

from services.notification_service.schemas import (
    NotificationPreferences,
    UpdatePreferencesRequest,
)
import services.notification_service.services.notification_service as notif_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get(
    "/{user_id}",
    summary="Get notification preferences for a user",
    response_class=ORJSONResponse,
)
async def get_preferences(
    user_id: str,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """
    Return the notification preferences for *user_id*.

    Only the authenticated user may access their own preferences.
    """
    if user_id != current_user.get("sub", current_user.get("user_id", current_user.get("id"))):
        raise HTTPException(status_code=403, detail="Access denied")

    prefs = await notif_svc.get_preferences(user_id)
    if prefs is None:
        # Return sensible defaults when no preferences have been saved yet
        prefs = NotificationPreferences(user_id=user_id)

    return ORJSONResponse(
        {
            "success": True,
            "data": prefs.model_dump() if hasattr(prefs, "model_dump") else dict(prefs),
        }
    )


@router.put(
    "/{user_id}",
    summary="Update notification preferences for a user",
    response_class=ORJSONResponse,
)
async def update_preferences(
    user_id: str,
    payload: UpdatePreferencesRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """
    Persist updated notification preferences for *user_id*.

    Only the authenticated user may update their own preferences.
    Performs a partial update: only keys supplied in the request body are changed.
    """
    if user_id != current_user.get("sub", current_user.get("user_id", current_user.get("id"))):
        raise HTTPException(status_code=403, detail="Access denied")

    updated = await notif_svc.update_preferences(
        user_id=user_id,
        updates=payload.model_dump(exclude_unset=True),
    )
    return ORJSONResponse(
        {
            "success": True,
            "data": updated.model_dump() if hasattr(updated, "model_dump") else dict(updated),
        }
    )
