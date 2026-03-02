"""
ZenSensei User Service - Users Router

Endpoints:
  GET    /users/me           - Get authenticated user's profile
  PUT    /users/me           - Update authenticated user's profile
  DELETE /users/me           - Delete authenticated user's account
  GET    /users/{user_id}    - Get another user's public profile (admin or self)
  PUT    /users/{user_id}/subscription - Update subscription tier (admin)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_active_user

from services.user_service.schemas import (
    UpdateUserRequest,
    UpdateSubscriptionRequest,
)
import services.user_service.services.user_service as user_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


# ─── /me endpoints ───────────────────────────────────────────────────────────


@router.get(
    "/me",
    summary="Get authenticated user's profile",
    response_class=ORJSONResponse,
)
async def get_me(
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """Return the full profile of the currently authenticated user."""
    user_id = current_user.get("sub", current_user.get("user_id", current_user.get("id")))
    user = await user_svc.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return ORJSONResponse({"success": True, "data": user})


@router.put(
    "/me",
    summary="Update authenticated user's profile",
    response_class=ORJSONResponse,
)
async def update_me(
    payload: UpdateUserRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """Update the profile fields of the currently authenticated user."""
    user_id = current_user.get("sub", current_user.get("user_id", current_user.get("id")))
    updated = await user_svc.update_user(
        user_id=user_id,
        updates=payload.model_dump(exclude_unset=True),
    )
    return ORJSONResponse({"success": True, "data": updated})


@router.delete(
    "/me",
    summary="Delete the authenticated user's account",
    response_class=ORJSONResponse,
)
async def delete_me(
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """Permanently delete the authenticated user's account and all associated data."""
    user_id = current_user.get("sub", current_user.get("user_id", current_user.get("id")))
    await user_svc.delete_user(user_id)
    return ORJSONResponse({"success": True, "message": "Account deleted successfully"})


# ─── /users/{user_id} endpoints ───────────────────────────────────────────────


@router.get(
    "/{user_id}",
    summary="Get a user's profile (self or admin)",
    response_class=ORJSONResponse,
)
async def get_user(
    user_id: str,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """Return the profile for *user_id*. Only the owner or an admin may access it."""
    caller_id = current_user.get("sub", current_user.get("user_id", current_user.get("id")))
    is_admin = current_user.get("role") == "admin"
    if caller_id != user_id and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    user = await user_svc.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return ORJSONResponse({"success": True, "data": user})


@router.put(
    "/{user_id}/subscription",
    summary="Update a user's subscription tier (admin only)",
    response_class=ORJSONResponse,
)
async def update_subscription(
    user_id: str,
    payload: UpdateSubscriptionRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """Update the subscription tier for *user_id*. Requires admin role."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    updated = await user_svc.update_subscription(
        user_id=user_id,
        tier=payload.tier,
    )
    return ORJSONResponse({"success": True, "data": updated})
