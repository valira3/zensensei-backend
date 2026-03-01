"""
ZenSensei Integration Service - Abstract Base Integration

Defines the Integration ABC that every provider implementation must satisfy,
plus the IntegrationMetadata value-object that populates the registry.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from shared.models.graph import GraphNode, GraphRelationship
from shared.models.integrations import IntegrationCategory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntegrationMetadata:
    """
    Immutable descriptor for an integration registered in the catalogue.

    All fields are used directly by the frontend to render the
    integrations marketplace UI.
    """

    id: str
    """Unique slug, e.g. ``'google_calendar'``."""

    name: str
    """Human-readable display name, e.g. ``'Google Calendar'``."""

    category: IntegrationCategory
    """High-level category grouping."""

    icon_name: str
    """
    Iconify / Lucide icon identifier used by the frontend.
    Convention: ``'logos:<provider>'`` for branded logos,
    ``'lucide:<icon>'`` for generic icons.
    """

    description: str
    """Short sentence describing what data this integration syncs."""

    required_scopes: list[str] = field(default_factory=list)
    """OAuth scopes requested during the authorization flow."""

    oauth_url_template: Optional[str] = None
    """
    Authorization URL template.  Use ``{client_id}``, ``{redirect_uri}``,
    ``{scopes}``, and ``{state}`` as placeholders.
    """

    supports_webhook: bool = False
    """
    ``True`` if the provider can push data via webhooks in addition to
    (or instead of) polling-based sync.
    """

    poll_interval_minutes: int = 15
    """How often the sync engine polls this integration (minutes)."""

    is_oauth: bool = True
    """
    ``False`` for integrations that use API keys or link tokens
    (e.g. Plaid) instead of standard OAuth.
    """


# ─── Abstract base class ───────────────────────────────────────────────────────


class Integration(ABC):
    """
    Abstract base class for all ZenSensei provider integrations.

    Subclasses implement provider-specific OAuth, data fetching,
    and graph transformation logic while the sync engine calls
    the standard interface.

    Lifecycle::

        integration = MyIntegration(config)
        auth_url = await integration.get_oauth_url(redirect_uri)
        # ... user visits auth_url, gets redirected back with code ...
        tokens = await integration.authorize(code, redirect_uri)
        raw_data = await integration.sync(user_id, tokens, last_sync=None)
        nodes, rels = await integration.push_update(user_id, raw_data)
        await integration.disconnect(user_id, tokens)
    """

    # Subclasses MUST set metadata at class level
    metadata: IntegrationMetadata

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Validate that concrete (non-abstract) subclasses declare metadata
        if not getattr(cls, "__abstractmethods__", None) and not hasattr(cls, "metadata"):
            raise TypeError(
                f"Concrete Integration subclass '{cls.__name__}' must define a "
                "'metadata' class attribute of type IntegrationMetadata."
            )

    # ─── OAuth ───────────────────────────────────────────────────────────────────────────

    @abstractmethod
    async def get_oauth_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: Optional[list[str]] = None,
    ) -> str:
        """
        Build and return the provider authorization URL.

        Args:
            redirect_uri: Callback URL registered with the OAuth provider.
            state: CSRF-protection state token.
            scopes: Override the default required_scopes if provided.

        Returns:
            Fully-formed authorization URL string.
        """

    @abstractmethod
    async def authorize(
        self,
        code: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        """
        Exchange an authorization code for access + refresh tokens.

        Args:
            code: Authorization code received in the OAuth callback.
            redirect_uri: Must match the URI used in :meth:`get_oauth_url`.

        Returns:
            Token dict with at minimum ``access_token``, optionally
            ``refresh_token``, ``expires_in``, ``scope``.
        """

    @abstractmethod
    async def refresh_tokens(
        self,
        refresh_token: str,
    ) -> dict[str, Any]:
        """
        Obtain a fresh access token using a stored refresh token.

        Returns:
            Updated token dict.
        """

    @abstractmethod
    async def disconnect(
        self,
        user_id: str,
        tokens: dict[str, Any],
    ) -> None:
        """
        Revoke provider-side tokens and clean up any stored credentials.

        Args:
            user_id: ZenSensei user ID.
            tokens: Currently stored token dict for the user.
        """

    # ─── Data sync ──────────────────────────────────────────────────────────────────────────

    @abstractmethod
    async def sync(
        self,
        user_id: str,
        tokens: dict[str, Any],
        last_sync: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Fetch raw data from the provider API.

        Args:
            user_id: ZenSensei user ID.
            tokens: Valid token dict (refresh first if needed).
            last_sync: ISO-8601 timestamp of the previous successful sync;
                ``None`` for the initial full sync.

        Returns:
            Provider-specific raw data dict that will be passed to
            :meth:`push_update`.
        """

    @abstractmethod
    async def push_update(
        self,
        user_id: str,
        raw_data: dict[str, Any],
    ) -> tuple[list[GraphNode], list[GraphRelationship]]:
        """
        Transform raw provider data into graph nodes + relationships.

        Args:
            user_id: ZenSensei user ID (used to scope nodes).
            raw_data: Output of :meth:`sync`.

        Returns:
            Tuple of ``(nodes, relationships)`` ready to upsert into the
            knowledge graph via the Graph Query Service.
        """

    # ─── Optional hook ─────────────────────────────────────────────────────────────────────────

    async def handle_webhook(
        self,
        user_id: str,
        payload: dict[str, Any],
        tokens: dict[str, Any],
    ) -> tuple[list[GraphNode], list[GraphRelationship]]:
        """
        Process an inbound webhook payload (optional).

        The default implementation delegates to :meth:`push_update` after
        wrapping the payload in a ``{"webhook": payload}`` envelope.
        Override for provider-specific webhook handling.
        """
        logger.info(
            "handle_webhook default: delegating to push_update",
            extra={"integration": self.metadata.id, "user_id": user_id},
        )
        return await self.push_update(user_id, {"webhook": payload})

    # ─── Convenience ─────────────────────────────────────────────────────────────────────────

    @property
    def id(self) -> str:
        """Shorthand for ``self.metadata.id``."""
        return self.metadata.id

    def __repr__(self) -> str:
        return f"<Integration id={self.metadata.id!r} name={self.metadata.name!r}>"
