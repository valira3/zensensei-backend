"""
ZenSensei Integration Service - Webhooks Router

Receives and processes inbound webhooks from external providers.
Handles challenge/verification requests and routes events to the sync engine.

Endpoints
---------
POST /webhooks/{provider}          Receive webhook events from a provider
POST /webhooks/verify/{provider}   Webhook verification (challenge/response)

Verification strategies
-----------------------
Slack:      Verifies ``X-Slack-Signature`` HMAC-SHA256 header
Google:     Returns the ``challenge`` field from the JSON body
Notion:     Passes Notion-Webhook-Signature header verification
Stripe:     Verifies ``Stripe-Signature`` header
GitHub:     Verifies ``X-Hub-Signature-256`` HMAC-SHA256 header
Default:    Echoes back any ``challenge`` field present in the body
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse

from shared.config import get_config

from integration_service.schemas import WebhookAckResponse, WebhookVerificationRequest
from integration_service.services.sync_engine import SyncEngine, get_sync_engine

logger = logging.getLogger(__name__)
_cfg = get_config()

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


# ─── Shared webhook secret resolver ──────────────────────────────────────────

import os as _os

_WEBHOOK_SECRETS: dict[str, str] = {
    "slack": _os.environ.get("SLACK_SIGNING_SECRET", ""),
    "stripe": _os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
    "github": _os.environ.get("GITHUB_WEBHOOK_SECRET", ""),
    "notion": _os.environ.get("NOTION_WEBHOOK_SECRET", ""),
    "plaid": _os.environ.get("PLAID_WEBHOOK_SECRET", ""),
}


# ─── Verification endpoint ────────────────────────────────────────────────────


@router.post(
    "/verify/{provider}",
    summary="Webhook verification endpoint",
    description=(
        "Handles provider-specific verification challenges. "
        "Called once when registering a webhook URL with a provider."
    ),
)
async def verify_webhook(
    provider: str,
    request: Request,
) -> Any:
    """
    Handle webhook challenge/response verification for each provider.

    Most providers send a one-time verification request when you register
    a webhook URL. This endpoint responds appropriately for each provider.
    """
    body_bytes = await request.body()

    # Google (Calendar, Gmail, etc.) — returns challenge field as-is
    if provider.startswith("google"):
        try:
            body = json.loads(body_bytes)
            challenge = body.get("challenge")
            if challenge:
                return JSONResponse(content={"challenge": challenge})
        except json.JSONDecodeError:
            pass
        return JSONResponse(content={"status": "ok"})

    # Slack URL verification
    if provider == "slack":
        try:
            body = json.loads(body_bytes)
            if body.get("type") == "url_verification":
                return JSONResponse(content={"challenge": body["challenge"]})
        except json.JSONDecodeError:
            pass

    # Notion webhook verification
    if provider == "notion":
        try:
            body = json.loads(body_bytes)
            if "challenge" in body:
                return JSONResponse(content={"challenge": body["challenge"]})
        except json.JSONDecodeError:
            pass

    # Generic: echo challenge if present
    try:
        body = json.loads(body_bytes)
        if "challenge" in body:
            return JSONResponse(content={"challenge": body["challenge"]})
    except (json.JSONDecodeError, TypeError):
        pass

    return JSONResponse(content={"status": "verified"})


# ─── Event reception endpoint ──────────────────────────────────────────────────


@router.post(
    "/{provider}",
    response_model=WebhookAckResponse,
    status_code=status.HTTP_200_OK,
    summary="Receive webhook event",
    description=(
        "Receives incoming webhook payloads from external providers. "
        "Validates signatures where applicable, then routes the event "
        "to the sync engine for processing."
    ),
)
async def receive_webhook(
    provider: str,
    request: Request,
    x_slack_signature: str | None = Header(default=None),
    x_slack_request_timestamp: str | None = Header(default=None),
    stripe_signature: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
    x_notion_signature: str | None = Header(default=None),
) -> WebhookAckResponse:
    body_bytes = await request.body()

    # ── Signature verification ───────────────────────────────────────────────
    secret = _WEBHOOK_SECRETS.get(provider, "")

    if provider == "slack" and secret:
        _verify_slack_signature(body_bytes, x_slack_signature, x_slack_request_timestamp, secret)

    elif provider == "stripe" and secret:
        _verify_stripe_signature(body_bytes, stripe_signature, secret)

    elif provider == "github" and secret:
        _verify_github_signature(body_bytes, x_hub_signature_256, secret)

    elif provider == "notion" and x_notion_signature and secret:
        _verify_notion_signature(body_bytes, x_notion_signature, secret)

    # ── Parse payload ────────────────────────────────────────────────────────
    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError:
        payload = {"raw": body_bytes.decode("utf-8", errors="replace")}

    # ── Dispatch to sync engine ───────────────────────────────────────────────
    sync_engine: SyncEngine = get_sync_engine()
    import asyncio
    asyncio.create_task(
        sync_engine.process_webhook(provider=provider, payload=payload)
    )

    return WebhookAckResponse(
        provider=provider,
        received_at=datetime.now(tz=timezone.utc),
        status="queued",
    )


# ─── Signature verification helpers ─────────────────────────────────────────────


def _verify_slack_signature(
    body: bytes,
    signature: str | None,
    timestamp: str | None,
    secret: str,
) -> None:
    """Verify Slack HMAC-SHA256 request signature."""
    if not signature or not timestamp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Slack signature headers",
        )
    basestring = f"v0:{timestamp}:{body.decode()}"
    computed = "v0=" + hmac.new(
        secret.encode(), basestring.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(computed, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack signature",
        )


def _verify_stripe_signature(
    body: bytes,
    signature: str | None,
    secret: str,
) -> None:
    """Verify Stripe webhook signature."""
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Stripe-Signature header",
        )
    try:
        import stripe  # type: ignore
        stripe.Webhook.construct_event(body, signature, secret)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Stripe signature: {exc}",
        )


def _verify_github_signature(
    body: bytes,
    signature: str | None,
    secret: str,
) -> None:
    """Verify GitHub HMAC-SHA256 webhook signature."""
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256 header",
        )
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GitHub signature",
        )


def _verify_notion_signature(
    body: bytes,
    signature: str | None,
    secret: str,
) -> None:
    """Verify Notion webhook signature."""
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Notion-Webhook-Signature header",
        )
    expected = "v1=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Notion signature",
        )
