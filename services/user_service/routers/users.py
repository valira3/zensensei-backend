"""
ZenSensei User Service - Users Router

Handles user profile management:
  GET    /users/me           Get current user profile
  PATCH  /users/me           Update profile fields
  DELETE /users/me           Soft-delete (deactivate) account
  GET    /users/{user_id}    Admin: fetch any user by ID
"""

from __future__ import annotations

import sys
import os

_shared_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if _shared_path not in sys.path:
    sys.path.insert(0, _shared_path)

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Path, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_active_user, require_roles
from shared.models.base import BaseResponse
from shared.models.user import UserResponse

from services.user_service.schemas import UpdateProfileRequest
from services.user_service.services.user_service import (
    _get_user_or_404,
    deactivate_user,
    get_user_by_id,
    update_user_profile,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


# ─── Get current user profile ────────────────────────────────────────────────


@router.get(
    "/me",
    response_model=BaseResponse[UserResponse],
    summary="Get the current user's profile",
    response_class=ORJSONResponse,
)
async def get_my_profile(
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> dict[str, Any]:
    """
    Return the full profile for the currently authenticated user.

    This endpoint duplicates ``GET /auth/me`` for semantic clarity—use
    whichever fits your client's mental model.
    """
    user_id: str = current_user["sub"]
    user = await get_user_by_id(user_id)
    return {
        "success": True,
        "message": "OK",
        "data": user.model_dump(),
    }


# ─── Update profile ────────────────────────────────────────────────────────────


@router.patch(
    "/me",
    response_model=BaseResponse[UserResponse],
    summary="Update profile fields",
    response_class=ORJSONResponse,
)
async def update_my_profile(
    request: UpdateProfileRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> dict[str, Any]:
    """
    Apply a partial update to the current user's profile.

    Only the fields provided in the request body are updated;
    omitted fields retain their current values.
    """
    user_id: str = current_user["sub"]
    await _get_user_or_404(user_id)  # Ensures user exists before patching

    updated = await update_user_profile(user_id, request)
    logger.info("Profile updated", user_id=user_id)
    return {
        "success": True,
        "message": "Profile updated.",
        "data": updated.model_dump(),
    }


# ─── Deactivate account ─────────────────────────────────────────────────────────


@router.delete(
    "/me",
    response_model=BaseResponse[None],
    summary="Deactivate (soft-delete) the current user account",
    status_code=status.HTTP_200_OK,
    response_class=ORJSONResponse,
)
async def deactivate_my_account(
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> dict[str, Any]:
    """
    Soft-delete the authenticated user's account.

    Sets ``is_active = False`` on the user record.  The account can be
    reactivated by an admin; personal data is not immediately purged.
    """
    user_id: str = current_user["sub"]
    await deactivate_user(user_id)
    logger.info("Account deactivated", user_id=user_id)
    return {
        "success": True,
        "message": "Account deactivated. Contact support to reactivate.",
        "data": None,
    }


# ─── Admin: fetch user by ID ─────────────────────────────────────────────────


@router.get(
    "/{user_id}",
    response_model=BaseResponse[UserResponse],
    summary="Admin: fetch any user by ID",
    response_class=ORJSONResponse,
    dependencies=[Depends(require_roles(["admin"]))],
)
async def admin_get_user(
    user_id: str = Path(..., description="UUID of the user to fetch"),
) -> dict[str, Any]:
    """
    Retrieve any user's profile by ID.

    Restricted to users with the ``admin`` role.
    """
    user = await get_user_by_id(user_id)
    return {
        "success": True,
        "message": "OK",
        "data": user.model_dump(),
    }
