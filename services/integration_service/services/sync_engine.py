"""
ZenSensei Integration Service - Sync Engine

Orchestrates data synchronisation between external services and the
ZenSensei knowledge graph. Publishes sync results to Google Cloud Pub/Sub
for downstream processing by the AI service.

Key responsibilities
--------------------
- Pull data from external APIs using stored OAuth tokens
- Transform raw API responses into ZenSensei event / node payloads
- Publish transformed payloads to the ``zensensei.sync.events`` Pub/Sub topic
- Track sync cursors (last-sync timestamps / page tokens) in Firestore
- Handle token refresh on 401 responses
- Process incoming webhooks and route to the appropriate handler
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import httpx

from shared.config import get_config
from shared.database.firestore import get_firestore_client
from shared.events.publisher import get_publisher
from shared.models.integrations import IntegrationStatus

from integration_service.integrations import registry

logger = logging.getLogger(__name__)
_cfg = get_config()

_USERS_COL = "users"
_INTEGRATIONS_SUB = "integrations"
_PUBSUB_TOPIC = "zensensei.sync.events"


class SyncEngine:
    """
    Coordinates data pulls and webhook processing for all integrations.

    Instance is a singleton (see ``get_sync_engine``). Methods are async-safe.
    """

    def __init__(self) -> None:
        self._fs = get_firestore_client()
        self._publisher = get_publisher()
        self._http: httpx.AsyncClient | None = None

    # ─── Lifecycle ───────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Initialise shared HTTP client and validate Pub/Sub connection."""
        self._http = httpx.AsyncClient(timeout=60.0)
        await self._publisher.connect()

    async def close(self) -> None:
        """Close HTTP client and Pub/Sub publisher."""
        if self._http:
            await self._http.aclose()
            self._http = None
        await self._publisher.close()

    # ─── Main sync entry point ──────────────────────────────────────────────────

    async def sync_integration(
        self,
        user_id: str,
        integration_id: str,
    ) -> None:
        """
        Pull data from an external service and publish events to Pub/Sub.

        This method is fire-and-forget; errors are caught and logged rather
        than propagated to the caller.
        """
        logger.info("sync.start", extra={"user_id": user_id, "integration": integration_id})

        try:
            # Load stored tokens
            token_doc = await self._load_tokens(user_id, integration_id)
            if not token_doc:
                logger.warning("sync.no_tokens", extra={"user_id": user_id, "integration": integration_id})
                return

            access_token: str = token_doc.get("access_token", "")
            sync_cursor: str | None = token_doc.get("sync_cursor")

            meta = registry.get_by_id(integration_id)
            if not meta:
                logger.error("sync.unknown_integration", extra={"integration": integration_id})
                return

            # Pull data from the provider
            raw_events = await self._fetch_events(
                integration_id=integration_id,
                access_token=access_token,
                cursor=sync_cursor,
                meta=meta,
            )

            # Transform and publish each event
            published = 0
            for raw in raw_events:
                payload = _transform_event(integration_id, raw)
                await self._publisher.publish(_PUBSUB_TOPIC, payload)
                published += 1

            # Update sync cursor in Firestore
            new_cursor = _extract_cursor(integration_id, raw_events)
            await self._update_sync_state(
                user_id=user_id,
                integration_id=integration_id,
                cursor=new_cursor,
                error=None,
            )

            logger.info(
                "sync.complete",
                extra={"user_id": user_id, "integration": integration_id, "published": published},
            )

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                # Attempt token refresh and retry once
                logger.info("sync.token_expired_refreshing", extra={"user_id": user_id, "integration": integration_id})
                try:
                    from integration_service.services.oauth_service import get_oauth_service
                    oauth_svc = get_oauth_service()
                    await oauth_svc.refresh_token(user_id, integration_id)
                    # Retry
                    await self.sync_integration(user_id, integration_id)
                except Exception as refresh_exc:
                    await self._update_sync_state(
                        user_id=user_id,
                        integration_id=integration_id,
                        cursor=None,
                        error=f"Token refresh failed: {refresh_exc}",
                    )
            else:
                err = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
                await self._update_sync_state(user_id=user_id, integration_id=integration_id, cursor=None, error=err)
                logger.error("sync.http_error", extra={"user_id": user_id, "integration": integration_id, "error": err})

        except Exception as exc:
            err = str(exc)
            await self._update_sync_state(user_id=user_id, integration_id=integration_id, cursor=None, error=err)
            logger.error("sync.error", extra={"user_id": user_id, "integration": integration_id, "error": err}, exc_info=True)

    # ─── Webhook processing ─────────────────────────────────────────────────────

    async def process_webhook(
        self,
        provider: str,
        payload: dict[str, Any],
    ) -> None:
        """
        Process an inbound webhook payload.

        Transforms the payload into a ZenSensei event and publishes it
        to the sync events topic.
        """
        try:
            event = _transform_event(provider, payload)
            await self._publisher.publish(_PUBSUB_TOPIC, event)
            logger.info("webhook.published", extra={"provider": provider})
        except Exception as exc:
            logger.error("webhook.error", extra={"provider": provider, "error": str(exc)}, exc_info=True)

    # ─── Internal helpers ────────────────────────────────────────────────────────

    async def _fetch_events(
        self,
        integration_id: str,
        access_token: str,
        cursor: str | None,
        meta: Any,
    ) -> list[dict[str, Any]]:
        """
        Fetch raw events from the external API.

        Dispatches to integration-specific fetchers where available;
        falls back to a generic paginated GET.
        """
        fetcher = _get_fetcher(integration_id)
        if fetcher:
            http = self._http or httpx.AsyncClient(timeout=60.0)
            return await fetcher(http, access_token, cursor)

        # Generic fallback
        if not meta.base_api_url:
            return []

        http = self._http or httpx.AsyncClient(timeout=60.0)
        params: dict[str, Any] = {}
        if cursor:
            params["page_token"] = cursor

        resp = await http.get(
            meta.base_api_url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("items", "data", "events", "results", "records"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []

    async def _load_tokens(
        self,
        user_id: str,
        integration_id: str,
    ) -> dict[str, Any] | None:
        path = f"{_USERS_COL}/{user_id}/{_INTEGRATIONS_SUB}/{integration_id}"
        return await self._fs.get_document(path)

    async def _update_sync_state(
        self,
        user_id: str,
        integration_id: str,
        cursor: str | None,
        error: str | None,
    ) -> None:
        path = f"{_USERS_COL}/{user_id}/{_INTEGRATIONS_SUB}/{integration_id}"
        updates: dict[str, Any] = {
            "last_synced_at": datetime.now(tz=timezone.utc).isoformat(),
            "error_message": error,
        }
        if cursor is not None:
            updates["sync_cursor"] = cursor
        if error:
            updates["status"] = IntegrationStatus.ERROR
        await self._fs.update_document(path, updates)


# ─── Singleton accessor ───────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_sync_engine() -> SyncEngine:
    """Return the global SyncEngine singleton."""
    return SyncEngine()


# ─── Transform helpers ──────────────────────────────────────────────────────────


def _transform_event(
    integration_id: str,
    raw: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert a raw API response item into a ZenSensei sync event.

    The event schema is intentionally generic so that the AI service can
    process events from any integration uniformly.
    """
    return {
        "source": integration_id,
        "event_type": raw.get("type") or raw.get("kind") or "unknown",
        "payload": raw,
        "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def _extract_cursor(
    integration_id: str,
    events: list[dict[str, Any]],
) -> str | None:
    """Extract the sync cursor from the last event, if applicable."""
    if not events:
        return None
    last = events[-1]
    for key in ("next_page_token", "page_token", "cursor", "next_cursor", "after"):
        if key in last:
            return str(last[key])
    return None


def _get_fetcher(integration_id: str) -> Any:
    """
    Return an integration-specific async fetcher function, or None.

    Fetcher signature: async (http, access_token, cursor) -> list[dict]
    """
    _FETCHERS: dict[str, Any] = {}
    return _FETCHERS.get(integration_id)
