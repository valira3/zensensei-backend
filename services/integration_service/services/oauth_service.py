"""
ZenSensei Integration Service - OAuth Service

Manages OAuth 2.0 flows, token exchange, storage, and refresh for all
67 registered integrations. Uses Firestore as the token store.

Key responsibilities
--------------------
- Generate provider-specific authorization URLs with CSRF state tokens
- Exchange authorization codes for access + refresh tokens
- Persist tokens in Firestore under ``users/{uid}/integrations/{id}``
- Refresh expired tokens automatically
- Revoke tokens on disconnect
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import httpx

from shared.config import get_config
from shared.database.firestore import get_firestore_client
from shared.models.integrations import IntegrationStatus

from integration_service.integrations import registry

logger = logging.getLogger(__name__)
_cfg = get_config()

# Firestore collection paths
_USERS_COL = "users"
_INTEGRATIONS_SUB = "integrations"
_OAUTH_STATES_COL = "oauth_states"


class OAuthService:
    """
    Manages OAuth flows and token storage for all integrations.

    Instance is a singleton (see ``get_oauth_service``). All methods are
    async-safe and use Firestore as the backing store.
    """

    def __init__(self) -> None:
        self._fs = get_firestore_client()
        self._http: httpx.AsyncClient | None = None

    # ─── Lifecycle ───────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Initialise the shared HTTP client and validate Firestore access."""
        self._http = httpx.AsyncClient(timeout=30.0)
        await self._fs.health_check()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http:
            await self._http.aclose()
            self._http = None

    # ─── OAuth URL generation ────────────────────────────────────────────────────

    async def get_oauth_url(
        self,
        integration_id: str,
        user_id: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
    ) -> tuple[str, str]:
        """
        Build the authorization URL for the given integration.

        Returns
        -------
        (authorization_url, state_token)
        """
        meta = registry.get_by_id(integration_id)
        if not meta:
            raise ValueError(f"Unknown integration: {integration_id}")
        if not meta.oauth_url_template:
            raise ValueError(f"Integration '{integration_id}' does not support OAuth")

        # Generate a CSRF state token and persist it briefly in Firestore
        state = secrets.token_urlsafe(32)
        await self._store_state(state, user_id, integration_id)

        # Build the authorization URL
        effective_scopes = scopes or meta.required_scopes
        scope_str = " ".join(effective_scopes)

        client_id = self._get_client_id(integration_id)
        auth_url = (
            meta.oauth_url_template
            .replace("{client_id}", client_id)
            .replace("{redirect_uri}", redirect_uri)
            .replace("{scope}", scope_str)
            .replace("{state}", state)
        )
        return auth_url, state

    # ─── Token exchange ────────────────────────────────────────────────────────

    async def exchange_code(
        self,
        integration_id: str,
        code: str,
        state: str,
        redirect_uri: str,
        user_id: str,
    ) -> dict[str, Any]:
        """
        Exchange the authorization code for tokens.

        Validates the state token, exchanges the code with the provider,
        and persists the tokens in Firestore.
        """
        # Validate CSRF state
        stored = await self._get_state(state)
        if not stored:
            raise ValueError("Invalid or expired OAuth state token")
        if stored.get("user_id") != user_id:
            raise ValueError("State token user mismatch")
        if stored.get("integration_id") != integration_id:
            raise ValueError("State token integration mismatch")

        # Clean up state token
        await self._delete_state(state)

        meta = registry.get_by_id(integration_id)
        if not meta or not meta.token_url:
            raise ValueError(f"No token URL configured for '{integration_id}'")

        client_id = self._get_client_id(integration_id)
        client_secret = self._get_client_secret(integration_id)

        http = self._http or httpx.AsyncClient(timeout=30.0)
        resp = await http.post(
            meta.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        tokens: dict[str, Any] = resp.json()

        # Persist tokens in Firestore
        await self._save_tokens(user_id, integration_id, tokens)

        return tokens

    # ─── Token refresh ─────────────────────────────────────────────────────────

    async def refresh_token(
        self,
        user_id: str,
        integration_id: str,
    ) -> dict[str, Any]:
        """
        Refresh the access token for the given user + integration.

        Updates Firestore with the new token data.
        """
        token_doc = await self._load_tokens(user_id, integration_id)
        if not token_doc:
            raise ValueError(f"No tokens found for '{integration_id}'")

        refresh_token = token_doc.get("refresh_token")
        if not refresh_token:
            raise ValueError(f"No refresh token for '{integration_id}'")

        meta = registry.get_by_id(integration_id)
        if not meta or not meta.token_url:
            raise ValueError(f"No token URL configured for '{integration_id}'")

        client_id = self._get_client_id(integration_id)
        client_secret = self._get_client_secret(integration_id)

        http = self._http or httpx.AsyncClient(timeout=30.0)
        resp = await http.post(
            meta.token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        new_tokens: dict[str, Any] = resp.json()

        # Merge: keep old refresh token if not returned
        if "refresh_token" not in new_tokens:
            new_tokens["refresh_token"] = refresh_token

        await self._save_tokens(user_id, integration_id, new_tokens)
        return new_tokens

    # ─── Status & listing ────────────────────────────────────────────────────────

    async def get_status(
        self, user_id: str, integration_id: str
    ) -> dict[str, Any] | None:
        """Return the Firestore status document for a user's integration."""
        return await self._load_tokens(user_id, integration_id)

    async def list_connected(
        self, user_id: str
    ) -> list[dict[str, Any]]:
        """List all integrations the user has connected."""
        try:
            docs = await self._fs.list_collection(
                f"{_USERS_COL}/{user_id}/{_INTEGRATIONS_SUB}"
            )
            return [d for d in docs if d.get("status") == IntegrationStatus.CONNECTED]
        except Exception as exc:
            logger.warning("list_connected failed: %s", exc)
            return []

    # ─── Revocation ─────────────────────────────────────────────────────────────

    async def revoke_tokens(
        self, user_id: str, integration_id: str
    ) -> None:
        """Revoke tokens at the provider and delete from Firestore."""
        token_doc = await self._load_tokens(user_id, integration_id)
        if token_doc:
            meta = registry.get_by_id(integration_id)
            revoke_url = meta.revoke_url if meta else None
            if revoke_url:
                http = self._http or httpx.AsyncClient(timeout=10.0)
                with contextlib.suppress(Exception):
                    await http.post(revoke_url, data={"token": token_doc.get("access_token", "")})

        await self._delete_tokens(user_id, integration_id)

    # ─── Firestore helpers ───────────────────────────────────────────────────────

    async def _save_tokens(
        self,
        user_id: str,
        integration_id: str,
        tokens: dict[str, Any],
    ) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        doc = {
            **tokens,
            "integration_id": integration_id,
            "status": IntegrationStatus.CONNECTED,
            "connected_at": now,
            "last_synced_at": None,
            "error_message": None,
            "sync_cursor": None,
        }
        path = f"{_USERS_COL}/{user_id}/{_INTEGRATIONS_SUB}/{integration_id}"
        await self._fs.set_document(path, doc)

    async def _load_tokens(
        self,
        user_id: str,
        integration_id: str,
    ) -> dict[str, Any] | None:
        path = f"{_USERS_COL}/{user_id}/{_INTEGRATIONS_SUB}/{integration_id}"
        return await self._fs.get_document(path)

    async def _delete_tokens(self, user_id: str, integration_id: str) -> None:
        path = f"{_USERS_COL}/{user_id}/{_INTEGRATIONS_SUB}/{integration_id}"
        await self._fs.delete_document(path)

    async def _store_state(
        self,
        state: str,
        user_id: str,
        integration_id: str,
    ) -> None:
        path = f"{_OAUTH_STATES_COL}/{state}"
        expires_at = (datetime.now(tz=timezone.utc) + timedelta(minutes=10)).isoformat()
        await self._fs.set_document(path, {
            "user_id": user_id,
            "integration_id": integration_id,
            "expires_at": expires_at,
        })

    async def _get_state(self, state: str) -> dict[str, Any] | None:
        path = f"{_OAUTH_STATES_COL}/{state}"
        doc = await self._fs.get_document(path)
        if not doc:
            return None
        # Check expiry
        expires_at_str = doc.get("expires_at")
        if expires_at_str:
            try:
                exp = datetime.fromisoformat(expires_at_str)
                if datetime.now(tz=timezone.utc) > exp:
                    await self._delete_state(state)
                    return None
            except ValueError:
                pass
        return doc

    async def _delete_state(self, state: str) -> None:
        path = f"{_OAUTH_STATES_COL}/{state}"
        await self._fs.delete_document(path)

    # ─── Config helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _get_client_id(integration_id: str) -> str:
        import os
        key = f"{integration_id.upper()}_CLIENT_ID"
        return os.environ.get(key, "")

    @staticmethod
    def _get_client_secret(integration_id: str) -> str:
        import os
        key = f"{integration_id.upper()}_CLIENT_SECRET"
        return os.environ.get(key, "")


# ─── Singleton accessor ───────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_oauth_service() -> OAuthService:
    """Return the global OAuthService singleton."""
    return OAuthService()
