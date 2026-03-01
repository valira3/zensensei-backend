"""
ZenSensei Integration Service - Integrations Router

Handles the integration catalogue, OAuth flow management, sync operations,
and connection status for all 67 registered integrations.

Endpoints
---------
GET  /integrations                        List all available integrations
GET  /integrations/connected              List user's connected integrations
GET  /integrations/{id}                   Get integration detail + user status
POST /integrations/{id}/connect           Start OAuth / link flow
POST /integrations/{id}/callback          OAuth callback handler
DELETE /integrations/{id}/disconnect      Disconnect integration
GET  /integrations/{id}/status            Get sync status
POST /integrations/{id}/sync              Trigger manual sync
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_active_user
from shared.models.integrations import IntegrationCategory, IntegrationStatus

from integration_service.integrations import registry
from integration_service.integrations.base import IntegrationMetadata
from integration_service.schemas import (
    ConnectedIntegration,
    ConnectedIntegrationsResponse,
    DisconnectResponse,
    IntegrationDetail,
    IntegrationDetailResponse,
    IntegrationListResponse,
    IntegrationSummary,
    OAuthCallbackRequest,
    OAuthCallbackResponse,
    OAuthStartRequest,
    OAuthStartResponse,
    SyncStatusResponse,
    SyncTriggerResponse,
)
from integration_service.services.oauth_service import OAuthService, get_oauth_service
from integration_service.services.sync_engine import SyncEngine, get_sync_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["Integrations"])


# ─── Dependency helpers ───────────────────────────────────────────────────────

def _current_user_id(user: dict[str, Any] = Depends(get_current_active_user)) -> str:
    return user["sub"]


def _to_summary(meta: IntegrationMetadata) -> IntegrationSummary:
    return IntegrationSummary(
        id=meta.id,
        name=meta.name,
        category=meta.category,
        icon_name=meta.icon_name,
        description=meta.description,
        supports_webhook=meta.supports_webhook,
        required_scopes=meta.required_scopes,
    )


def _to_detail(
    meta: IntegrationMetadata,
    status_doc: dict[str, Any] | None = None,
) -> IntegrationDetail:
    status_val = IntegrationStatus.AVAILABLE
    last_synced_at = None
    error_message = None
    sync_cursor = None
    connected_at = None
    scopes_granted: list[str] = []

    if status_doc:
        status_val = IntegrationStatus(
            status_doc.get("status", IntegrationStatus.AVAILABLE)
        )
        last_synced_str = status_doc.get("last_synced_at")
        last_synced_at = _parse_dt(last_synced_str)
        connected_str = status_doc.get("connected_at")
        connected_at = _parse_dt(connected_str)
        error_message = status_doc.get("error_message")
        sync_cursor = status_doc.get("sync_cursor")
        scopes_granted = status_doc.get("scopes", [])

    return IntegrationDetail(
        id=meta.id,
        name=meta.name,
        category=meta.category,
        icon_name=meta.icon_name,
        description=meta.description,
        supports_webhook=meta.supports_webhook,
        required_scopes=meta.required_scopes,
        oauth_url_template=meta.oauth_url_template,
        status=status_val,
        last_synced_at=last_synced_at,
        error_message=error_message,
        sync_cursor=sync_cursor,
        connected_at=connected_at,
        scopes_granted=scopes_granted,
    )


def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# ─── Routes ───────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=IntegrationListResponse,
    summary="List all available integrations",
    description=(
        "Returns all 67 registered integrations grouped by category. "
        "Authenticated users also see their per-integration connection status."
    ),
)
async def list_integrations(
    category: IntegrationCategory | None = Query(
        default=None,
        description="Filter by category (e.g. CALENDAR, HEALTH)",
    ),
    user_id: str = Depends(_current_user_id),
    oauth_svc: OAuthService = Depends(get_oauth_service),
) -> IntegrationListResponse:
    # Fetch user's connected integration statuses
    try:
        connected_docs = await oauth_svc.list_connected(user_id)
        status_map = {d["integration_id"]: d for d in connected_docs}
    except Exception:
        status_map = {}

    all_meta = registry.get_all()
    if category:
        all_meta = [m for m in all_meta if m.category == category]

    items: list[IntegrationSummary] = [_to_summary(m) for m in all_meta]

    by_cat: dict[str, list[IntegrationSummary]] = {}
    for item in items:
        by_cat.setdefault(str(item.category), []).append(item)

    return IntegrationListResponse(
        total=len(items),
        items=items,
        by_category=by_cat,
    )


@router.get(
    "/connected",
    response_model=ConnectedIntegrationsResponse,
    summary="List user's connected integrations",
)
async def list_connected_integrations(
    user_id: str = Depends(_current_user_id),
    oauth_svc: OAuthService = Depends(get_oauth_service),
) -> ConnectedIntegrationsResponse:
    connected_docs = await oauth_svc.list_connected(user_id)

    items: list[ConnectedIntegration] = []
    for doc in connected_docs:
        meta = registry.get_by_id(doc["integration_id"])
        if not meta:
            continue
        items.append(
            ConnectedIntegration(
                id=meta.id,
                name=meta.name,
                category=meta.category,
                icon_name=meta.icon_name,
                status=IntegrationStatus(doc.get("status", IntegrationStatus.CONNECTED)),
                connected_at=_parse_dt(doc.get("connected_at")) or datetime.now(tz=timezone.utc),
                last_synced_at=_parse_dt(doc.get("last_synced_at")),
                error_message=doc.get("error_message"),
                scopes_granted=doc.get("scopes", []),
            )
        )

    return ConnectedIntegrationsResponse(total=len(items), items=items)


@router.get(
    "/{integration_id}",
    response_model=IntegrationDetailResponse,
    summary="Get integration details and connection status",
)
async def get_integration(
    integration_id: str,
    user_id: str = Depends(_current_user_id),
    oauth_svc: OAuthService = Depends(get_oauth_service),
) -> IntegrationDetailResponse:
    meta = registry.get_by_id(integration_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_id}' not found",
        )

    try:
        status_doc = await oauth_svc.get_status(user_id, integration_id)
    except Exception:
        status_doc = None

    detail = _to_detail(meta, status_doc)
    return IntegrationDetailResponse(data=detail)


@router.post(
    "/{integration_id}/connect",
    response_model=OAuthStartResponse,
    status_code=status.HTTP_200_OK,
    summary="Start OAuth flow for an integration",
    description=(
        "Generates an authorization URL (or Plaid link token) and stores a "
        "short-lived CSRF state token. Redirect the user to `authorization_url`."
    ),
)
async def start_oauth(
    integration_id: str,
    body: OAuthStartRequest,
    user_id: str = Depends(_current_user_id),
    oauth_svc: OAuthService = Depends(get_oauth_service),
) -> OAuthStartResponse:
    meta = registry.get_by_id(integration_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_id}' not found",
        )

    # Plaid uses a Link token instead of a standard OAuth URL
    if integration_id == "plaid":
        from integration_service.integrations.plaid import PlaidIntegration
        plaid = PlaidIntegration()
        link_data = await plaid.create_link_token(user_id, body.redirect_uri)
        state = body.state or str(uuid.uuid4())
        return OAuthStartResponse(
            authorization_url=link_data.get("link_token", ""),
            state=state,
        )

    try:
        auth_url, state = await oauth_svc.get_oauth_url(
            integration_id=integration_id,
            user_id=user_id,
            redirect_uri=body.redirect_uri,
            scopes=body.scopes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return OAuthStartResponse(authorization_url=auth_url, state=state)


@router.post(
    "/{integration_id}/callback",
    response_model=OAuthCallbackResponse,
    status_code=status.HTTP_200_OK,
    summary="OAuth callback handler",
    description=(
        "Validates the CSRF state token, exchanges the authorization code for "
        "access/refresh tokens, and persists them. Returns connection metadata."
    ),
)
async def oauth_callback(
    integration_id: str,
    body: OAuthCallbackRequest,
    user_id: str = Depends(_current_user_id),
    oauth_svc: OAuthService = Depends(get_oauth_service),
) -> OAuthCallbackResponse:
    meta = registry.get_by_id(integration_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_id}' not found",
        )

    try:
        tokens = await oauth_svc.exchange_code(
            integration_id=integration_id,
            code=body.code,
            state=body.state,
            redirect_uri=body.redirect_uri,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("OAuth callback error for %s: %s", integration_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to exchange authorization code: {exc}",
        )

    scopes = tokens.get("scope", "")
    if isinstance(scopes, str):
        scopes_list = scopes.split()
    else:
        scopes_list = list(scopes)

    return OAuthCallbackResponse(
        integration_id=integration_id,
        scopes_granted=scopes_list,
        connected_at=datetime.now(tz=timezone.utc),
    )


@router.delete(
    "/{integration_id}/disconnect",
    response_model=DisconnectResponse,
    summary="Disconnect integration",
    description="Revokes provider tokens and removes stored credentials.",
)
async def disconnect_integration(
    integration_id: str,
    user_id: str = Depends(_current_user_id),
    oauth_svc: OAuthService = Depends(get_oauth_service),
) -> DisconnectResponse:
    meta = registry.get_by_id(integration_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_id}' not found",
        )

    await oauth_svc.revoke_tokens(user_id, integration_id)
    return DisconnectResponse(integration_id=integration_id)


@router.get(
    "/{integration_id}/status",
    response_model=SyncStatusResponse,
    summary="Get sync status",
    description="Returns the current sync status, last sync timestamp, and any error messages.",
)
async def get_sync_status(
    integration_id: str,
    user_id: str = Depends(_current_user_id),
    oauth_svc: OAuthService = Depends(get_oauth_service),
) -> SyncStatusResponse:
    meta = registry.get_by_id(integration_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_id}' not found",
        )

    status_doc = await oauth_svc.get_status(user_id, integration_id)
    if not status_doc:
        return SyncStatusResponse(
            integration_id=integration_id,
            status=IntegrationStatus.AVAILABLE,
        )

    last_synced_at = _parse_dt(status_doc.get("last_synced_at"))
    next_sync_at = None
    if last_synced_at:
        from datetime import timedelta
        next_sync_at = last_synced_at + timedelta(minutes=meta.poll_interval_minutes)

    return SyncStatusResponse(
        integration_id=integration_id,
        status=IntegrationStatus(status_doc.get("status", IntegrationStatus.CONNECTED)),
        last_synced_at=last_synced_at,
        next_sync_at=next_sync_at,
        error_message=status_doc.get("error_message"),
        sync_cursor=status_doc.get("sync_cursor"),
    )


@router.post(
    "/{integration_id}/sync",
    response_model=SyncTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger manual sync",
    description=(
        "Enqueues an immediate sync job for the integration. "
        "The job runs asynchronously; poll /status to check completion."
    ),
)
async def trigger_sync(
    integration_id: str,
    user_id: str = Depends(_current_user_id),
    oauth_svc: OAuthService = Depends(get_oauth_service),
    sync_engine: SyncEngine = Depends(get_sync_engine),
) -> SyncTriggerResponse:
    meta = registry.get_by_id(integration_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_id}' not found",
        )

    # Verify the user has this integration connected
    status_doc = await oauth_svc.get_status(user_id, integration_id)
    if not status_doc or status_doc.get("status") == IntegrationStatus.AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Integration '{integration_id}' is not connected",
        )

    job_id = str(uuid.uuid4())

    # Fire-and-forget the sync task (don't await)
    import asyncio
    asyncio.create_task(
        sync_engine.sync_integration(user_id, integration_id)
    )

    return SyncTriggerResponse(
        integration_id=integration_id,
        job_id=job_id,
    )
