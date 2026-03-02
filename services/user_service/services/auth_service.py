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
import hashlib
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

# Legacy in-memory token stores -- kept ONLY as last-resort fallback when Redis
# is also unavailable.  Redis is always attempted first.
_refresh_tokens: set[str] = set()                      # valid refresh tokens
_blacklisted_tokens: set[str] = set()                  # invalidated refresh tokens
_password_reset_tokens: dict[str, dict[str, Any]] = {} # token -> {user_id, expires_at}
_email_verify_tokens: dict[str, dict[str, Any]] = {}   # token -> {user_id, expires_at}
_email_change_tokens: dict[str, dict[str, Any]] = {}   # token -> {user_id, new_email, expires_at}

# Login attempt tracking: email -> list[attempt_timestamp]
_login_attempts: dict[str, list[datetime]] = defaultdict(list)


# ─── Redis helpers ────────────────────────────────────────────────────────────


def _token_hash(token: str) -> str:
    """Return a short SHA-256 hex digest of a token string (for use as Redis key suffix)."""
    return hashlib.sha256(token.encode()).hexdigest()[:32]


async def _get_redis():
    """Return a connected RedisClient singleton, or None if unavailable."""
    try:
        from shared.database.redis import get_redis_client
        client = get_redis_client()
        if client._client is None:
            await client.connect()
        return client
    except Exception as exc:
        logger.warning("Redis unavailable, using in-memory token stores", error=str(exc))
        return None


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


async def _check_login_rate_limit(
    email: str,
    config: UserServiceConfig | None = None,
) -> None:
    """
    Enforce per-email login rate limiting using Redis (INCR / EXPIRE).

    Redis key: zensensei:login_attempts:{email}
      - Value: integer count of failed attempts within the lockout window.
      - TTL:   cfg.login_lockout_seconds (set on first failed attempt).

    Falls back to the in-memory sliding window when Redis is unavailable.

    Raises:
        HTTPException 429 if the account is temporarily locked.
    """
    cfg = config or get_user_service_config()

    redis = await _get_redis()
    if redis is not None:
        try:
            key = f"zensensei:login_attempts:{email}"
            count_raw = await redis.get(key)
            count = int(count_raw) if count_raw is not None else 0

            if count >= cfg.max_login_attempts:
                retry_after = cfg.login_lockout_seconds
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
            return
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning(
                "Redis login rate-limit check failed, falling back to in-memory",
                email=email,
                error=str(exc),
            )
            # Fall through to in-memory fallback

    # In-memory fallback
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


async def _record_failed_login(
    email: str,
    config: UserServiceConfig | None = None,
) -> None:
    """Record a failed login attempt in Redis (with TTL) or in-memory fallback."""
    cfg = config or get_user_service_config()

    redis = await _get_redis()
    if redis is not None:
        try:
            key = f"zensensei:login_attempts:{email}"
            raw_client = redis._client
            pipe = raw_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, cfg.login_lockout_seconds)
            await pipe.execute()
            return
        except Exception as exc:
            logger.warning(
                "Redis failed to record login attempt, falling back to in-memory",
                email=email,
                error=str(exc),
            )

    # In-memory fallback
    _login_attempts[email].append(datetime.now(tz=timezone.utc))


async def _clear_login_attempts(email: str) -> None:
    """Clear login attempt history after a successful login."""
    redis = await _get_redis()
    if redis is not None:
        try:
            key = f"zensensei:login_attempts:{email}"
            await redis.delete(key)
            return
        except Exception as exc:
            logger.warning(
                "Redis failed to clear login attempts, falling back to in-memory",
                email=email,
                error=str(exc),
            )

    # In-memory fallback
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


async def _issue_token_pair(
    user: dict[str, Any],
    config: UserServiceConfig | None = None,
) -> TokenResponse:
    """
    Issue an access + refresh token pair for the given user record.

    Stores the refresh token in Redis with key:
      zensensei:refresh:{user_id}:{token_hash}  TTL = refresh token expiry
    Falls back to the in-memory set when Redis is unavailable.
    """
    cfg = config or get_user_service_config()
    claims = _build_token_claims(user)

    access_token = create_access_token(data=claims, config=cfg)
    refresh_token = create_refresh_token(data=claims, config=cfg)

    # Store refresh token in Redis
    user_id = user["id"]
    token_hash = _token_hash(refresh_token)
    refresh_ttl = cfg.jwt_refresh_token_expire_days * 86400  # seconds

    redis = await _get_redis()
    if redis is not None:
        try:
            key = f"zensensei:refresh:{user_id}:{token_hash}"
            await redis.set(key, "1", ttl=refresh_ttl)
        except Exception as exc:
            logger.warning(
                "Redis failed to store refresh token, falling back to in-memory",
                user_id=user_id,
                error=str(exc),
            )
            _refresh_tokens.add(refresh_token)
    else:
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
    email: str,
    password: str,
    display_name: str,
    life_stage: LifeStage = LifeStage.EARLY_CAREER,
    config: UserServiceConfig | None = None,
) -> dict[str, Any]:
    """
    Register a new user account.

    Steps:
    1. Validate password strength.
    2. Check for duplicate email.
    3. Hash password and persist to Firestore.
    4. Create Person node in Neo4j.
    5. Issue JWT token pair.
    6. Send email verification OTP.

    Raises:
        HTTPException 400 on weak password.
        HTTPException 409 if email already registered.
    """
    cfg = config or get_user_service_config()

    # Build a minimal request object for validate_password_strength
    class _Req:
        pass
    req = _Req()
    req.password = password  # type: ignore[attr-defined]
    validate_password_strength(password, cfg)

    # Normalise email
    email = email.lower().strip()

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
        "display_name": display_name,
        "hashed_password": get_password_hash(password),
        "life_stage": life_stage,
        "is_active": True,
        "is_premium": False,
        "email_verified": False,
        "subscription_tier": SubscriptionTier.FREE,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    await _firestore_create_user(user_id, user_record)
    await _neo4j_create_person_node(user_id, display_name, email)

    tokens = await _issue_token_pair(user_record, cfg)

    # Send verification email (best-effort)
    try:
        await send_verification_email(email, user_id)
    except Exception as exc:
        logger.warning("Could not send verification email", user_id=user_id, error=str(exc))

    return {
        "user_id": user_id,
        "email": email,
        "display_name": display_name,
        "email_verified": False,
        "tokens": tokens.model_dump(),
    }


async def login_user(
    email: str,
    password: str,
    config: UserServiceConfig | None = None,
) -> dict[str, Any]:
    """
    Authenticate with email/password.

    Raises:
        HTTPException 429 on too many failed attempts.
        HTTPException 401 on invalid credentials.
    """
    cfg = config or get_user_service_config()
    email = email.lower().strip()

    await _check_login_rate_limit(email, cfg)

    user = await _firestore_get_user_by_email(email)
    if not user or not verify_password(password, user.get("hashed_password", "")):
        await _record_failed_login(email, cfg)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "INVALID_CREDENTIALS",
                "message": "Invalid email or password.",
            },
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "ACCOUNT_DISABLED", "message": "Account is disabled."},
        )

    await _clear_login_attempts(email)
    tokens = await _issue_token_pair(user, cfg)
    return {"tokens": tokens.model_dump(), "user_id": user["id"]}


async def refresh_tokens(
    refresh_token: str,
    config: UserServiceConfig | None = None,
) -> dict[str, Any]:
    """
    Validate a refresh token and issue a new token pair (rotation).

    Redis flow:
      1. Decode JWT to extract sub (user_id) and jti.
      2. Look up zensensei:refresh:{user_id}:{token_hash}  in Redis.
      3. If present, delete it (one-time use) and issue a new pair.

    Falls back to in-memory set when Redis is unavailable.

    Raises:
        HTTPException 401 on invalid/expired/revoked token.
    """
    cfg = config or get_user_service_config()

    payload = verify_token(refresh_token, token_type="refresh", config=cfg)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "INVALID_TOKEN", "message": "Invalid or expired refresh token."},
        )

    user_id: str = payload.get("sub", "")
    token_hash = _token_hash(refresh_token)

    redis = await _get_redis()
    if redis is not None:
        try:
            key = f"zensensei:refresh:{user_id}:{token_hash}"
            exists = await redis.get(key)
            if not exists:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "error_code": "TOKEN_REVOKED",
                        "message": "Refresh token has been revoked or already used.",
                    },
                )
            # Revoke old token (rotation)
            await redis.delete(key)
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Redis token rotation check failed", error=str(exc))
            # Fall through to in-memory
            if refresh_token in _blacklisted_tokens:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"error_code": "TOKEN_REVOKED", "message": "Refresh token has been revoked."},
                )
            _refresh_tokens.discard(refresh_token)
    else:
        if refresh_token not in _refresh_tokens or refresh_token in _blacklisted_tokens:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "TOKEN_REVOKED", "message": "Refresh token has been revoked."},
            )
        _refresh_tokens.discard(refresh_token)

    user = await _firestore_get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "USER_NOT_FOUND", "message": "User no longer exists."},
        )

    new_tokens = await _issue_token_pair(user, cfg)
    return new_tokens.model_dump()


async def logout_user(
    refresh_token: str,
    config: UserServiceConfig | None = None,
) -> None:
    """
    Revoke a refresh token (logout).

    Deletes the Redis key (or blacklists in-memory).
    """
    cfg = config or get_user_service_config()

    payload = verify_token(refresh_token, token_type="refresh", config=cfg)
    user_id = payload.get("sub", "") if payload else ""
    token_hash = _token_hash(refresh_token)

    redis = await _get_redis()
    if redis is not None:
        try:
            key = f"zensensei:refresh:{user_id}:{token_hash}"
            await redis.delete(key)
            return
        except Exception as exc:
            logger.warning("Redis logout failed, falling back to in-memory", error=str(exc))

    _refresh_tokens.discard(refresh_token)
    _blacklisted_tokens.add(refresh_token)


# ─── Email Verification ───────────────────────────────────────────────────────

_OTP_TTL_SECONDS = 600  # 10 minutes


async def send_verification_email(email: str, user_id: str) -> None:
    """Generate an OTP and send a verification email."""
    otp = "{:06d}".format(secrets.randbelow(1_000_000))
    ttl = _OTP_TTL_SECONDS

    redis = await _get_redis()
    if redis is not None:
        try:
            key = f"zensensei:email_verify:{email}"
            await redis.set(key, f"{user_id}:{otp}", ttl=ttl)
        except Exception as exc:
            logger.warning("Redis OTP store failed, using in-memory", error=str(exc))
            _email_verify_tokens[otp] = {
                "user_id": user_id,
                "email": email,
                "expires_at": (datetime.now(tz=timezone.utc) + timedelta(seconds=ttl)).isoformat(),
            }
    else:
        _email_verify_tokens[otp] = {
            "user_id": user_id,
            "email": email,
            "expires_at": (datetime.now(tz=timezone.utc) + timedelta(seconds=ttl)).isoformat(),
        }

    logger.info("Verification OTP generated", user_id=user_id, email=email)
    # TODO: integrate with email provider (SendGrid / SES) to actually send the email


async def verify_email(email: str, otp: str) -> None:
    """
    Verify an email address using the OTP.

    Raises:
        HTTPException 400 on invalid/expired OTP.
    """
    email = email.lower().strip()
    user_id: str | None = None

    redis = await _get_redis()
    if redis is not None:
        try:
            key = f"zensensei:email_verify:{email}"
            val = await redis.get(key)
            if val:
                stored_user_id, stored_otp = val.split(":", 1)
                if stored_otp == otp:
                    user_id = stored_user_id
                    await redis.delete(key)
        except Exception as exc:
            logger.warning("Redis OTP lookup failed, using in-memory", error=str(exc))

    if user_id is None:
        # In-memory fallback
        record = _email_verify_tokens.get(otp)
        if record and record.get("email") == email:
            expires_at = datetime.fromisoformat(record["expires_at"])
            if datetime.now(tz=timezone.utc) <= expires_at:
                user_id = record["user_id"]
                del _email_verify_tokens[otp]

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_OTP", "message": "Invalid or expired verification code."},
        )

    await _firestore_update_user(user_id, {"email_verified": True})
    logger.info("Email verified", user_id=user_id)


async def resend_verification_email(email: str) -> None:
    """Re-send verification OTP (no-op if user not found, to prevent enumeration)."""
    email = email.lower().strip()
    user = await _firestore_get_user_by_email(email)
    if user and not user.get("email_verified", False):
        await send_verification_email(email, user["id"])


# ─── Password Reset ───────────────────────────────────────────────────────────


async def send_password_reset(email: str) -> None:
    """Generate a password-reset OTP and send it via email (best-effort)."""
    email = email.lower().strip()
    user = await _firestore_get_user_by_email(email)
    if not user:
        # Silent no-op to prevent email enumeration
        return

    otp = "{:06d}".format(secrets.randbelow(1_000_000))
    ttl = _OTP_TTL_SECONDS
    user_id = user["id"]

    redis = await _get_redis()
    if redis is not None:
        try:
            key = f"zensensei:pwd_reset:{email}"
            await redis.set(key, f"{user_id}:{otp}", ttl=ttl)
        except Exception as exc:
            logger.warning("Redis OTP store failed, using in-memory", error=str(exc))
            _password_reset_tokens[otp] = {
                "user_id": user_id,
                "email": email,
                "expires_at": (datetime.now(tz=timezone.utc) + timedelta(seconds=ttl)).isoformat(),
            }
    else:
        _password_reset_tokens[otp] = {
            "user_id": user_id,
            "email": email,
            "expires_at": (datetime.now(tz=timezone.utc) + timedelta(seconds=ttl)).isoformat(),
        }

    logger.info("Password reset OTP generated", user_id=user_id)
    # TODO: send via email provider


async def reset_password(email: str, otp: str, new_password: str) -> None:
    """
    Apply a new password using the OTP.

    Raises:
        HTTPException 400 on invalid/expired OTP or weak password.
    """
    email = email.lower().strip()
    user_id: str | None = None

    redis = await _get_redis()
    if redis is not None:
        try:
            key = f"zensensei:pwd_reset:{email}"
            val = await redis.get(key)
            if val:
                stored_user_id, stored_otp = val.split(":", 1)
                if stored_otp == otp:
                    user_id = stored_user_id
                    await redis.delete(key)
        except Exception as exc:
            logger.warning("Redis OTP lookup failed, using in-memory", error=str(exc))

    if user_id is None:
        record = _password_reset_tokens.get(otp)
        if record and record.get("email") == email:
            expires_at = datetime.fromisoformat(record["expires_at"])
            if datetime.now(tz=timezone.utc) <= expires_at:
                user_id = record["user_id"]
                del _password_reset_tokens[otp]

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_OTP", "message": "Invalid or expired reset code."},
        )

    validate_password_strength(new_password)
    hashed = get_password_hash(new_password)
    await _firestore_update_user(user_id, {
        "hashed_password": hashed,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
    })
    logger.info("Password reset completed", user_id=user_id)


async def change_password(
    user_id: str,
    current_password: str,
    new_password: str,
) -> None:
    """
    Change password for an authenticated user.

    Raises:
        HTTPException 401 if current_password is wrong.
        HTTPException 400 if new_password is too weak.
    """
    user = await _firestore_get_user_by_id(user_id)
    if not user or not verify_password(current_password, user.get("hashed_password", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "INVALID_CREDENTIALS", "message": "Current password is incorrect."},
        )

    validate_password_strength(new_password)
    hashed = get_password_hash(new_password)
    await _firestore_update_user(user_id, {
        "hashed_password": hashed,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
    })
    logger.info("Password changed", user_id=user_id)
