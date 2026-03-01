"""
ZenSensei User Service - Configuration

Extends the shared ZenSenseiConfig with user-service-specific settings.
"""

from __future__ import annotations

import sys
import os

# Ensure shared library is importable when running standalone
_shared_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _shared_path not in sys.path:
    sys.path.insert(0, _shared_path)

from functools import lru_cache

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from shared.config import ZenSenseiConfig


class UserServiceConfig(ZenSenseiConfig):
    """
    User-service-specific configuration.

    Inherits all shared settings and adds overrides / additional fields
    specific to authentication, token management, and email workflows.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Service Identity ───────────────────────────────────────────────────────
    service_name: str = "user-service"
    service_version: str = "1.0.0"

    # ─── Password Policy ───────────────────────────────────────────────────────
    password_min_length: int = Field(default=12, ge=8, le=128)
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_digit: bool = True
    password_require_symbol: bool = True

    # ─── Auth / Session ────────────────────────────────────────────────────────
    # Maximum failed login attempts before temporary lockout
    max_login_attempts: int = Field(default=5, ge=1, le=20)
    # Lockout duration in seconds after max failed attempts
    login_lockout_seconds: int = Field(default=900, ge=60)  # 15 minutes

    # ─── Password Reset ───────────────────────────────────────────────────────
    # How long password reset tokens are valid (seconds)
    password_reset_token_expire_seconds: int = Field(default=3600, ge=300)  # 1 hour

    # ─── Email ──────────────────────────────────────────────────────────────────
    app_frontend_url: str = "http://localhost:3000"
    password_reset_email_template_id: str = ""

    # ─── Onboarding ────────────────────────────────────────────────────────────
    # Ordered list of steps that must be completed for full onboarding
    onboarding_steps: list[str] = Field(
        default=["life_stage", "interests", "integrations"],
        description="Ordered onboarding steps",
    )

    @property
    def password_reset_url_template(self) -> str:
        return f"{self.app_frontend_url}/auth/reset-password?token={{token}}"


@lru_cache(maxsize=1)
def get_user_service_config() -> UserServiceConfig:
    """Return a cached singleton UserServiceConfig instance."""
    return UserServiceConfig()
