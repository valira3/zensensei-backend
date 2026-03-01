"""
ZenSensei Integration Service - Pydantic Schemas

Request/response models for all Integration Service API endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from shared.models.integrations import IntegrationCategory, IntegrationStatus


# ─── Integration list / detail ──────────────────────────────────────────────────────


class IntegrationSummary(BaseModel):
    id: str
    name: str
    category: IntegrationCategory
    icon_name: str
    description: str
    supports_webhook: bool = False
    required_scopes: list[str] = Field(default_factory=list)


class IntegrationDetail(IntegrationSummary):
    oauth_url_template: str | None = None
    status: IntegrationStatus = IntegrationStatus.AVAILABLE
    last_synced_at: datetime | None = None
    error_message: str | None = None
    sync_cursor: str | None = None
    connected_at: datetime | None = None
    scopes_granted: list[str] = Field(default_factory=list)


class IntegrationListResponse(BaseModel):
    total: int
    items: list[IntegrationSummary]
    by_category: dict[str, list[IntegrationSummary]]


class IntegrationDetailResponse(BaseModel):
    data: IntegrationDetail


# ─── Connected integrations ───────────────────────────────────────────────────────


class ConnectedIntegration(BaseModel):
    id: str
    name: str
    category: IntegrationCategory
    icon_name: str
    status: IntegrationStatus
    connected_at: datetime
    last_synced_at: datetime | None = None
    error_message: str | None = None
    scopes_granted: list[str] = Field(default_factory=list)


class ConnectedIntegrationsResponse(BaseModel):
    total: int
    items: list[ConnectedIntegration]


# ─── OAuth flow ──────────────────────────────────────────────────────────────────


class OAuthStartRequest(BaseModel):
    redirect_uri: str
    scopes: list[str] = Field(default_factory=list)
    state: str | None = None


class OAuthStartResponse(BaseModel):
    authorization_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str
    redirect_uri: str


class OAuthCallbackResponse(BaseModel):
    integration_id: str
    scopes_granted: list[str]
    connected_at: datetime


class DisconnectResponse(BaseModel):
    integration_id: str
    disconnected: bool = True


# ─── Sync status ──────────────────────────────────────────────────────────────────


class SyncStatusResponse(BaseModel):
    integration_id: str
    status: IntegrationStatus
    last_synced_at: datetime | None = None
    next_sync_at: datetime | None = None
    error_message: str | None = None
    sync_cursor: str | None = None


class SyncTriggerResponse(BaseModel):
    integration_id: str
    job_id: str
    message: str = "Sync job enqueued"


# ─── Webhooks ─────────────────────────────────────────────────────────────────────


class WebhookVerificationRequest(BaseModel):
    challenge: str | None = None
    type: str | None = None


class WebhookAckResponse(BaseModel):
    provider: str
    received_at: datetime
    status: str = "queued"
