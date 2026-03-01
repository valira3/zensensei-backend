"""
ZenSensei User Service - Auth Router

Handles:
  POST /auth/register       Create new user account
  POST /auth/login          Authenticate with email/password
  POST /auth/refresh        Exchange refresh token for new access token
  POST /auth/logout         Invalidate a refresh token
  POST /auth/forgot-password  Initiate password reset flow
  POST /auth/reset-password   Complete password reset with token
  GET  /auth/me             Return the currently authenticated user
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
from fastapi import APIRouter, Depends, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_active_user
from shared.models.base import BaseResponse
from shared.models.user import UserResponse

from services.user_service.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
)
from services.user_service.services import auth_service as auth_svc
from services.user_service.services.auth_service import (
    _firestore_get_user_by_id,
    _user_record_to_response,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ─── Register ─────────────────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=BaseResponse[RegisterResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    response_class=ORJSONResponse,
)
async def register(request: RegisterRequest) -> dict[str, Any]:
    """
    Create a new ZenSensei user account.

    - Validates password strength (min 12 chars, upper, lower, digit, symbol).
    - Hashes the password with bcrypt.
    - Stores the user record in Firestore.
    - Creates a ``Person`` node in the Neo4j knowledge graph.
    - Returns a JWT access + refresh token pair and the new user profile.
    """
    logger.info("Registration attempt", email=request.email)
    result = await auth_svc.register_user(request)
    return {
        "success": True,
        "message": "Account created successfully.",
        "data": result.model_dump(),
    }


# ─── Login ────────────────────────────────────────────────────────────────────


@router.post(
    "/login",
    response_model=BaseResponse[LoginResponse],
    summary="Authenticate with email and password",
    response_class=ORJSONResponse,
)
async def login(request: LoginRequest) -> dict[str, Any]:
    """
    Authenticate a user with email and password.

    - Enforces per-email rate limiting (max 5 attempts / 15-minute window).
    - Returns a JWT access + refresh token pair on success.
    """
    logger.info("Login attempt", email=request.email)
    result = await auth_svc.authenticate_user(request)
    return {
        "success": True,
        "message": "Login successful.",
        "data": result.model_dump(),
    }


# ─── Refresh Token ────────────────────────────────────────────────────────────


@router.post(
    "/refresh",
    response_model=BaseResponse[RefreshResponse],
    summary="Exchange a refresh token for a new access token",
    response_class=ORJSONResponse,
)
async def refresh(request: RefreshRequest) -> dict[str, Any]:
    """
    Issue a new access token using a valid refresh token.

    The refresh token is validated and must not be blacklisted.
    """
    result = await auth_svc.refresh_tokens(request.refresh_token)
    return {
        "success": True,
        "message": "Token refreshed.",
        "data": result.model_dump(),
    }


# ─── Logout ───────────────────────────────────────────────────────────────────


@router.post(
    "/logout",
    response_model=BaseResponse[None],
    summary="Invalidate a refresh token",
    response_class=ORJSONResponse,
)
async def logout(
    request: LogoutRequest,
    _current_user: dict[str, Any] = Depends(get_current_active_user),
) -> dict[str, Any]:
    """
    Invalidate the provided refresh token.

    The access token will remain valid until its natural expiry —
    front-ends should discard it immediately after calling this endpoint.
    """
    await auth_svc.logout_user(request.refresh_token)
    return {
        "success": True,
        "message": "Logged out successfully.",
        "data": None,
    }


# ─── Forgot Password ──────────────────────────────────────────────────────────


@router.post(
    "/forgot-password",
    response_model=BaseResponse[None],
    summary="Initiate a password reset flow",
    response_class=ORJSONResponse,
)
async def forgot_password(request: ForgotPasswordRequest) -> dict[str, Any]:
    """
    Send a password reset email to the provided address.

    Returns 200 regardless of whether the email exists to prevent
    user enumeration attacks.
    """
    await auth_svc.initiate_password_reset(request.email)
    return {
        "success": True,
        "message": (
            "If an account with that email exists, "
            "a password reset link has been sent."
        ),
        "data": None,
    }


# ─── Reset Password ───────────────────────────────────────────────────────────


@router.post(
    "/reset-password",
    response_model=BaseResponse[None],
    summary="Complete password reset with a valid token",
    response_class=ORJSONResponse,
)
async def reset_password(request: ResetPasswordRequest) -> dict[str, Any]:
    """
    Reset the user's password using the token delivered by email.

    The token is single-use and expires after 1 hour.
    """
    await auth_svc.reset_password(request.token, request.new_password)
    return {
        "success": True,
        "message": "Password reset successfully. You can now log in with your new password.",
        "data": None,
    }


# ─── Get Current User ─────────────────────────────────────────────────────────


@router.get(
    "/me",
    response_model=BaseResponse[UserResponse],
    summary="Get the currently authenticated user",
    response_class=ORJSONResponse,
)
async def get_me(
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> dict[str, Any]:
    """
    Return the full profile of the currently authenticated user.

    Requires a valid ``Authorization: Bearer <access_token>`` header.
    """
    user_id: str = current_user["sub"]
    user_record = await _firestore_get_user_by_id(user_id)

    if not user_record:
        # Token is valid but user was deleted — soft 404 with auth context
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "USER_NOT_FOUND",
                "message": "Authenticated user profile not found.",
            },
        )

    user_response = _user_record_to_response(user_record)
    return {
        "success": True,
        "message": "OK",
        "data": user_response.model_dump(),
    }
