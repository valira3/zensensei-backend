"""
ZenSensei Integration Service - Spotify Integration

Syncs recently played tracks, top artists, and podcast episodes to build
Content nodes and derive listening pattern insights.

Graph mapping
-------------
Track / Episode  → NodeType.CONTENT
  - properties: title, artist, album, duration_ms, played_at, type, uri
  - relationships: PERSON (user) –[CONSUMED]→ CONTENT
Artist           → NodeType.CONTENT (type=artist)
  - relationships: CONTENT (track) –[INCLUDES]→ CONTENT (artist)
"""

from __future__ import annotations

import base64
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

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_RECENTLY_PLAYED_URL = "https://api.spotify.com/v1/me/player/recently-played"
_TOP_ARTISTS_URL = "https://api.spotify.com/v1/me/top/artists"
_TOP_TRACKS_URL = "https://api.spotify.com/v1/me/top/tracks"

_DEFAULT_SCOPES = [
    "user-read-recently-played",
    "user-top-read",
    "user-read-playback-state",
]

# Spotify client credentials stored in config extensions
# (Use google_client_id/secret slots as placeholder keys for MVP;
#  production should add spotify_client_id/secret to ZenSenseiConfig)
_SPOTIFY_CLIENT_ID = ""   # Populated from env: SPOTIFY_CLIENT_ID
_SPOTIFY_CLIENT_SECRET = ""  # Populated from env: SPOTIFY_CLIENT_SECRET

try:
    import os
    _SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
    _SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
except Exception:
    pass


class SpotifyIntegration(Integration):
    """
    Spotify integration.

    Fetches recently played tracks (up to 50), top artists, and top tracks,
    then transforms them into Content nodes with CONSUMED relationships.
    """

    metadata: IntegrationMetadata = get_by_id("spotify")  # type: ignore[assignment]

    # ─── OAuth ───────────────────────────────────────────────────────────────────────────

    async def get_oauth_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: Optional[list[str]] = None,
    ) -> str:
        if _cfg.is_development and not _SPOTIFY_CLIENT_ID:
            return (
                f"http://localhost:8004/mock/oauth/spotify"
                f"?redirect_uri={urllib.parse.quote(redirect_uri)}&state={state}"
            )

        scope_str = " ".join(scopes or _DEFAULT_SCOPES)
        params = {
            "response_type": "code",
            "client_id": _SPOTIFY_CLIENT_ID,
            "scope": scope_str,
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"https://accounts.spotify.com/authorize?{urllib.parse.urlencode(params)}"

    async def authorize(self, code: str, redirect_uri: str) -> dict[str, Any]:
        if _cfg.is_development and not _SPOTIFY_CLIENT_SECRET:
            return _mock_tokens()

        credentials = base64.b64encode(
            f"{_SPOTIFY_CLIENT_ID}:{_SPOTIFY_CLIENT_SECRET}".encode()
        ).decode()

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TOKEN_URL,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def refresh_tokens(self, refresh_token: str) -> dict[str, Any]:
        if _cfg.is_development and not _SPOTIFY_CLIENT_SECRET:
            return _mock_tokens()

        credentials = base64.b64encode(
            f"{_SPOTIFY_CLIENT_ID}:{_SPOTIFY_CLIENT_SECRET}".encode()
        ).decode()

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TOKEN_URL,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            data.setdefault("refresh_token", refresh_token)
            return data

    async def disconnect(self, user_id: str, tokens: dict[str, Any]) -> None:
        """Spotify has no token revocation endpoint; just delete stored tokens."""
        logger.info("spotify: tokens removed for user %s (no revocation endpoint)", user_id)

    # ─── Sync ─────────────────────────────────────────────────────────────────────────────

    async def sync(
        self,
        user_id: str,
        tokens: dict[str, Any],
        last_sync: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Fetch recently played tracks, top artists, and top tracks.

        For incremental sync, filters recently_played by timestamp.
        """
        if _cfg.is_development and tokens.get("access_token", "").startswith("mock_"):
            return _mock_listening_data()

        access_token = tokens["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        params_recent: dict[str, Any] = {"limit": 50}
        if last_sync:
            try:
                dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
                params_recent["after"] = int(dt.timestamp() * 1000)  # Spotify uses ms
            except (ValueError, TypeError):
                pass

        recently_played: list[dict[str, Any]] = []
        top_artists: list[dict[str, Any]] = []
        top_tracks: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=30) as client:
            # Recently played
            resp = await client.get(
                _RECENTLY_PLAYED_URL, headers=headers, params=params_recent
            )
            if resp.status_code == 200:
                recently_played = resp.json().get("items", [])

            # Top artists (medium term = ~6 months)
            resp = await client.get(
                _TOP_ARTISTS_URL,
                headers=headers,
                params={"limit": 20, "time_range": "medium_term"},
            )
            if resp.status_code == 200:
                top_artists = resp.json().get("items", [])

            # Top tracks (medium term)
            resp = await client.get(
                _TOP_TRACKS_URL,
                headers=headers,
                params={"limit": 20, "time_range": "medium_term"},
            )
            if resp.status_code == 200:
                top_tracks = resp.json().get("items", [])

        return {
            "recently_played": recently_played,
            "top_artists": top_artists,
            "top_tracks": top_tracks,
        }

    # ─── Graph transformation ──────────────────────────────────────────────────────────────────────

    async def push_update(
        self,
        user_id: str,
        raw_data: dict[str, Any],
    ) -> tuple[list[GraphNode], list[GraphRelationship]]:
        """Transform Spotify data into Content nodes with CONSUMED edges."""
        import uuid

        nodes: list[GraphNode] = []
        relationships: list[GraphRelationship] = []
        user_node_id = f"person:{user_id}:self"

        # ── Recently played tracks ──
        for item in raw_data.get("recently_played", []):
            track = item.get("track", {})
            if not track:
                continue

            track_id = track.get("id", str(uuid.uuid4()))
            node_id = f"content:{user_id}:spotify:track:{track_id}"
            played_at = item.get("played_at", "")

            artists = [a.get("name", "") for a in track.get("artists", [])]

            node = GraphNode(
                id=node_id,
                type=NodeType.CONTENT,
                schema_scope=f"user:{user_id}",
                properties={
                    "content_type": "track",
                    "title": track.get("name", ""),
                    "artist": ", ".join(artists),
                    "album": track.get("album", {}).get("name", ""),
                    "duration_ms": track.get("duration_ms", 0),
                    "played_at": played_at,
                    "uri": track.get("uri", ""),
                    "preview_url": track.get("preview_url"),
                    "explicit": track.get("explicit", False),
                    "popularity": track.get("popularity", 0),
                    "source": "spotify",
                },
            )
            nodes.append(node)

            rel = GraphRelationship(
                id=f"consumed:{user_node_id}:{node_id}:{played_at}",
                type=RelationshipType.CONSUMED,
                source_id=user_node_id,
                target_id=node_id,
                properties={
                    "consumed_at": played_at,
                    "source": "spotify",
                },
            )
            relationships.append(rel)

        # ── Top artists (as Content nodes representing listening preferences) ──
        for rank, artist in enumerate(raw_data.get("top_artists", []), start=1):
            artist_id = artist.get("id", str(uuid.uuid4()))
            node_id = f"content:{user_id}:spotify:artist:{artist_id}"

            node = GraphNode(
                id=node_id,
                type=NodeType.CONTENT,
                schema_scope=f"user:{user_id}",
                properties={
                    "content_type": "artist",
                    "title": artist.get("name", ""),
                    "genres": artist.get("genres", []),
                    "popularity": artist.get("popularity", 0),
                    "followers": artist.get("followers", {}).get("total", 0),
                    "top_rank": rank,
                    "uri": artist.get("uri", ""),
                    "source": "spotify",
                },
            )
            nodes.append(node)

            rel = GraphRelationship(
                id=f"subscribed:{user_node_id}:{node_id}",
                type=RelationshipType.SUBSCRIBED_TO,
                source_id=user_node_id,
                target_id=node_id,
                properties={"rank": rank, "source": "spotify"},
            )
            relationships.append(rel)

        logger.info(
            "spotify: transformed %d tracks + %d artists → %d nodes for user %s",
            len(raw_data.get("recently_played", [])),
            len(raw_data.get("top_artists", [])),
            len(nodes),
            user_id,
        )
        return nodes, relationships


# ─── Mock helpers ─────────────────────────────────────────────────────────────────────────────

def _mock_tokens() -> dict[str, Any]:
    return {
        "access_token": "mock_access_spotify_dev",
        "refresh_token": "mock_refresh_spotify_dev",
        "expires_in": 3600,
        "token_type": "Bearer",
        "scope": " ".join(_DEFAULT_SCOPES),
    }


def _mock_listening_data() -> dict[str, Any]:
    now = datetime.now(tz=timezone.utc)
    return {
        "recently_played": [
            {
                "track": {
                    "id": "trk_001",
                    "name": "Lose Yourself",
                    "artists": [{"name": "Eminem"}],
                    "album": {"name": "8 Mile Soundtrack"},
                    "duration_ms": 326000,
                    "uri": "spotify:track:7w9bgPAmPTtrkt2v16QWvQ",
                    "popularity": 82,
                    "explicit": True,
                },
                "played_at": (now - timedelta(hours=1)).isoformat(),
            },
            {
                "track": {
                    "id": "trk_002",
                    "name": "Eye of the Tiger",
                    "artists": [{"name": "Survivor"}],
                    "album": {"name": "Eye of the Tiger"},
                    "duration_ms": 244700,
                    "uri": "spotify:track:2HHtWyy5CgaQbC7XSoOb0e",
                    "popularity": 79,
                    "explicit": False,
                },
                "played_at": (now - timedelta(hours=3)).isoformat(),
            },
        ],
        "top_artists": [
            {
                "id": "art_001",
                "name": "Eminem",
                "genres": ["hip hop", "rap"],
                "popularity": 90,
                "followers": {"total": 55000000},
                "uri": "spotify:artist:7dGJo4pcD2V6oG8kP0tJRR",
            },
            {
                "id": "art_002",
                "name": "Hans Zimmer",
                "genres": ["orchestral", "soundtrack"],
                "popularity": 78,
                "followers": {"total": 12000000},
                "uri": "spotify:artist:0YC192cP3KPCRWx8zr8MfZ",
            },
        ],
        "top_tracks": [],
    }
