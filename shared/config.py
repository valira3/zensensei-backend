"""
ZenSensei Shared Configuration

Pydantic Settings class that reads all environment variables with
sensible defaults for local development.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ZenSenseiConfig(BaseSettings):
    """Central configuration for all ZenSensei services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Core ───────────────────────────────────────────────────────────────────
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    secret_key: str = "change-me-in-production"
    api_version: str = "v1"

    # ─── Service Ports ────────────────────────────────────────────────────────────
    user_service_port: int = Field(default=8001, ge=1024, le=65535)
    graph_query_service_port: int = Field(default=8002, ge=1024, le=65535)
    ai_reasoning_service_port: int = Field(default=8003, ge=1024, le=65535)
    integration_service_port: int = Field(default=8004, ge=1024, le=65535)
    notification_service_port: int = Field(default=8005, ge=1024, le=65535)
    analytics_service_port: int = Field(default=8006, ge=1024, le=65535)
    api_gateway_port: int = Field(default=4000, ge=1024, le=65535)

    # ─── Neo4j ─────────────────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "localdev"
    neo4j_max_connection_pool_size: int = 50
    neo4j_connection_timeout: int = 30

    # ─── Redis ───────────────────────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_password: str = ""
    redis_db: int = 0
    redis_max_connections: int = 20
    redis_socket_timeout: float = 5.0

    # ─── Firebase / Identity Platform ───────────────────────────────────────────
    firebase_project_id: str = "zensensei-platform"
    firebase_credentials_path: str = "./credentials/firebase-sa.json"

    # ─── Google Cloud ────────────────────────────────────────────────────────────
    gcp_project_id: str = "zensensei-platform"
    gcp_region: str = "us-central1"

    # ─── BigQuery ─────────────────────────────────────────────────────────────────
    bigquery_dataset: str = "analytics"

    # ─── Pub/Sub Topics ───────────────────────────────────────────────────────────
    pubsub_user_events_topic: str = "user-events"
    pubsub_graph_updates_topic: str = "graph-updates"
    pubsub_ai_jobs_topic: str = "ai-jobs"

    # ─── AI / ML ───────────────────────────────────────────────────────────────
    gemini_model: str = "gemini-1.5-pro"
    vertex_ai_location: str = "us-central1"

    # ─── SendGrid ───────────────────────────────────────────────────────────────
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "noreply@zensensei.net"

    # ─── Integration OAuth ──────────────────────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    plaid_client_id: str = ""
    plaid_secret: str = ""

    # ─── JWT ────────────────────────────────────────────────────────────────────
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # ─── CORS ───────────────────────────────────────────────────────────────────
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:4000",
        "https://app.zensensei.net",
    ]

    # ─── Rate Limiting ────────────────────────────────────────────────────────────
    rate_limit_requests_per_minute: int = 60
    rate_limit_burst: int = 10

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Support comma-separated string from environment variable."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache(maxsize=1)
def get_config() -> ZenSenseiConfig:
    """Return a cached singleton config instance."""
    return ZenSenseiConfig()
