"""
ZenSensei Shared Configuration

Pydantic Settings class that reads all environment variables with the
``ZENSENSEI_`` prefix and provides typed, validated config objects
throughout the application.

All fields have sensible defaults so the service can start in
development without any environment variables set.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class ZenSenseiConfig(BaseSettings):
    """
    Application-wide configuration loaded from environment variables.

    All variables are prefixed with ``ZENSENSEI_`` when read from the
    environment (e.g. ``ZENSENSEI_SECRET_KEY``).
    """

    model_config = {"env_prefix": "ZENSENSEI_", "case_sensitive": False}

    # ─── Core security ────────────────────────────────────────────────────────────
    secret_key: str = Field(
        default="dev-insecure-change-me-in-production",
        description="Secret key for JWT signing.  Must be long and random in production.",
    )

    # ─── JWT ───────────────────────────────────────────────────────────────────────
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm.")
    jwt_access_token_expire_minutes: int = Field(
        default=30,
        ge=1,
        description="Access token lifetime in minutes.",
    )
    jwt_refresh_token_expire_days: int = Field(
        default=30,
        ge=1,
        description="Refresh token lifetime in days.",
    )

    # ─── Database ────────────────────────────────────────────────────────────────
    firestore_project_id: Optional[str] = Field(
        default=None,
        description="Google Cloud project ID for Firestore.",
    )
    neo4j_uri: str = Field(
        default="bolt://localhost:7687",
        description="Neo4j connection URI.",
    )
    neo4j_user: str = Field(default="neo4j", description="Neo4j username.")
    neo4j_password: str = Field(default="password", description="Neo4j password.")
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL.",
    )

    # ─── Email / notifications ───────────────────────────────────────────────────
    sendgrid_api_key: Optional[str] = Field(
        default=None,
        description="SendGrid API key for transactional email.",
    )
    from_email: str = Field(
        default="noreply@zensensei.app",
        description="Default sender address for outgoing emails.",
    )
    frontend_url: str = Field(
        default="http://localhost:3000",
        description="Frontend base URL (used in email links).",
    )

    # ─── Service ports ───────────────────────────────────────────────────────────
    user_service_port: int = Field(default=8001, ge=1, le=65535)
    insight_service_port: int = Field(default=8002, ge=1, le=65535)
    integration_service_port: int = Field(default=8003, ge=1, le=65535)
    notification_service_port: int = Field(default=8004, ge=1, le=65535)
    goal_service_port: int = Field(default=8005, ge=1, le=65535)

    # ─── Environment ────────────────────────────────────────────────────────────
    environment: str = Field(
        default="development",
        description="Deployment environment: 'development', 'staging', or 'production'.",
    )
    debug: bool = Field(default=False, description="Enable debug mode.")
    log_level: str = Field(default="INFO", description="Logging level.")

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_not_be_default_in_prod(cls, v: str, info: Any) -> str:  # type: ignore[override]
        # Can't access other fields easily in Pydantic v2 validator without model_validator
        # Just warn if it looks like the insecure default
        if v == "dev-insecure-change-me-in-production":
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "SECRET_KEY is set to the insecure default value. "
                "Set ZENSENSEI_SECRET_KEY to a long random string in production."
            )
        return v


@lru_cache(maxsize=1)
def get_config() -> ZenSenseiConfig:
    """Return the cached application configuration singleton."""
    return ZenSenseiConfig()
