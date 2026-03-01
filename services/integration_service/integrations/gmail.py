"""
ZenSensei Integration Service - Gmail Integration

Syncs recent Gmail messages to extract contacts and build PERSON nodes
with communication relationship signals in the knowledge graph.

Graph mapping
-------------
Email sender/recipient → NodeType.PERSON
  - properties: email, name, message_count, last_contact
  - relationships: PERSON –[KNOWS]→ PERSON (user ↔ contact)
"""

from __future__ import annotations

import base64
import email as email_lib
import logging
import re
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

# ─── API endpoints ───────────────────────────────────────────────────────────────────────────

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
_MESSAGES_LIST_URL = "https://www.googleapis.com/gmail/v1/users/me/messages"
_MESSAGE_URL = "https://www.googleapis.com/gmail/v1/users/me/messages/{id}"
_PROFILE_URL = "https://www.googleapis.com/gmail/v1/users/me/profile"
_DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]
_MAX_MESSAGES = 100  # messages to fetch per sync pass


class GmailIntegration(Integration):
    """
    Gmail integration.

    Fetches recent messages, extracts unique sender/recipient email addresses,
    and creates PERSON graph nodes with communication frequency metadata.
    """

    metadata: IntegrationMetadata = get_by_id("gmail")  # type: ignore[assignment]

    # ─── OAuth ───────────────────────────────────────────────────────────────────────────

    async def get_oauth_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: Optional[list[str]] = None,
    ) -> str:
        if _cfg.is_development and not _cfg.google_client_id:
            return (
                f"http://localhost:8004/mock/oauth/gmail"
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

    async def authorize(self, code: str, redirect_uri: str) -> dict[str, Any]:
        if _cfg.is_development and not _cfg.google_client_secret:
            logger.info("gmail: returning mock tokens (dev mode)")
            return _mock_tokens()

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
        if _cfg.is_development and not _cfg.google_client_secret:
            return _mock_tokens()

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
            data.setdefault("refresh_token", refresh_token)
            return data

    async def disconnect(self, user_id: str, tokens: dict[str, Any]) -> None:
        token = tokens.get("access_token") or tokens.get("refresh_token")
        if not token or _cfg.is_development:
            return

        async with httpx.AsyncClient(timeout=10) as client:
            try:
                await client.post(_REVOKE_URL, params={"token": token})
            except httpx.HTTPError as exc:
                logger.warning("Failed to revoke Gmail token: %s", exc)

    # ─── Sync ─────────────────────────────────────────────────────────────────────────────

    async def sync(
        self,
        user_id: str,
        tokens: dict[str, Any],
        last_sync: Optional[str] = None,
    ) -> dict[str, Any]:
        """Fetch recent Gmail messages and extract contact metadata."""
        if _cfg.is_development and tokens.get("access_token", "").startswith("mock_"):
            logger.info("gmail: returning mock data (dev mode)")
            return _mock_messages()

        access_token = tokens["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # Build query: messages from last 30 days (or since last_sync)
        if last_sync:
            try:
                dt = datetime.fromisoformat(last_sync)
                after_epoch = int(dt.timestamp())
                query = f"after:{after_epoch}"
            except (ValueError, TypeError):
                query = "newer_than:30d"
        else:
            query = "newer_than:30d"

        # Step 1: List message IDs
        msg_ids: list[str] = []
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                _MESSAGES_LIST_URL,
                headers=headers,
                params={
                    "q": query,
                    "maxResults": _MAX_MESSAGES,
                    "includeSpamTrash": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            msg_ids = [m["id"] for m in data.get("messages", [])]

            # Step 2: Fetch message headers in parallel (batch-style)
            messages: list[dict[str, Any]] = []
            for msg_id in msg_ids[:_MAX_MESSAGES]:
                try:
                    msg_resp = await client.get(
                        _MESSAGE_URL.format(id=msg_id),
                        headers=headers,
                        params={"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date"]},
                    )
                    if msg_resp.status_code == 200:
                        messages.append(msg_resp.json())
                except httpx.HTTPError:
                    pass

        return {"messages": messages, "total_fetched": len(messages)}

    # ─── Graph transformation ──────────────────────────────────────────────────────────────────────

    async def push_update(
        self,
        user_id: str,
        raw_data: dict[str, Any],
    ) -> tuple[list[GraphNode], list[GraphRelationship]]:
        """
        Build PERSON nodes from email contacts extracted from message headers.
        Aggregates contact frequency to populate message_count and last_contact.
        """
        import uuid

        messages = raw_data.get("messages", [])
        contact_stats: dict[str, dict[str, Any]] = {}

        for msg in messages:
            headers = {
                h["name"].lower(): h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            # Extract all email addresses from From/To fields
            for field in ("from", "to"):
                value = headers.get(field, "")
                for name, addr in _parse_addresses(value):
                    addr = addr.lower().strip()
                    if not addr or addr == "" or _is_noreply(addr):
                        continue
                    if addr not in contact_stats:
                        contact_stats[addr] = {
                            "email": addr,
                            "name": name or addr.split("@")[0],
                            "message_count": 0,
                            "last_contact": None,
                        }
                    contact_stats[addr]["message_count"] += 1
                    msg_date = headers.get("date", "")
                    if msg_date and (
                        not contact_stats[addr]["last_contact"]
                        or msg_date > contact_stats[addr]["last_contact"]
                    ):
                        contact_stats[addr]["last_contact"] = msg_date

        nodes: list[GraphNode] = []
        relationships: list[GraphRelationship] = []
        user_node_id = f"person:{user_id}:self"

        for addr, stats in contact_stats.items():
            node_id = f"person:{user_id}:{addr}"
            node = GraphNode(
                id=node_id,
                type=NodeType.PERSON,
                schema_scope=f"user:{user_id}",
                properties={
                    "email": addr,
                    "name": stats["name"],
                    "message_count": stats["message_count"],
                    "last_contact": stats["last_contact"],
                    "source": "gmail",
                },
            )
            nodes.append(node)

            # KNOWS relationship: user ↔ contact
            rel_id = f"knows:{user_node_id}:{node_id}"
            rel = GraphRelationship(
                id=rel_id,
                type=RelationshipType.KNOWS,
                source_id=user_node_id,
                target_id=node_id,
                properties={
                    "source": "gmail",
                    "message_count": stats["message_count"],
                    "last_contact": stats["last_contact"],
                },
            )
            relationships.append(rel)

        logger.info(
            "gmail: extracted %d contacts → %d nodes from %d messages for user %s",
            len(contact_stats),
            len(nodes),
            len(messages),
            user_id,
        )
        return nodes, relationships


# ─── Helpers ─────────────────────────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"[\w.+%-]+@[\w.-]+\.\w+")
_NAME_EMAIL_RE = re.compile(r'"?([^"<]*)"?\s*<([^>]+)>')


def _parse_addresses(header_value: str) -> list[tuple[str, str]]:
    """Parse RFC 5322 address header into (display_name, email) pairs."""
    results: list[tuple[str, str]] = []
    for addr_str in header_value.split(","):
        addr_str = addr_str.strip()
        match = _NAME_EMAIL_RE.search(addr_str)
        if match:
            results.append((match.group(1).strip(), match.group(2).strip()))
        else:
            email_match = _EMAIL_RE.search(addr_str)
            if email_match:
                results.append(("", email_match.group(0)))
    return results


_NOREPLY_PATTERNS = re.compile(
    r"(no.?reply|noreply|do.not.reply|mailer-daemon|postmaster|bounce|notifications?@)",
    re.IGNORECASE,
)


def _is_noreply(email: str) -> bool:
    return bool(_NOREPLY_PATTERNS.search(email))


def _mock_tokens() -> dict[str, Any]:
    return {
        "access_token": "mock_access_gmail_dev",
        "refresh_token": "mock_refresh_gmail_dev",
        "expires_in": 3600,
        "token_type": "Bearer",
        "scope": " ".join(_DEFAULT_SCOPES),
    }


def _mock_messages() -> dict[str, Any]:
    return {
        "messages": [
            {
                "id": "msg_001",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Alice Smith <alice@example.com>"},
                        {"name": "To", "value": "me@example.com"},
                        {"name": "Subject", "value": "Re: Project Update"},
                        {"name": "Date", "value": "Mon, 01 Mar 2026 09:00:00 +0000"},
                    ]
                },
            },
            {
                "id": "msg_002",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Bob Jones <bob@company.com>"},
                        {"name": "To", "value": "me@example.com, alice@example.com"},
                        {"name": "Subject", "value": "Meeting tomorrow"},
                        {"name": "Date", "value": "Tue, 25 Feb 2026 14:30:00 +0000"},
                    ]
                },
            },
            {
                "id": "msg_003",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "mentor@coaching.com"},
                        {"name": "To", "value": "me@example.com"},
                        {"name": "Subject", "value": "Your progress this month"},
                        {"name": "Date", "value": "Fri, 28 Feb 2026 11:15:00 +0000"},
                    ]
                },
            },
        ],
        "total_fetched": 3,
    }
