"""
ZenSensei Integration Service - Notion Integration

Syncs Notion pages and database entries as Content and Task nodes,
capturing knowledge management and project tracking in the graph.

Graph mapping
-------------
Notion Page     → NodeType.CONTENT
  - properties: title, url, last_edited, parent_type, icon, cover
Database Row    → NodeType.TASK  (if contains status/assignee properties)
              or NodeType.CONTENT
  - relationships: PERSON (user) –[CONSUMED]→ CONTENT
                   PERSON (user) –[ASSIGNED_TO]→ TASK
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

_TOKEN_URL = "https://api.notion.com/v1/oauth/token"
_SEARCH_URL = "https://api.notion.com/v1/search"
_BLOCKS_URL = "https://api.notion.com/v1/blocks/{block_id}/children"
_NOTION_VERSION = "2022-06-28"

# Notion OAuth credentials (add to .env as NOTION_CLIENT_ID / NOTION_CLIENT_SECRET)
import os as _os
_NOTION_CLIENT_ID = _os.environ.get("NOTION_CLIENT_ID", "")
_NOTION_CLIENT_SECRET = _os.environ.get("NOTION_CLIENT_SECRET", "")


class NotionIntegration(Integration):
    """
    Notion integration.

    Uses Notion OAuth to access workspaces the user explicitly connects.
    Syncs all accessible pages and databases, classifying rows with
    status/checkbox properties as Task nodes.
    """

    metadata: IntegrationMetadata = get_by_id("notion")  # type: ignore[assignment]

    # ─── OAuth ───────────────────────────────────────────────────────────────────────────

    async def get_oauth_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: Optional[list[str]] = None,
    ) -> str:
        if _cfg.is_development and not _NOTION_CLIENT_ID:
            return (
                f"http://localhost:8004/mock/oauth/notion"
                f"?redirect_uri={urllib.parse.quote(redirect_uri)}&state={state}"
            )

        params = {
            "client_id": _NOTION_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "owner": "user",
        }
        return f"https://api.notion.com/v1/oauth/authorize?{urllib.parse.urlencode(params)}"

    async def authorize(self, code: str, redirect_uri: str) -> dict[str, Any]:
        if _cfg.is_development and not _NOTION_CLIENT_SECRET:
            return _mock_tokens()

        import base64
        credentials = base64.b64encode(
            f"{_NOTION_CLIENT_ID}:{_NOTION_CLIENT_SECRET}".encode()
        ).decode()

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TOKEN_URL,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/json",
                },
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def refresh_tokens(self, refresh_token: str) -> dict[str, Any]:
        """Notion tokens don't expire — no-op refresh."""
        return {"access_token": refresh_token}

    async def disconnect(self, user_id: str, tokens: dict[str, Any]) -> None:
        """Notion has no token revocation API; delete stored token."""
        logger.info("notion: tokens removed for user %s (no revocation endpoint)", user_id)

    # ─── Sync ─────────────────────────────────────────────────────────────────────────────

    async def sync(
        self,
        user_id: str,
        tokens: dict[str, Any],
        last_sync: Optional[str] = None,
    ) -> dict[str, Any]:
        """Fetch all pages and databases the user has granted access to."""
        if _cfg.is_development and tokens.get("access_token", "").startswith("mock_"):
            return _mock_notion_data()

        access_token = tokens["access_token"]
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }

        pages: list[dict[str, Any]] = []
        databases: list[dict[str, Any]] = []

        # Build filter for incremental sync
        filter_body: dict[str, Any] = {
            "page_size": 100,
            "sort": {"direction": "descending", "timestamp": "last_edited_time"},
        }
        if last_sync:
            # Notion search doesn't support date filtering natively;
            # we post-filter below
            pass

        async with httpx.AsyncClient(timeout=30) as client:
            has_more = True
            cursor: Optional[str] = None

            while has_more:
                body = dict(filter_body)
                if cursor:
                    body["start_cursor"] = cursor

                resp = await client.post(_SEARCH_URL, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()

                for result in data.get("results", []):
                    # Filter by last_edited_time for incremental sync
                    if last_sync and result.get("last_edited_time", "") < last_sync:
                        has_more = False
                        break

                    if result.get("object") == "page":
                        pages.append(result)
                    elif result.get("object") == "database":
                        databases.append(result)

                has_more = data.get("has_more", False) and has_more
                cursor = data.get("next_cursor")

        return {"pages": pages, "databases": databases}

    # ─── Graph transformation ──────────────────────────────────────────────────────────────────────

    async def push_update(
        self,
        user_id: str,
        raw_data: dict[str, Any],
    ) -> tuple[list[GraphNode], list[GraphRelationship]]:
        """Transform Notion pages/databases into Content and Task nodes."""
        import uuid

        nodes: list[GraphNode] = []
        relationships: list[GraphRelationship] = []
        user_node_id = f"person:{user_id}:self"

        # ── Pages ──
        for page in raw_data.get("pages", []):
            page_id = page.get("id", str(uuid.uuid4())).replace("-", "")
            node_id = f"content:{user_id}:notion:page:{page_id}"

            title = _extract_notion_title(page)
            last_edited = page.get("last_edited_time", "")
            created = page.get("created_time", "")
            url = page.get("url", "")
            icon = _extract_icon(page.get("icon"))
            cover = (page.get("cover") or {}).get("external", {}).get("url", "")

            node = GraphNode(
                id=node_id,
                type=NodeType.CONTENT,
                schema_scope=f"user:{user_id}",
                properties={
                    "content_type": "notion_page",
                    "title": title,
                    "url": url,
                    "notion_id": page_id,
                    "created_at": created,
                    "last_edited": last_edited,
                    "parent_type": page.get("parent", {}).get("type", ""),
                    "icon": icon,
                    "cover": cover,
                    "archived": page.get("archived", False),
                    "source": "notion",
                },
            )
            nodes.append(node)

            rel = GraphRelationship(
                id=f"consumed:{user_node_id}:{node_id}",
                type=RelationshipType.CONSUMED,
                source_id=user_node_id,
                target_id=node_id,
                properties={"source": "notion", "last_edited": last_edited},
            )
            relationships.append(rel)

        # ── Databases (treat as project containers) ──
        for db in raw_data.get("databases", []):
            db_id = db.get("id", str(uuid.uuid4())).replace("-", "")
            node_id = f"content:{user_id}:notion:database:{db_id}"

            title = _extract_notion_title(db)

            # Determine if DB looks like a task board (has Status or Checkbox props)
            props = db.get("properties", {})
            has_status = any(
                v.get("type") in ("status", "checkbox", "select")
                for v in props.values()
            )
            node_type = NodeType.TASK if has_status else NodeType.CONTENT

            node = GraphNode(
                id=node_id,
                type=node_type,
                schema_scope=f"user:{user_id}",
                properties={
                    "content_type": "notion_database",
                    "title": title,
                    "url": db.get("url", ""),
                    "notion_id": db_id,
                    "created_at": db.get("created_time", ""),
                    "last_edited": db.get("last_edited_time", ""),
                    "property_count": len(props),
                    "has_status_column": has_status,
                    "source": "notion",
                },
            )
            nodes.append(node)

            rel_type = RelationshipType.ASSIGNED_TO if has_status else RelationshipType.CONSUMED
            rel = GraphRelationship(
                id=f"{rel_type.lower()}:{user_node_id}:{node_id}",
                type=rel_type,
                source_id=user_node_id,
                target_id=node_id,
                properties={"source": "notion"},
            )
            relationships.append(rel)

        logger.info(
            "notion: transformed %d pages + %d databases → %d nodes for user %s",
            len(raw_data.get("pages", [])),
            len(raw_data.get("databases", [])),
            len(nodes),
            user_id,
        )
        return nodes, relationships


# ─── Helpers ─────────────────────────────────────────────────────────────────────────────

def _extract_notion_title(obj: dict[str, Any]) -> str:
    """Extract the human-readable title from a Notion page or database object."""
    # Pages store title in properties.title or properties.Name
    props = obj.get("properties", {})
    for key in ("title", "Title", "Name", "name"):
        prop = props.get(key, {})
        if prop.get("type") == "title":
            rich_texts = prop.get("title", [])
            if rich_texts:
                return "".join(rt.get("plain_text", "") for rt in rich_texts)

    # Databases store title at top level
    title_list = obj.get("title", [])
    if title_list and isinstance(title_list, list):
        return "".join(rt.get("plain_text", "") for rt in title_list)

    return "Untitled"


def _extract_icon(icon: Optional[dict[str, Any]]) -> str:
    if not icon:
        return ""
    icon_type = icon.get("type")
    if icon_type == "emoji":
        return icon.get("emoji", "")
    elif icon_type == "external":
        return icon.get("external", {}).get("url", "")
    return ""


def _mock_tokens() -> dict[str, Any]:
    return {
        "access_token": "mock_access_notion_dev",
        "token_type": "bearer",
        "bot_id": "mock-bot-001",
        "workspace_name": "My Workspace",
        "workspace_id": "mock-workspace-001",
    }


def _mock_notion_data() -> dict[str, Any]:
    now = datetime.now(tz=timezone.utc)
    return {
        "pages": [
            {
                "id": "page-001",
                "object": "page",
                "created_time": (now - timedelta(days=30)).isoformat(),
                "last_edited_time": now.isoformat(),
                "url": "https://www.notion.so/mock-page-001",
                "icon": {"type": "emoji", "emoji": "📚"},
                "cover": None,
                "archived": False,
                "parent": {"type": "workspace"},
                "properties": {
                    "title": {
                        "type": "title",
                        "title": [{"plain_text": "2026 Goals & Vision"}],
                    }
                },
            },
            {
                "id": "page-002",
                "object": "page",
                "created_time": (now - timedelta(days=15)).isoformat(),
                "last_edited_time": (now - timedelta(hours=6)).isoformat(),
                "url": "https://www.notion.so/mock-page-002",
                "icon": {"type": "emoji", "emoji": "💡"},
                "cover": None,
                "archived": False,
                "parent": {"type": "workspace"},
                "properties": {
                    "title": {
                        "type": "title",
                        "title": [{"plain_text": "Book Notes: Atomic Habits"}],
                    }
                },
            },
        ],
        "databases": [
            {
                "id": "db-001",
                "object": "database",
                "created_time": (now - timedelta(days=60)).isoformat(),
                "last_edited_time": (now - timedelta(days=1)).isoformat(),
                "url": "https://www.notion.so/mock-db-001",
                "title": [{"plain_text": "Project Tasks"}],
                "properties": {
                    "Name": {"type": "title"},
                    "Status": {"type": "status"},
                    "Due Date": {"type": "date"},
                    "Assignee": {"type": "person"},
                },
            },
        ],
    }
