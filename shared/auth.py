"""
ZenSensei Shared Auth

JWT token creation/verification, password hashing, and a
FastAPI dependency for extracting the current user from a Bearer token.

Token types
-----------
access   Short-lived (default 30 min).  Carries user claims.
refresh  Long-lived (default 30 days).  Used only to rotate the pair.

Each token embeds a ``type`` claim so access tokens cannot be used
where a refresh token is expected and vice-versa.

Each token also embeds a ``jti`` (JWT ID) — a random UUID that uniquely
identifies the token.  The auth service uses the jti to key revocation
records in Redis (``zensensei:refresh:{user_id}:{token_hash}``).
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from shared.config import ZenSenseiConfig, get_config

logger = logging.getLogger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer_scheme = HTTPBearer(auto_error=False)


# ─── Password helpers ─────────────────────────────────────────────────────────


def get_password_hash(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


# ─── Token creation ──────────────────────────────────────────────────────────


def create_access_token(
    data: dict[str, Any],
    config: ZenSenseiConfig | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a signed JWT access token.

    Adds ``type=access``, ``jti``, ``iat``, and ``exp`` claims automatically.
    """
    cfg = config or get_config()
    to_encode = data.copy()
    now = datetime.now(tz=timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=cfg.jwt_access_token_expire_minutes)
    )
    to_encode.update({
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expire,
    })
    return jwt.encode(to_encode, cfg.secret_key, algorithm=cfg.jwt_algorithm)


def create_refresh_token(
    data: dict[str, Any],
    config: ZenSenseiConfig | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a signed JWT refresh token.

    Adds ``type=refresh``, ``jti``, ``iat``, and ``exp`` claims automatically.
    """
    cfg = config or get_config()
    to_encode = data.copy()
    now = datetime.now(tz=timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(days=cfg.jwt_refresh_token_expire_days)
    )
    to_encode.update({
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expire,
    })
    return jwt.encode(to_encode, cfg.secret_key, algorithm=cfg.jwt_algorithm)


# ─── Token verification ───────────────────────────────────────────────────────


def verify_token(
    token: str,
    token_type: str = "access",
    config: ZenSenseiConfig | None = None,
) -> Optional[dict[str, Any]]:
    """
    Decode and verify a JWT token.

    Returns the decoded payload dict if valid, or ``None`` on any failure.
    Validates the ``type`` claim so access tokens cannot be reused as refresh
    tokens and vice-versa.
    """
    cfg = config or get_config()
    try:
        payload = jwt.decode(
            token,
            cfg.secret_key,
            algorithms=[cfg.jwt_algorithm],
        )
        if payload.get("type") != token_type:
            logger.warning(
                "Token type mismatch: expected %s, got %s",
                token_type,
                payload.get("type"),
            )
            return None
        return payload
    except JWTError as exc:
        logger.debug("JWT verification failed: %s", exc)
        return None


# ─── FastAPI dependency ───────────────────────────────────────────────────────


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    config: ZenSenseiConfig | None = None,
) -> dict[str, Any]:
    """
    FastAPI dependency that extracts and validates the current user from
    the ``Authorization: Bearer <token>`` header.

    Raises:
        HTTPException 401 if the token is missing, malformed, or invalid.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or not credentials.credentials:
        raise credentials_exception

    payload = verify_token(
        credentials.credentials,
        token_type="access",
        config=config,
    )
    if payload is None:
        raise credentials_exception

    return payload


async def get_current_active_user(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    FastAPI dependency that additionally checks the ``is_active`` claim.

    Raises:
        HTTPException 403 if the account is marked inactive.
    """
    if not current_user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )
    return current_user
