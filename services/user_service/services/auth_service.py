"""
ZenSensei User Service - Auth Service

Business logic for user registration, authentication, token management,
password reset, and login rate limiting.

Falls back to in-memory storage when Firestore/Neo4j are unavailable,
so the service can run locally without any cloud dependencies.
"""

from __future__ import annotations

import sys
import os
import re
import secrets
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

_shared_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if _shared_path not in sys.path:
    sys.path.insert(0, _shared_path)

from fastapi import HTTPException, status

from shared.auth import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    verify_token,
)
from shared.models.user import LifeStage, SubscriptionTier, UserInDB, UserResponse

from services.user_service.config import UserServiceConfig, get_user_service_config
from services.user_service.schemas import (
    LoginRequest,
    LoginResponse,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)

logger = structlog.get_logger(__name__)

# ─── In-memory fallback stores ────────────────────────────────────────────────
# Used when Firestore / Neo4j are not reachable

_users_store: dict[str, dict[str, Any]] = {}          # user_id -> user record
_email_index: dict[str, str] = {}                      # email -> user_id
_refresh_tokens: set[str] = set()                      # valid refresh tokens
_blacklisted_tokens: set[str] = set()                  # invalidated refresh tokens
_password_reset_tokens: dict[str, dict[str, Any]] = {} # token -> {user_id, expires_at}

# Login attempt tracking: email -> list[attempt_timestamp]
_login_attempts: dict[str, list[datetime]] = defaultdict(list)


# ─── Password Validation ──────────────────────────────────────────────────────


def validate_password_strength(
    password: str,
    config: UserServiceConfig | None = None,
) -> None:
    """
    Enforce password complexity policy.

    Raises:
        HTTPException 400 with details about which requirements failed.
    """
    cfg = config or get_user_service_config()
    errors: list[str] = []

    if len(password) < cfg.password_min_length:
        errors.append(f"at least {cfg.password_min_length} characters")
    if cfg.password_require_uppercase and not re.search(r"[A-Z]", password):
        errors.append("at least one uppercase letter")
    if cfg.password_require_lowercase and not re.search(r"[a-z]", password):
        errors.append("at least one lowercase letter")
    if cfg.password_require_digit and not re.search(r"\d", password):
        errors.append("at least one digit")
    if cfg.password_require_symbol and not re.search(r"[^a-zA-Z0-9]", password):
        errors.append("at least one special character (!@#$%^&* etc.)")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "WEAK_PASSWORD",
                "message": "Password does not meet complexity requirements.",
                "requirements": errors,
            },
        )


# ─── Login Rate Limiting ──────────────────────────────────────────────────────


def _check_login_rate_limit(
    email: str,
    config: UserServiceConfig | None = None,
) -> None:
    """
    Enforce per-email login rate limiting using an in-memory sliding window.

    Raises:
        HTTPException 429 if the account is temporarily locked.
    """
    cfg = config or get_user_service_config()
    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(seconds=cfg.login_lockout_seconds)

    attempts = _login_attempts[email]
    # Prune attempts outside the window
    recent = [ts for ts in attempts if ts > window_start]
    _login_attempts[email] = recent

    if len(recent) >= cfg.max_login_attempts:
        oldest = recent[0]
        retry_after = int(
            (oldest + timedelta(seconds=cfg.login_lockout_seconds) - now).total_seconds()
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error_code": "ACCOUNT_LOCKED",
                "message": (
                    "Too many failed login attempts. "
                    f"Please try again in {retry_after} seconds."
                ),
                "retry_after": max(retry_after, 1),
            },
            headers={"Retry-After": str(max(retry_after, 1))},
        )


def _record_failed_login(email: str) -> None:
    """Record a failed login attempt timestamp for rate limiting."""
    _login_attempts[email].append(datetime.now(tz=timezone.utc))


def _clear_login_attempts(email: str) -> None:
    """Clear login attempt history after a successful login."""
    _login_attempts.pop(email, None)


# ─── Firestore helpers (with in-memory fallback) ──────────────────────────────


async def _firestore_create_user(
    user_id: str,
    data: dict[str, Any],
) -> None:
    """Persist user record to Firestore, falling back to in-memory store."""
    try:
        from shared.database.firestore import get_firestore_client
        client = get_firestore_client()
        if client._db is not None:
            await client.create("users", user_id, data)
            return
    except Exception as exc:
        logger.warning("Firestore unavailable, using in-memory store", error=str(exc))
    _users_store[user_id] = data
    _email_index[data["email"]] = user_id


async def _firestore_get_user_by_id(user_id: str) -> dict[str, Any] | None:
    """Fetch a user by ID from Firestore, with in-memory fallback."""
    try:
        from shared.database.firestore import get_firestore_client
        client = get_firestore_client()
        if client._db is not None:
            return await client.get("users", user_id)
    except Exception as exc:
        logger.warning("Firestore unavailable, using in-memory store", error=str(exc))
    return _users_store.get(user_id)


async def _firestore_get_user_by_email(email: str) -> dict[str, Any] | None:
    """Fetch a user by email (queries Firestore, falls back to in-memory index)."""
    try:
        from shared.database.firestore import get_firestore_client
        client = get_firestore_client()
        if client._db is not None:
            results = await client.query_collection(
                "users",
                filters=[("email", "==", email.lower())],
                limit=1,
            )
            return results[0] if results else None
    except Exception as exc:
        logger.warning("Firestore unavailable, using in-memory store", error=str(exc))

    user_id = _email_index.get(email.lower())
    if user_id:
        return _users_store.get(user_id)
    return None


async def _firestore_update_user(
    user_id: str,
    data: dict[str, Any],
) -> None:
    """Update user fields in Firestore, falling back to in-memory store."""
    try:
        from shared.database.firestore import get_firestore_client
        client = get_firestore_client()
        if client._db is not None:
            await client.update("users", user_id, data)
            return
    except Exception as exc:
        logger.warning("Firestore unavailable, using in-memory store", error=str(exc))
    if user_id in _users_store:
        _users_store[user_id].update(data)


# ─── Neo4j helpers (with in-memory fallback) ──────────────────────────────────


async def _neo4j_create_person_node(user_id: str, display_name: str, email: str) -> None:
    """Create a Person node in Neo4j, silently skipping if unavailable."""
    try:
        from shared.database.neo4j import get_neo4j_client
        client = get_neo4j_client()
        if client._driver is not None:
            await client.run_query(
                """
                MERGE (p:Person {id: $id})
                SET p.display_name = $display_name,
                    p.email        = $email,
                    p.created_at   = $created_at
                """,
                {
                    "id": user_id,
                    "display_name": display_name,
                    "email": email,
                    "created_at": datetime.now(tz=timezone.utc).isoformat(),
                },
            )
            logger.debug("Created Neo4j Person node", user_id=user_id)
    except Exception as exc:
        logger.warning(
            "Neo4j unavailable, skipping Person node creation",
            user_id=user_id,
            error=str(exc),
        )


# ─── Token helpers ────────────────────────────────────────────────────────────


def _build_token_claims(user: dict[str, Any]) -> dict[str, Any]:
    """Build JWT claims dict from a user record."""
    return {
        "sub": user["id"],
        "email": user["email"],
        "display_name": user.get("display_name", ""),
        "is_active": user.get("is_active", True),
        "subscription_tier": user.get("subscription_tier", SubscriptionTier.FREE),
    }


def _issue_token_pair(
    user: dict[str, Any],
    config: UserServiceConfig | None = None,
) -> TokenResponse:
    """Issue an access + refresh token pair for the given user record."""
    cfg = config or get_user_service_config()
    claims = _build_token_claims(user)

    access_token = create_access_token(data=claims, config=cfg)
    refresh_token = create_refresh_token(data=claims, config=cfg)

    # Track valid refresh tokens
    _refresh_tokens.add(refresh_token)

    expires_in = cfg.jwt_access_token_expire_minutes * 60
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
    )


def _user_record_to_response(record: dict[str, Any]) -> UserResponse:
    """Convert a raw Firestore / in-memory record to a UserResponse."""
    avatar = record.get("avatar_url")
    return UserResponse(
        id=record["id"],
        email=record["email"],
        display_name=record["display_name"],
        life_stage=LifeStage(record.get("life_stage", LifeStage.EARLY_CAREER)),
        avatar_url=avatar,
        is_active=record.get("is_active", True),
        is_premium=record.get("is_premium", False),
        subscription_tier=SubscriptionTier(
            record.get("subscription_tier", SubscriptionTier.FREE)
        ),
        created_at=record.get("created_at", datetime.now(tz=timezone.utc)),
        updated_at=record.get("updated_at", datetime.now(tz=timezone.utc)),
    )


# ─── Core Auth Functions ──────────────────────────────────────────────────────


async def register_user(
    request: RegisterRequest,
    config: UserServiceConfig | None = None,
) -> RegisterResponse:
    """
    Register a new user account.

    Steps:
    1. Validate password strength.
    2. Check for duplicate email.
    3. Hash password and persist to Firestore.
    4. Create Person node in Neo4j.
    5. Issue JWT token pair.

    Raises:
        HTTPException 400 on weak password.
        HTTPException 409 if email already registered.
    """
    cfg = config or get_user_service_config()

    validate_password_strength(request.password, cfg)

    # Normalise email
    email = request.email.lower().strip()

    # Check for existing account
    existing = await _firestore_get_user_by_email(email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "EMAIL_ALREADY_REGISTERED",
                "message": "An account with this email address already exists.",
            },
        )

    user_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)

    user_record: dict[str, Any] = {
        "id": user_id,
        "email": email,
        "display_name": request.display_name,
        "life_stage": request.life_stage,
        "hashed_password": get_password_hash(request.password),
        "is_active": True,
        "is_premium": False,
        "subscription_tier": SubscriptionTier.FREE,
        "avatar_url": None,
        "firebase_uid": None,
        "onboarding_completed": False,
        "completed_onboarding_steps": [],
        "interest_areas": [],
        "created_at": now,
        "updated_at": now,
    }

    await _firestore_create_user(user_id, user_record)
    await _neo4j_create_person_node(user_id, request.display_name, email)

    logger.info("User registered", user_id=user_id, email=email)

    tokens = _issue_token_pair(user_record, cfg)
    user_response = _user_record_to_response(user_record)

    return RegisterResponse(tokens=tokens, user=user_response)


async def authenticate_user(
    request: LoginRequest,
    config: UserServiceConfig | None = None,
) -> LoginResponse:
    """
    Authenticate a user with email and password.

    Raises:
        HTTPException 401 on invalid credentials.
        HTTPException 403 on disabled account.
        HTTPException 429 on too many failed attempts.
    """
    cfg = config or get_user_service_config()
    email = request.email.lower().strip()

    _check_login_rate_limit(email, cfg)

    user_record = await _firestore_get_user_by_email(email)

    if not user_record:
        _record_failed_login(email)
        logger.warning("Login attempt for unknown email", email=email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "INVALID_CREDENTIALS",
                "message": "Invalid email or password.",
            },
        )

    if not verify_password(request.password, user_record.get("hashed_password", "")):
        _record_failed_login(email)
        logger.warning("Invalid password attempt", user_id=user_record.get("id"), email=email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "INVALID_CREDENTIALS",
                "message": "Invalid email or password.",
            },
        )

    if not user_record.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "ACCOUNT_DISABLED",
                "message": "Your account has been disabled. Please contact support.",
            },
        )

    _clear_login_attempts(email)

    # Update last_active_at
    now = datetime.now(tz=timezone.utc)
    await _firestore_update_user(user_record["id"], {"last_active_at": now, "updated_at": now})

    logger.info("User authenticated", user_id=user_record["id"])

    tokens = _issue_token_pair(user_record, cfg)
    user_response = _user_record_to_response(user_record)

    return LoginResponse(tokens=tokens, user=user_response)


async def refresh_tokens(
    refresh_token: str,
    config: UserServiceConfig | None = None,
) -> RefreshResponse:
    """
    Validate the refresh token and issue a new access token.

    Raises:
        HTTPException 401 on invalid / blacklisted token.
    """
    cfg = config or get_user_service_config()

    if refresh_token in _blacklisted_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "TOKEN_REVOKED",
                "message": "This refresh token has been revoked.",
            },
        )

    payload = verify_token(refresh_token, expected_type="refresh", config=cfg)
    user_id: str = payload["sub"]

    user_record = await _firestore_get_user_by_id(user_id)
    if not user_record or not user_record.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "INVALID_CREDENTIALS",
                "message": "Could not validate credentials.",
            },
        )

    claims = _build_token_claims(user_record)
    new_access = create_access_token(data=claims, config=cfg)
    expires_in = cfg.jwt_access_token_expire_minutes * 60

    logger.debug("Access token refreshed", user_id=user_id)

    return RefreshResponse(
        access_token=new_access,
        token_type="bearer",
        expires_in=expires_in,
    )


async def logout_user(refresh_token: str) -> None:
    """
    Invalidate a refresh token (logout).

    Silently succeeds if the token was already blacklisted or never existed.
    """
    _refresh_tokens.discard(refresh_token)
    _blacklisted_tokens.add(refresh_token)
    logger.debug("Refresh token invalidated")


async def initiate_password_reset(
    email: str,
    config: UserServiceConfig | None = None,
) -> None:
    """
    Generate a password reset token and send a reset email.

    Returns silently even if the email doesn't exist (prevents enumeration).
    """
    cfg = config or get_user_service_config()
    email = email.lower().strip()

    user_record = await _firestore_get_user_by_email(email)
    if not user_record:
        logger.info("Password reset requested for unknown email", email=email)
        return  # Silently succeed to prevent email enumeration

    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(
        seconds=cfg.password_reset_token_expire_seconds
    )

    _password_reset_tokens[token] = {
        "user_id": user_record["id"],
        "email": email,
        "expires_at": expires_at,
        "used": False,
    }

    reset_url = cfg.password_reset_url_template.format(token=token)

    # Attempt to send via SendGrid if configured
    await _send_password_reset_email(email, reset_url, user_record.get("display_name", ""), cfg)

    logger.info("Password reset initiated", user_id=user_record["id"], email=email)


async def _send_password_reset_email(
    email: str,
    reset_url: str,
    display_name: str,
    config: UserServiceConfig,
) -> None:
    """Send password reset email via SendGrid, logging on failure."""
    if not config.sendgrid_api_key:
        logger.warning(
            "SendGrid not configured; password reset email not sent",
            email=email,
            reset_url=reset_url,
        )
        return

    try:
        import sendgrid  # type: ignore[import-untyped]
        from sendgrid.helpers.mail import Mail  # type: ignore[import-untyped]

        message = Mail(
            from_email=config.sendgrid_from_email,
            to_emails=email,
            subject="Reset your ZenSensei password",
            html_content=(
                f"<p>Hi {display_name},</p>"
                f"<p>Click the link below to reset your password. "
                f"This link expires in 1 hour.</p>"
                f'<p><a href="{reset_url}">Reset Password</a></p>'
                f"<p>If you didn't request this, you can safely ignore this email.</p>"
            ),
        )
        sg = sendgrid.SendGridAPIClient(api_key=config.sendgrid_api_key)
        sg.send(message)
        logger.info("Password reset email sent", email=email)
    except Exception as exc:
        logger.error("Failed to send password reset email", email=email, error=str(exc))


async def reset_password(
    token: str,
    new_password: str,
    config: UserServiceConfig | None = None,
) -> None:
    """
    Reset the user's password using a valid reset token.

    Raises:
        HTTPException 400 on invalid / expired / already-used token.
        HTTPException 400 on weak new password.
    """
    cfg = config or get_user_service_config()

    token_data = _password_reset_tokens.get(token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INVALID_RESET_TOKEN",
                "message": "Invalid or expired password reset token.",
            },
        )

    if token_data.get("used"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "TOKEN_ALREADY_USED",
                "message": "This password reset link has already been used.",
            },
        )

    if datetime.now(tz=timezone.utc) > token_data["expires_at"]:
        _password_reset_tokens.pop(token, None)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "EXPIRED_RESET_TOKEN",
                "message": "This password reset link has expired. Please request a new one.",
            },
        )

    validate_password_strength(new_password, cfg)

    now = datetime.now(tz=timezone.utc)
    await _firestore_update_user(
        token_data["user_id"],
        {
            "hashed_password": get_password_hash(new_password),
            "updated_at": now,
        },
    )

    # Mark token as used (don't delete so we can detect reuse)
    token_data["used"] = True

    logger.info("Password reset successfully", user_id=token_data["user_id"])
