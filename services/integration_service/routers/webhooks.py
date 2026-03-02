"""
ZenSensei Integration Service - Webhooks Router

Receives and processes inbound webhooks from third-party platforms.

Endpoints:
    POST /webhooks/{provider}              Receive an inbound webhook
    GET  /webhooks/providers               List registered providers
    GET  /webhooks/events                  List recent webhook events
    POST /webhooks/test/{provider}         Send a test/ping to a provider
    GET  /webhooks/events/{event_id}       Get a specific webhook event
    POST /webhooks/replay/{event_id}       Replay a past webhook event
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_user
from shared.models.base import BaseResponse

from services.integration_service.schemas import (
    WebhookEvent,
    WebhookEventListResponse,
    WebhookProvider,
    WebhookProviderListResponse,
    WebhookTestResponse,
)
from services.integration_service.services.webhook_service import (
    WebhookService,
    get_webhook_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# ---------------------------------------------------------------------------
# Supported providers and their signature-verification configs
# ---------------------------------------------------------------------------

_PROVIDER_CONFIGS: dict[str, dict[str, Any]] = {
    "github": {
        "header": "x-hub-signature-256",
        "prefix": "sha256=",
        "algorithm": "sha256",
        "secret_env": "GITHUB_WEBHOOK_SECRET",
    },
    "stripe": {
        "header": "stripe-signature",
        "prefix": "",
        "algorithm": "sha256",
        "secret_env": "STRIPE_WEBHOOK_SECRET",
        "stripe_style": True,
    },
    "notion": {
        "header": "x-notion-signature",
        "prefix": "v0=",
        "algorithm": "sha256",
        "secret_env": "NOTION_WEBHOOK_SECRET",
    },
    "google": {
        "header": "x-goog-signature",
        "prefix": "",
        "algorithm": "sha256",
        "secret_env": "GOOGLE_WEBHOOK_SECRET",
    },
}


# ---------------------------------------------------------------------------
# Signature verification helpers
# ---------------------------------------------------------------------------


async def _get_raw_body(request: Request) -> bytes:
    """Read and return the raw request body (cached on the request scope)."""
    if not hasattr(request.state, "_body"):
        request.state._body = await request.body()
    return request.state._body  # type: ignore[no-any-return]


def _verify_github_signature(body: bytes, secret: str, header_value: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_value)


def _verify_stripe_signature(
    body: bytes,
    secret: str,
    header_value: str,
    tolerance_seconds: int = 300,
) -> bool:
    """Stripe uses a timestamp + signed payload scheme."""
    parts = {k: v for part in header_value.split(",") for k, v in [part.split("=", 1)]}
    ts = parts.get("t", "")
    sig = parts.get("v1", "")
    if not ts or not sig:
        return False
    if abs(time.time() - int(ts)) > tolerance_seconds:
        return False
    signed_payload = f"{ts}.{body.decode()}"
    expected = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _verify_generic_signature(
    body: bytes,
    secret: str,
    header_value: str,
    prefix: str,
    algorithm: str,
) -> bool:
    digestmod = getattr(hashlib, algorithm, hashlib.sha256)
    expected = prefix + hmac.new(secret.encode(), body, digestmod).hexdigest()
    return hmac.compare_digest(expected, header_value)


async def _verify_webhook_signature(
    provider: str,
    request: Request,
    raw_body: bytes,
) -> None:
    """
    Enforce HMAC signature verification for the given provider.
    Raises HTTP 401 if the signature is missing or invalid.
    Raises HTTP 400 if the provider is unknown.
    """
    import os

    config = _PROVIDER_CONFIGS.get(provider)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown webhook provider: '{provider}'",
        )

    header_name = config["header"]
    sig_header = request.headers.get(header_name)
    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing signature header '{header_name}' for provider '{provider}'",
        )

    secret = os.environ.get(config["secret_env"], "")
    if not secret:
        logger.warning(
            "Webhook secret not configured for provider '%s' (env: %s)",
            provider,
            config["secret_env"],
        )
        # Fail closed: if the secret is not set, reject the request
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook signature verification not configured",
        )

    if config.get("stripe_style"):
        valid = _verify_stripe_signature(raw_body, secret, sig_header)
    elif config["prefix"] == "sha256=":  # GitHub style
        valid = _verify_github_signature(raw_body, secret, sig_header)
    else:
        valid = _verify_generic_signature(
            raw_body, secret, sig_header, config["prefix"], config["algorithm"]
        )

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _svc() -> WebhookService:
    return get_webhook_service()


Svc = Annotated[WebhookService, Depends(_svc)]
CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.post(
    "/{provider}",
    response_class=ORJSONResponse,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=True,
)
async def receive_webhook(
    provider: str,
    request: Request,
    svc: Svc,
) -> ORJSONResponse:
    """Receive an inbound webhook from a third-party provider.

    Signature verification is enforced for all registered providers.
    The raw body is read once and cached on the request state to avoid
    double-consumption issues with FastAPI's body parsing.
    """
    raw_body = await _get_raw_body(request)
    await _verify_webhook_signature(provider, request, raw_body)

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    event: WebhookEvent = await svc.process_webhook(
        provider=provider,
        payload=payload,
        headers=dict(request.headers),
    )
    return ORJSONResponse(
        BaseResponse(data={"event_id": event.id, "queued": True}).model_dump(),
        status_code=status.HTTP_202_ACCEPTED,
    )


@router.get(
    "/providers",
    response_class=ORJSONResponse,
    status_code=status.HTTP_200_OK,
)
async def list_providers(
    svc: Svc,
    current_user: CurrentUser,
) -> ORJSONResponse:
    """List all registered webhook providers. Requires authentication."""
    result: WebhookProviderListResponse = await svc.list_providers()
    return ORJSONResponse(BaseResponse(data=result.model_dump()).model_dump())


@router.get(
    "/events",
    response_class=ORJSONResponse,
    status_code=status.HTTP_200_OK,
)
async def list_webhook_events(
    svc: Svc,
    current_user: CurrentUser,
    limit: Optional[int] = Query(50, ge=1, le=500),
    offset: Optional[int] = Query(0, ge=0),
    provider: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
) -> ORJSONResponse:
    """List recent webhook events. Requires authentication."""
    result: WebhookEventListResponse = await svc.list_events(
        limit=limit or 50,
        offset=offset or 0,
        provider=provider,
        status_filter=status_filter,
    )
    return ORJSONResponse(BaseResponse(data=result.model_dump()).model_dump())


@router.post(
    "/test/{provider}",
    response_class=ORJSONResponse,
    status_code=status.HTTP_200_OK,
)
async def test_webhook(
    provider: str,
    svc: Svc,
    current_user: CurrentUser,
) -> ORJSONResponse:
    """Send a test ping to a provider. Requires authentication."""
    result: WebhookTestResponse = await svc.send_test_webhook(provider=provider)
    return ORJSONResponse(BaseResponse(data=result.model_dump()).model_dump())


@router.get(
    "/events/{event_id}",
    response_class=ORJSONResponse,
    status_code=status.HTTP_200_OK,
)
async def get_webhook_event(
    event_id: str,
    svc: Svc,
    current_user: CurrentUser,
) -> ORJSONResponse:
    """Get a specific webhook event by ID. Requires authentication."""
    event: WebhookEvent = await svc.get_event(event_id=event_id)
    return ORJSONResponse(BaseResponse(data=event.model_dump()).model_dump())


@router.post(
    "/replay/{event_id}",
    response_class=ORJSONResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def replay_webhook_event(
    event_id: str,
    svc: Svc,
    current_user: CurrentUser,
) -> ORJSONResponse:
    """Replay a past webhook event. Requires authentication."""
    event: WebhookEvent = await svc.replay_event(event_id=event_id)
    return ORJSONResponse(
        BaseResponse(data={"event_id": event.id, "replayed": True}).model_dump(),
        status_code=status.HTTP_202_ACCEPTED,
    )
