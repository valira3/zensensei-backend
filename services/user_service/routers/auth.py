"""
ZenSensei User Service - Auth Router

Endpoints:
  POST /auth/register           - Create a new user account
  POST /auth/login              - Exchange credentials for tokens
  POST /auth/refresh            - Rotate access/refresh token pair
  POST /auth/logout             - Revoke the current refresh token
  POST /auth/verify-email       - Mark email as verified via OTP
  POST /auth/resend-verification - Re-send email verification OTP
  POST /auth/forgot-password    - Send password-reset OTP
  POST /auth/reset-password     - Apply new password via OTP
  POST /auth/change-password    - Change password (authenticated)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_active_user

from services.user_service.schemas import (
    ChangePasswordRequest,
    EmailVerificationRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
)
import services.user_service.services.auth_service as auth_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ─── Register ────────────────────────────────────────────────────────────────


@router.post(
    "/register",
    summary="Register a new user account",
    response_class=ORJSONResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    request: Request,
) -> ORJSONResponse:
    """Create a new user account and send an email-verification OTP."""
    user = await auth_svc.register_user(
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        life_stage=payload.life_stage,
    )
    return ORJSONResponse(
        {"success": True, "data": user},
        status_code=status.HTTP_201_CREATED,
    )


# ─── Login ─────────────────────────────────────────────────────────────────


@router.post(
    "/login",
    summary="Login and get access + refresh tokens",
    response_class=ORJSONResponse,
)
async def login(
    payload: LoginRequest,
    request: Request,
) -> ORJSONResponse:
    """Authenticate with email/password and receive a token pair."""
    tokens = await auth_svc.login_user(
        email=payload.email,
        password=payload.password,
    )
    return ORJSONResponse({"success": True, "data": tokens})


# ─── Refresh ─────────────────────────────────────────────────────────────────


@router.post(
    "/refresh",
    summary="Rotate access and refresh tokens",
    response_class=ORJSONResponse,
)
async def refresh_tokens(
    payload: RefreshRequest,
) -> ORJSONResponse:
    """Rotate the token pair using a valid refresh token."""
    tokens = await auth_svc.refresh_tokens(payload.refresh_token)
    return ORJSONResponse({"success": True, "data": tokens})


# ─── Logout ─────────────────────────────────────────────────────────────────


@router.post(
    "/logout",
    summary="Logout (revoke refresh token)",
    response_class=ORJSONResponse,
)
async def logout(
    payload: RefreshRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """Revoke the provided refresh token, invalidating the session."""
    await auth_svc.logout_user(payload.refresh_token)
    return ORJSONResponse({"success": True, "message": "Logged out successfully"})


# ─── Email verification ──────────────────────────────────────────────────────


@router.post(
    "/verify-email",
    summary="Verify email address using OTP",
    response_class=ORJSONResponse,
)
async def verify_email(
    payload: EmailVerificationRequest,
) -> ORJSONResponse:
    """Mark the user's email as verified using the OTP sent on registration."""
    await auth_svc.verify_email(payload.email, payload.otp)
    return ORJSONResponse({"success": True, "message": "Email verified successfully"})


@router.post(
    "/resend-verification",
    summary="Resend email verification OTP",
    response_class=ORJSONResponse,
)
async def resend_verification(
    payload: ResendVerificationRequest,
) -> ORJSONResponse:
    """Re-send the email verification OTP to the specified address."""
    await auth_svc.resend_verification_email(payload.email)
    return ORJSONResponse(
        {"success": True, "message": "Verification email sent if account exists"}
    )


# ─── Password management ─────────────────────────────────────────────────────


@router.post(
    "/forgot-password",
    summary="Request password reset OTP",
    response_class=ORJSONResponse,
)
async def forgot_password(
    payload: ForgotPasswordRequest,
) -> ORJSONResponse:
    """Send a password-reset OTP to the given email address."""
    await auth_svc.send_password_reset(payload.email)
    return ORJSONResponse(
        {"success": True, "message": "Password reset email sent if account exists"}
    )


@router.post(
    "/reset-password",
    summary="Reset password using OTP",
    response_class=ORJSONResponse,
)
async def reset_password(
    payload: ResetPasswordRequest,
) -> ORJSONResponse:
    """Apply a new password using the OTP received via email."""
    await auth_svc.reset_password(payload.email, payload.otp, payload.new_password)
    return ORJSONResponse({"success": True, "message": "Password reset successfully"})


@router.post(
    "/change-password",
    summary="Change password (authenticated)",
    response_class=ORJSONResponse,
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """Change the authenticated user's password."""
    user_id = current_user.get("sub", current_user.get("user_id", current_user.get("id")))
    await auth_svc.change_password(
        user_id=user_id,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return ORJSONResponse({"success": True, "message": "Password changed successfully"})
