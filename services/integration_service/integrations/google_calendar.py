"""
ZenSensei Integration Service - Google Calendar Integration

Full implementation of Google Calendar OAuth, event sync, and graph
node transformation.

Graph mapping
-------------
Calendar Event → NodeType.EVENT
  - properties: title, start_time, end_time, location, attendees,
                recurrence, calendar_id, html_link, event_id
  - relationships: PERSON –[ATTENDED]→ EVENT
"""

from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from shared.config import get_config
from shared.models.graph import (
    GraphNode,
    GraphRelationship,
    NodeType,
    RelationshipType,
)
from shared.models.integrations import IntegrationCategory

from .base import Integration, IntegrationMetadata
from .registry import get_by_id

logger = logging.getLogger(__name__)

_cfg = get_config()

# ─── OAuth endpoints ─────────────────────────────────────────────────────────────────────────

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
_CALENDARS_URL = "https://www.googleapis.com/calendar/v3/users/me/calendarList"
_DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]


class GoogleCalendarIntegration(Integration):
    """
    Google Calendar integration.

    Syncs calendar events incrementally using the ``syncToken`` mechanism.
    Initial sync fetches events from the last 30 days; subsequent syncs
    use the stored token for delta updates.
    """

    metadata: IntegrationMetadata = get_by_id("google_calendar")  # type: ignore[assignment]

    # ─── OAuth ───────────────────────────────────────────────────────────────────────────

    async def get_oauth_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: Optional[list[str]] = None,
    ) -> str:
        """Build Google OAuth2 authorization URL."""
        if _cfg.is_development and not _cfg.google_client_id:
            # Return a mock URL for local dev
            return (
                f"http://localhost:8004/mock/oauth/google_calendar"
                f"?redirect_uri={urllib.parse.quote(redirect_uri)}&state={state}"
            )

        scope_str = " ".join(scopes or _DEFAULT_SCOPES)
        params = {
            "client_id": _cfg.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope_str,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"

    async def authorize(
        self,
        code: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        """Exchange authorization code for tokens via Google token endpoint."""
        if _cfg.is_development and not _cfg.google_client_secret:
            logger.info("google_calendar: returning mock tokens (dev mode)")
            return _mock_tokens("google_calendar")

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "code": code,
                    "client_id": _cfg.google_client_id,
                    "client_secret": _cfg.google_client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def refresh_tokens(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an expired Google access token."""
        if _cfg.is_development and not _cfg.google_client_secret:
            return _mock_tokens("google_calendar")

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "refresh_token": refresh_token,
                    "client_id": _cfg.google_client_id,
                    "client_secret": _cfg.google_client_secret,
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            # Google doesn't return refresh_token on refresh; preserve the old one
            data.setdefault("refresh_token", refresh_token)
            return data

    async def disconnect(self, user_id: str, tokens: dict[str, Any]) -> None:
        """Revoke the OAuth token with Google."""
        token = tokens.get("access_token") or tokens.get("refresh_token")
        if not token or _cfg.is_development:
            logger.info("google_calendar: skipping revoke in dev mode")
            return

        async with httpx.AsyncClient(timeout=10) as client:
            try:
                await client.post(_REVOKE_URL, params={"token": token})
            except httpx.HTTPError as exc:
                logger.warning("Failed to revoke Google token: %s", exc)

    # ─── Sync ─────────────────────────────────────────────────────────────────────────────

    async def sync(
        self,
        user_id: str,
        tokens: dict[str, Any],
        last_sync: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Fetch Google Calendar events.

        Uses ``syncToken`` for incremental updates when available;
        falls back to a ``timeMin`` filter for the initial sync.
        """
        if _cfg.is_development and tokens.get("access_token", "").startswith("mock_"):
            logger.info("google_calendar: returning mock events (dev mode)")
            return _mock_events()

        access_token = tokens["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        sync_token: Optional[str] = tokens.get("sync_token")

        params: dict[str, Any] = {
            "maxResults": 250,
            "singleEvents": True,
            "orderBy": "startTime",
        }

        if sync_token:
            params["syncToken"] = sync_token
        else:
            # First sync: fetch 30 days of history + 90 days future
            time_min = (datetime.now(tz=timezone.utc) - timedelta(days=30)).isoformat()
            time_max = (datetime.now(tz=timezone.utc) + timedelta(days=90)).isoformat()
            params["timeMin"] = time_min
            params["timeMax"] = time_max

        events: list[dict[str, Any]] = []
        next_page_token: Optional[str] = None
        new_sync_token: Optional[str] = None

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                if next_page_token:
                    params["pageToken"] = next_page_token

                resp = await client.get(_EVENTS_URL, headers=headers, params=params)

                # 410 Gone means sync token is invalidated; do a full re-sync
                if resp.status_code == 410:
                    logger.warning(
                        "google_calendar: syncToken expired for user %s; full re-sync",
                        user_id,
                    )
                    params.pop("syncToken", None)
                    time_min = (datetime.now(tz=timezone.utc) - timedelta(days=30)).isoformat()
                    params["timeMin"] = time_min
                    resp = await client.get(_EVENTS_URL, headers=headers, params=params)

                resp.raise_for_status()
                page = resp.json()

                events.extend(page.get("items", []))
                new_sync_token = page.get("nextSyncToken")
                next_page_token = page.get("nextPageToken")

                if not next_page_token:
                    break

        return {"events": events, "sync_token": new_sync_token}

    # ─── Graph transformation ──────────────────────────────────────────────────────────────────────

    async def push_update(
        self,
        user_id: str,
        raw_data: dict[str, Any],
    ) -> tuple[list[GraphNode], list[GraphRelationship]]:
        """Transform calendar events into EVENT graph nodes."""
        import uuid

        events = raw_data.get("events", [])
        nodes: list[GraphNode] = []
        relationships: list[GraphRelationship] = []

        for event in events:
            # Skip cancelled events
            if event.get("status") == "cancelled":
                continue

            event_id = event.get("id", str(uuid.uuid4()))
            node_id = f"event:{user_id}:{event_id}"

            start = event.get("start", {})
            end = event.get("end", {})
            start_time = start.get("dateTime") or start.get("date")
            end_time = end.get("dateTime") or end.get("date")

            attendees = [
                a.get("email", "") for a in event.get("attendees", [])
                if not a.get("self", False)
            ]

            node = GraphNode(
                id=node_id,
                type=NodeType.EVENT,
                schema_scope=f"user:{user_id}",
                properties={
                    "title": event.get("summary", "Untitled Event"),
                    "description": event.get("description", ""),
                    "start_time": start_time,
                    "end_time": end_time,
                    "location": event.get("location", ""),
                    "attendees": attendees,
                    "attendee_count": len(event.get("attendees", [])),
                    "recurrence": event.get("recurrence", []),
                    "calendar_id": "primary",
                    "html_link": event.get("htmlLink", ""),
                    "event_id": event_id,
                    "source": "google_calendar",
                    "status": event.get("status", "confirmed"),
                    "organizer_email": event.get("organizer", {}).get("email", ""),
                    "is_recurring": bool(event.get("recurringEventId")),
                    "conferencing": bool(event.get("conferenceData")),
                },
            )
            nodes.append(node)

            # Create ATTENDED relationships for each attendee (Person → Event)
            for attendee_email in attendees:
                if not attendee_email:
                    continue
                person_node_id = f"person:{user_id}:{attendee_email}"
                rel = GraphRelationship(
                    id=f"attended:{person_node_id}:{node_id}",
                    type=RelationshipType.ATTENDED,
                    source_id=person_node_id,
                    target_id=node_id,
                    properties={"source": "google_calendar"},
                )
                relationships.append(rel)

        logger.info(
            "google_calendar: transformed %d events → %d nodes, %d rels for user %s",
            len(events),
            len(nodes),
            len(relationships),
            user_id,
        )
        return nodes, relationships

    # ─── Webhook ────────────────────────────────────────────────────────────────────────────

    async def handle_webhook(
        self,
        user_id: str,
        payload: dict[str, Any],
        tokens: dict[str, Any],
    ) -> tuple[list[GraphNode], list[GraphRelationship]]:
        """
        Handle Google Calendar push notifications.

        Google sends a minimal notification (no event data); we trigger
        a full incremental sync to pick up changes.
        """
        logger.info("google_calendar: webhook received for user %s; triggering sync", user_id)
        raw_data = await self.sync(user_id, tokens)
        return await self.push_update(user_id, raw_data)


# ─── Dev helpers ─────────────────────────────────────────────────────────────────────────────

def _mock_tokens(provider: str) -> dict[str, Any]:
    return {
        "access_token": f"mock_access_{provider}_dev",
        "refresh_token": f"mock_refresh_{provider}_dev",
        "expires_in": 3600,
        "token_type": "Bearer",
        "scope": " ".join(_DEFAULT_SCOPES),
    }


def _mock_events() -> dict[str, Any]:
    now = datetime.now(tz=timezone.utc)
    return {
        "events": [
            {
                "id": "evt_mock_001",
                "summary": "Team Standup",
                "status": "confirmed",
                "start": {"dateTime": now.isoformat()},
                "end": {"dateTime": (now + timedelta(minutes=30)).isoformat()},
                "attendees": [
                    {"email": "alice@example.com"},
                    {"email": "bob@example.com"},
                ],
                "htmlLink": "https://calendar.google.com/mock/evt001",
                "organizer": {"email": "alice@example.com"},
                "conferenceData": {"conferenceId": "meet-123"},
            },
            {
                "id": "evt_mock_002",
                "summary": "1:1 with Manager",
                "status": "confirmed",
                "start": {"dateTime": (now + timedelta(days=1)).isoformat()},
                "end": {"dateTime": (now + timedelta(days=1, minutes=60)).isoformat()},
                "attendees": [{"email": "manager@example.com"}],
                "htmlLink": "https://calendar.google.com/mock/evt002",
                "organizer": {"email": "manager@example.com"},
                "location": "Conference Room A",
            },
            {
                "id": "evt_mock_003",
                "summary": "Deep Work Block",
                "status": "confirmed",
                "start": {"dateTime": (now + timedelta(days=2, hours=9)).isoformat()},
                "end": {"dateTime": (now + timedelta(days=2, hours=12)).isoformat()},
                "attendees": [],
                "htmlLink": "https://calendar.google.com/mock/evt003",
                "organizer": {"email": "self@example.com"},
            },
        ],
        "sync_token": "mock_sync_token_abc123",
    }
