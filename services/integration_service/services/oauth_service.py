"""
ZenSensei Integration Service - OAuth Service

Manages the full OAuth lifecycle:
  - Generating provider authorization URLs with CSRF state tokens
  - Exchanging authorization codes for access/refresh tokens
  - Refreshing expired access tokens automatically
  - Storing and retrieving encrypted tokens in Firestore
  - Revoking and deleting tokens on disconnect

Firestore collections
---------------------
``integration_tokens/{user_id}/providers/{integration_id}``
  Stores the encrypted token dict + metadata per user/provider combination.

``oauth_states/{state}``
  Short-lived CSRF state documents (TTL 10 min) linking state token
  to user_id + redirect_uri + integration_id.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken

from shared.config import ZenSenseiConfig, get_config
from shared.database.firestore import FirestoreClient, get_firestore_client
from shared.models.integrations import IntegrationStatus

logger = logging.getLogger(__name__)

# ─── Provider integration map ─────────────────────────────────────────────────
# Lazy import to avoid circular deps; populated on first use.
_PROVIDER_MAP: dict[str, Any] | None = None


def _get_provider_instance(integration_id: str) -> Any:
    """Lazy-load and cache provider integration instances."""
    global _PROVIDER_MAP
    if _PROVIDER_MAP is None:
        from integration_service.integrations.google_calendar import GoogleCalendarIntegration
        from integration_service.integrations.gmail import GmailIntegration
        from integration_service.integrations.plaid import PlaidIntegration
        from integration_service.integrations.spotify import SpotifyIntegration
        from integration_service.integrations.notion import NotionIntegration

        _PROVIDER_MAP = {
            "google_calendar": GoogleCalendarIntegration(),
            "gmail": GmailIntegration(),
            "plaid": PlaidIntegration(),
            "spotify": SpotifyIntegration(),
            "notion": NotionIntegration(),
        }
    return _PROVIDER_MAP.get(integration_id)


class OAuthService:
    """
    Centralized OAuth lifecycle manager for all integrations.

    Usage::

        svc = OAuthService()
        await svc.connect()

        url, state = await svc.get_oauth_url("google_calendar", user_id, redirect_uri)
        tokens = await svc.exchange_code("google_calendar", code, state, redirect_uri, user_id)
        stored = await svc.load_tokens(user_id, "google_calendar")
        fresh = await svc.ensure_fresh_tokens(user_id, "google_calendar")
        await svc.revoke_tokens(user_id, "google_calendar")
    """

    _TOKENS_COLLECTION = "integration_tokens"
    _STATES_COLLECTION = "oauth_states"
    _STATE_TTL_SECONDS = 600  # 10 minutes

    def __init__(
        self,
        config: ZenSenseiConfig | None = None,
        db: FirestoreClient | None = None,
    ) -> None:
        self._config = config or get_config()
        self._db = db or get_firestore_client()

    async def connect(self) -> None:
        """Initialise the Firestore client."""
        await self._db.connect()

    async def close(self) -> None:
        await self._db.close()

    # ─── URL generation ───────────────────────────────────────────────────────

    async def get_oauth_url(
        self,
        integration_id: str,
        user_id: str,
        redirect_uri: str,
        scopes: Optional[list[str]] = None,
    ) -> tuple[str, str]:
        """
        Generate an authorization URL for the given integration.

        Stores a short-lived CSRF state token in Firestore.

        Returns:
            ``(authorization_url, state)`` tuple.

        Raises:
            ValueError: if ``integration_id`` is not a known provider.
        """
        provider = _get_provider_instance(integration_id)
        if provider is None:
            raise ValueError(f"Unknown integration: {integration_id!r}")

        state = _generate_state()
        auth_url = await provider.get_oauth_url(redirect_uri, state, scopes)

        # Store state → (user_id, redirect_uri, integration_id) for callback validation
        state_doc = {
            "user_id": user_id,
            "integration_id": integration_id,
            "redirect_uri": redirect_uri,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "expires_at": (
                datetime.now(tz=timezone.utc) + timedelta(seconds=self._STATE_TTL_SECONDS)
            ).isoformat(),
        }
        await self._db.set(self._STATES_COLLECTION, state, state_doc)
        logger.debug("OAuth state stored: %s for integration %s", state, integration_id)
        return auth_url, state

    # ─── Code exchange ────────────────────────────────────────────────────────

    async def exchange_code(
        self,
        integration_id: str,
        code: str,
        state: str,
        redirect_uri: str,
        user_id: str,
    ) -> dict[str, Any]:
        """
        Validate state, exchange the authorization code, and persist tokens.

        Args:
            integration_id: Integration slug.
            code: Authorization code from the OAuth callback.
            state: CSRF state token from the callback query param.
            redirect_uri: Must match the URI used in :meth:`get_oauth_url`.
            user_id: ZenSensei user ID from the JWT.

        Returns:
            Token dict with at minimum ``access_token``.

        Raises:
            ValueError: on invalid/expired state or mismatched user.
        """
        await self._validate_state(state, user_id, integration_id)

        provider = _get_provider_instance(integration_id)
        if provider is None:
            raise ValueError(f"Unknown integration: {integration_id!r}")

        tokens = await provider.authorize(code, redirect_uri)
        await self.store_tokens(user_id, integration_id, tokens)

        # Clean up used state
        await self._db.delete(self._STATES_COLLECTION, state)
        return tokens

    # ─── Token refresh ────────────────────────────────────────────────────────

    async def refresh_tokens(
        self,
        provider_id: str,
        refresh_token: str,
    ) -> dict[str, Any]:
        """Refresh tokens using the provider's token endpoint."""
        provider = _get_provider_instance(provider_id)
        if provider is None:
            raise ValueError(f"Unknown integration: {provider_id!r}")
        return await provider.refresh_tokens(refresh_token)

    async def ensure_fresh_tokens(
        self,
        user_id: str,
        integration_id: str,
    ) -> dict[str, Any]:
        """
        Load stored tokens for ``user_id``/``integration_id``.

        If the access token is expired (or within 5 min of expiry), automatically
        refreshes using the stored refresh token and re-saves.

        Returns:
            Token dict ready to use.

        Raises:
            LookupError: if no tokens are stored for this user/integration.
            RuntimeError: if refresh fails and no valid token exists.
        """
        tokens = await self.load_tokens(user_id, integration_id)
        if not tokens:
            raise LookupError(
                f"No tokens found for user {user_id!r} / integration {integration_id!r}"
            )

        expires_at_str: Optional[str] = tokens.get("expires_at")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                # Refresh if within 5 minutes of expiry
                if datetime.now(tz=timezone.utc) >= expires_at - timedelta(minutes=5):
                    refresh_token = tokens.get("refresh_token")
                    if refresh_token:
                        logger.info(
                            "Refreshing tokens for user %s / %s",
                            user_id,
                            integration_id,
                        )
                        new_tokens = await self.refresh_tokens(integration_id, refresh_token)
                        # Merge: preserve refresh_token if provider doesn't return one
                        new_tokens.setdefault("refresh_token", refresh_token)
                        await self.store_tokens(user_id, integration_id, new_tokens)
                        return new_tokens
            except (ValueError, TypeError):
                pass

        return tokens

    # ─── Token storage ────────────────────────────────────────────────────────

    async def store_tokens(
        self,
        user_id: str,
        integration_id: str,
        tokens: dict[str, Any],
    ) -> None:
        """
        Persist tokens to Firestore, encrypted with the service secret key.

        Token encryption uses HMAC-SHA256 to derive a key from the
        ``secret_key`` config value, then stores base64-encoded ciphertext.
        In production this should use Google Cloud Secret Manager or KMS.
        """
        encrypted = _encrypt_tokens(tokens, self._config.secret_key)
        doc = {
            "integration_id": integration_id,
            "user_id": user_id,
            "encrypted_tokens": encrypted,
            "status": IntegrationStatus.CONNECTED,
            "connected_at": datetime.now(tz=timezone.utc).isoformat(),
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
            # Store non-sensitive metadata in plain text for quick access
            "scopes": tokens.get("scope", "").split() if isinstance(tokens.get("scope"), str) else tokens.get("scope", []),
            "expires_at": _compute_expiry(tokens),
            "sync_cursor": tokens.get("sync_token") or tokens.get("sync_cursor"),
        }
        doc_id = f"{user_id}__{integration_id}"
        await self._db.set(self._TOKENS_COLLECTION, doc_id, doc)
        logger.info("Stored tokens for user %s / %s", user_id, integration_id)

    async def load_tokens(
        self,
        user_id: str,
        integration_id: str,
    ) -> Optional[dict[str, Any]]:
        """
        Load and decrypt stored tokens.

        Returns:
            Decrypted token dict, or ``None`` if not found.
        """
        doc_id = f"{user_id}__{integration_id}"
        doc = await self._db.get(self._TOKENS_COLLECTION, doc_id)
        if not doc:
            return None

        encrypted = doc.get("encrypted_tokens")
        if not encrypted:
            return None

        tokens = _decrypt_tokens(encrypted, self._config.secret_key)
        # Re-attach expiry metadata
        tokens["expires_at"] = doc.get("expires_at")
        tokens["sync_cursor"] = doc.get("sync_cursor")
        return tokens

    async def update_sync_cursor(
        self,
        user_id: str,
        integration_id: str,
        cursor: Optional[str],
        last_synced_at: Optional[str] = None,
    ) -> None:
        """Update the sync cursor and last_synced_at after a successful sync."""
        doc_id = f"{user_id}__{integration_id}"
        await self._db.update(
            self._TOKENS_COLLECTION,
            doc_id,
            {
                "sync_cursor": cursor,
                "last_synced_at": last_synced_at or datetime.now(tz=timezone.utc).isoformat(),
                "status": IntegrationStatus.CONNECTED,
                "error_message": None,
            },
        )

    async def mark_error(
        self,
        user_id: str,
        integration_id: str,
        error: str,
    ) -> None:
        """Mark an integration as errored after a failed sync/refresh."""
        doc_id = f"{user_id}__{integration_id}"
        try:
            await self._db.update(
                self._TOKENS_COLLECTION,
                doc_id,
                {
                    "status": IntegrationStatus.ERROR,
                    "error_message": error,
                    "updated_at": datetime.now(tz=timezone.utc).isoformat(),
                },
            )
        except Exception as exc:
            logger.warning("Could not mark error for %s/%s: %s", user_id, integration_id, exc)

    # ─── Revocation ───────────────────────────────────────────────────────────

    async def revoke_tokens(
        self,
        user_id: str,
        integration_id: str,
    ) -> None:
        """
        Revoke tokens with the provider and delete from Firestore.

        Does not raise on provider revocation errors (tokens are deleted
        from Firestore regardless).
        """
        tokens = await self.load_tokens(user_id, integration_id)
        if tokens:
            provider = _get_provider_instance(integration_id)
            if provider:
                try:
                    await provider.disconnect(user_id, tokens)
                except Exception as exc:
                    logger.warning(
                        "Provider revocation failed for %s/%s: %s",
                        user_id,
                        integration_id,
                        exc,
                    )

        doc_id = f"{user_id}__{integration_id}"
        await self._db.delete(self._TOKENS_COLLECTION, doc_id)
        logger.info("Revoked and deleted tokens for user %s / %s", user_id, integration_id)

    # ─── Connected integrations listing ───────────────────────────────────────

    async def list_connected(self, user_id: str) -> list[dict[str, Any]]:
        """Return all connected integrations for a user (without token data)."""
        docs = await self._db.query_collection(
            self._TOKENS_COLLECTION,
            filters=[("user_id", "==", user_id)],
            limit=200,
        )
        result = []
        for doc in docs:
            result.append({
                "integration_id": doc.get("integration_id"),
                "status": doc.get("status", IntegrationStatus.CONNECTED),
                "connected_at": doc.get("connected_at"),
                "last_synced_at": doc.get("last_synced_at"),
                "scopes": doc.get("scopes", []),
                "error_message": doc.get("error_message"),
            })
        return result

    async def get_status(
        self,
        user_id: str,
        integration_id: str,
    ) -> Optional[dict[str, Any]]:
        """Return status metadata for one integration (no tokens)."""
        doc_id = f"{user_id}__{integration_id}"
        doc = await self._db.get(self._TOKENS_COLLECTION, doc_id)
        if not doc:
            return None
        return {
            "integration_id": integration_id,
            "status": doc.get("status", IntegrationStatus.AVAILABLE),
            "connected_at": doc.get("connected_at"),
            "last_synced_at": doc.get("last_synced_at"),
            "error_message": doc.get("error_message"),
            "sync_cursor": doc.get("sync_cursor"),
        }

    # ─── Internal helpers ─────────────────────────────────────────────────────

    async def _validate_state(
        self,
        state: str,
        user_id: str,
        integration_id: str,
    ) -> None:
        doc = await self._db.get(self._STATES_COLLECTION, state)
        if not doc:
            raise ValueError("Invalid or expired OAuth state token")

        expires_at_str = doc.get("expires_at", "")
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now(tz=timezone.utc) > expires_at:
                raise ValueError("OAuth state token has expired")
        except (ValueError, TypeError) as exc:
            if "expired" in str(exc):
                raise
            raise ValueError("Invalid OAuth state token format") from exc

        if doc.get("user_id") != user_id:
            raise ValueError("OAuth state user_id mismatch")
        if doc.get("integration_id") != integration_id:
            raise ValueError("OAuth state integration_id mismatch")


# ─── Crypto helpers ───────────────────────────────────────────────────────────

def _generate_state() -> str:
    """Generate a cryptographically secure random state token."""
    return secrets.token_urlsafe(32)


def _get_fernet() -> Fernet:
    """
    Return a Fernet instance using the key from the OAUTH_ENCRYPTION_KEY env var.

    The env var must contain a valid URL-safe base64-encoded 32-byte Fernet key
    (as produced by ``Fernet.generate_key()``).  Raises ``RuntimeError`` if
    the env var is missing or the key is malformed.
    """
    raw_key = os.environ.get("OAUTH_ENCRYPTION_KEY", "")
    if not raw_key:
        raise RuntimeError(
            "OAUTH_ENCRYPTION_KEY environment variable is not set. "
            "Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return Fernet(raw_key.encode() if isinstance(raw_key, str) else raw_key)


def _encrypt_tokens(tokens: dict[str, Any], secret: str) -> str:  # noqa: ARG001
    """
    Encrypt token dict using Fernet (AES-128-CBC + HMAC-SHA256).

    The ``secret`` parameter is accepted for API compatibility but is not used;
    the Fernet key is loaded from the OAUTH_ENCRYPTION_KEY env var.
    """
    fernet = _get_fernet()
    plaintext = json.dumps(tokens, default=str).encode()
    return fernet.encrypt(plaintext).decode()


def _decrypt_tokens(encrypted: str, secret: str) -> dict[str, Any]:  # noqa: ARG001
    """
    Decrypt tokens produced by :func:`_encrypt_tokens`.

    The ``secret`` parameter is accepted for API compatibility but is not used;
    the Fernet key is loaded from the OAUTH_ENCRYPTION_KEY env var.

    Raises:
        ValueError: if the token is invalid or has been tampered with.
    """
    fernet = _get_fernet()
    try:
        ciphertext = encrypted.encode() if isinstance(encrypted, str) else encrypted
        plaintext = fernet.decrypt(ciphertext)
        return json.loads(plaintext.decode())
    except InvalidToken as exc:
        logger.error("Failed to decrypt OAuth tokens: invalid or tampered ciphertext")
        raise ValueError("Invalid or tampered OAuth token ciphertext") from exc


def _compute_expiry(tokens: dict[str, Any]) -> Optional[str]:
    """Compute an ISO-8601 expiry timestamp from token ``expires_in`` field."""
    expires_in = tokens.get("expires_in")
    if isinstance(expires_in, (int, float)):
        return (
            datetime.now(tz=timezone.utc) + timedelta(seconds=int(expires_in))
        ).isoformat()
    return None


# ─── Module-level singleton ────────────────────────────────────────────────────

_oauth_service: OAuthService | None = None


def get_oauth_service() -> OAuthService:
    """Return the module-level OAuthService singleton."""
    global _oauth_service
    if _oauth_service is None:
        _oauth_service = OAuthService()
    return _oauth_service
