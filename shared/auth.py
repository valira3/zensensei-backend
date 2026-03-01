"""
ZenSensei Shared Auth

JWT token creation/verification, password hashing, and a
FastAPI dependency for retrieving the current authenticated user.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from shared.config import ZenSenseiConfig, get_config

# ─── Password hashing ───────────────────────────────────────────────────────────────

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Return a bcrypt hash of the supplied plain-text password."""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if *plain_password* matches *hashed_password*."""
    return _pwd_context.verify(plain_password, hashed_password)


# ─── Token creation ───────────────────────────────────────────────────────────────

def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
    config: ZenSenseiConfig | None = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        data: Claims to embed in the token (must include a ``sub`` field).
        expires_delta: Custom expiry override; defaults to
            ``JWT_ACCESS_TOKEN_EXPIRE_MINUTES`` from config.
        config: Optional config override for testing.

    Returns:
        Encoded JWT string.
    """
    cfg = config or get_config()
    payload = data.copy()

    expire = datetime.now(tz=timezone.utc) + (
        expires_delta or timedelta(minutes=cfg.jwt_access_token_expire_minutes)
    )
    payload.update(
        {
            "exp": expire,
            "iat": datetime.now(tz=timezone.utc),
            "type": "access",
        }
    )
    return jwt.encode(payload, cfg.jwt_secret_key, algorithm=cfg.jwt_algorithm)


def create_refresh_token(
    data: dict[str, Any],
    config: ZenSenseiConfig | None = None,
) -> str:
    """
    Create a signed JWT refresh token with a longer expiry.

    Args:
        data: Claims to embed (must include a ``sub`` field).
        config: Optional config override for testing.

    Returns:
        Encoded JWT string.
    """
    cfg = config or get_config()
    payload = data.copy()

    expire = datetime.now(tz=timezone.utc) + timedelta(days=cfg.jwt_refresh_token_expire_days)
    payload.update(
        {
            "exp": expire,
            "iat": datetime.now(tz=timezone.utc),
            "type": "refresh",
        }
    )
    return jwt.encode(payload, cfg.jwt_secret_key, algorithm=cfg.jwt_algorithm)


# ─── Token verification ────────────────────────────────────────────────────────────

def verify_token(
    token: str,
    expected_type: str = "access",
    config: ZenSenseiConfig | None = None,
) -> dict[str, Any]:
    """
    Decode and validate a JWT token.

    Args:
        token: The raw JWT string.
        expected_type: ``"access"`` or ``"refresh"`` — checked against the
            ``type`` claim embedded at creation time.
        config: Optional config override for testing.

    Returns:
        Decoded token payload dict.

    Raises:
        HTTPException 401 if the token is invalid, expired, or the wrong type.
    """
    cfg = config or get_config()
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            cfg.jwt_secret_key,
            algorithms=[cfg.jwt_algorithm],
        )
    except JWTError:
        raise credentials_exception

    token_type: str | None = payload.get("type")
    if token_type != expected_type:
        raise credentials_exception

    sub: str | None = payload.get("sub")
    if sub is None:
        raise credentials_exception

    return payload


# ─── FastAPI dependency ────────────────────────────────────────────────────────────

_http_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    config: ZenSenseiConfig = Depends(get_config),
) -> dict[str, Any]:
    """
    FastAPI dependency that extracts and validates the current user
    from the ``Authorization: Bearer <token>`` header.

    Returns:
        The decoded JWT payload dict, which includes at minimum
        ``sub`` (user ID) and standard JWT claims.

    Raises:
        HTTPException 401 on invalid / missing / expired token.
    """
    return verify_token(credentials.credentials, expected_type="access", config=config)


async def get_current_active_user(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Extends ``get_current_user`` by checking the ``is_active`` claim.

    Raises:
        HTTPException 403 if the account is disabled.
    """
    if not current_user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    return current_user
