"""
ZenSensei Integration Service - Plaid Banking Integration

Uses Plaid Link flow (not standard OAuth) to connect bank accounts.
Syncs transactions and balances as FinancialArtifact nodes in the graph.

Graph mapping
-------------
Transaction      → NodeType.FINANCIAL_ARTIFACT
  - properties: amount, merchant, category, date, account_id, transaction_id
Balance snapshot → NodeType.FINANCIAL_ARTIFACT (type=balance)
  - properties: available, current, iso_currency_code, account_id

Plaid flow
----------
1. POST /integrations/plaid/connect → server calls plaid.link_token_create()
                                     returns link_token to frontend
2. Frontend shows Plaid Link modal; user connects account
3. Frontend receives public_token → POST /integrations/plaid/callback
4. Server calls plaid.item_public_token_exchange() → access_token stored
5. Sync: plaid.transactions_sync() with incremental cursor
"""

from __future__ import annotations

import logging
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

_PLAID_BASE_URLS = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}


def _plaid_url(path: str) -> str:
    env = "sandbox" if _cfg.is_development else "production"
    return f"{_PLAID_BASE_URLS[env]}{path}"


class PlaidIntegration(Integration):
    """
    Plaid banking integration using Plaid Link flow.

    Not standard OAuth — uses a two-step Link token → public token
    → access token exchange.
    """

    metadata: IntegrationMetadata = get_by_id("plaid")  # type: ignore[assignment]

    # ─── Plaid Link helpers (called by the router, not the standard OAuth flow) ─

    async def create_link_token(self, user_id: str, redirect_uri: str) -> dict[str, Any]:
        """
        Create a Plaid Link token to initialise the frontend Link modal.

        Returns a dict containing ``link_token`` and ``expiration``.
        """
        if _cfg.is_development and not _cfg.plaid_client_id:
            logger.info("plaid: returning mock link token (dev mode)")
            return {
                "link_token": "link-sandbox-mock-token-abc123",
                "expiration": (datetime.now(tz=timezone.utc) + timedelta(minutes=30)).isoformat(),
                "request_id": "mock-req-001",
            }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _plaid_url("/link/token/create"),
                json={
                    "client_id": _cfg.plaid_client_id,
                    "secret": _cfg.plaid_secret,
                    "client_name": "ZenSensei",
                    "user": {"client_user_id": user_id},
                    "products": ["transactions"],
                    "country_codes": ["US"],
                    "language": "en",
                    "redirect_uri": redirect_uri,
                    "webhook": f"https://api.zensensei.net/webhooks/plaid",
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def exchange_public_token(self, public_token: str) -> dict[str, Any]:
        """
        Exchange a Plaid public token for a persistent access token.

        Returns dict with ``access_token`` and ``item_id``.
        """
        if _cfg.is_development and public_token.startswith("public-sandbox-mock"):
            return {
                "access_token": "mock_plaid_access_sandbox_abc123",
                "item_id": "mock-item-001",
                "request_id": "mock-req-002",
            }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _plaid_url("/item/public_token/exchange"),
                json={
                    "client_id": _cfg.plaid_client_id,
                    "secret": _cfg.plaid_secret,
                    "public_token": public_token,
                },
            )
            resp.raise_for_status()
            return resp.json()

    # ─── Integration ABC (Plaid doesn't use standard OAuth URLs) ─────────────

    async def get_oauth_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: Optional[list[str]] = None,
    ) -> str:
        """
        For Plaid, returns the link_token instead of a URL.

        The router extracts this and returns it to the frontend so it can
        open the Plaid Link modal.
        """
        raise NotImplementedError(
            "Plaid uses create_link_token() instead of get_oauth_url(). "
            "Call PlaidIntegration().create_link_token() from the router."
        )

    async def authorize(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange a Plaid public_token (passed as ``code``) for an access_token."""
        return await self.exchange_public_token(public_token=code)

    async def refresh_tokens(self, refresh_token: str) -> dict[str, Any]:
        """Plaid access tokens don't expire — no-op refresh."""
        return {"access_token": refresh_token}

    async def disconnect(self, user_id: str, tokens: dict[str, Any]) -> None:
        """Remove the Plaid item (revokes access_token server-side)."""
        access_token = tokens.get("access_token", "")
        if not access_token or _cfg.is_development:
            logger.info("plaid: skipping item removal in dev mode")
            return

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                await client.post(
                    _plaid_url("/item/remove"),
                    json={
                        "client_id": _cfg.plaid_client_id,
                        "secret": _cfg.plaid_secret,
                        "access_token": access_token,
                    },
                )
            except httpx.HTTPError as exc:
                logger.warning("Failed to remove Plaid item: %s", exc)

    # ─── Sync ─────────────────────────────────────────────────────────────────────────────

    async def sync(
        self,
        user_id: str,
        tokens: dict[str, Any],
        last_sync: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Fetch transactions via /transactions/sync (cursor-based incremental).
        Also fetches current account balances.
        """
        if _cfg.is_development and tokens.get("access_token", "").startswith("mock_"):
            logger.info("plaid: returning mock transactions (dev mode)")
            return _mock_transactions()

        access_token = tokens["access_token"]
        cursor: Optional[str] = tokens.get("sync_cursor")

        added: list[dict[str, Any]] = []
        modified: list[dict[str, Any]] = []
        removed: list[str] = []
        has_more = True

        async with httpx.AsyncClient(timeout=30) as client:
            while has_more:
                body: dict[str, Any] = {
                    "client_id": _cfg.plaid_client_id,
                    "secret": _cfg.plaid_secret,
                    "access_token": access_token,
                }
                if cursor:
                    body["cursor"] = cursor

                resp = await client.post(_plaid_url("/transactions/sync"), json=body)
                resp.raise_for_status()
                data = resp.json()

                added.extend(data.get("added", []))
                modified.extend(data.get("modified", []))
                removed.extend([r["transaction_id"] for r in data.get("removed", [])])
                cursor = data.get("next_cursor")
                has_more = data.get("has_more", False)

            # Fetch balances
            balances_resp = await client.post(
                _plaid_url("/accounts/balance/get"),
                json={
                    "client_id": _cfg.plaid_client_id,
                    "secret": _cfg.plaid_secret,
                    "access_token": access_token,
                },
            )
            balances_resp.raise_for_status()
            balances = balances_resp.json().get("accounts", [])

        return {
            "added": added,
            "modified": modified,
            "removed": removed,
            "balances": balances,
            "sync_cursor": cursor,
        }

    # ─── Graph transformation ──────────────────────────────────────────────────────────────────────

    async def push_update(
        self,
        user_id: str,
        raw_data: dict[str, Any],
    ) -> tuple[list[GraphNode], list[GraphRelationship]]:
        """Transform Plaid transactions and balances into FinancialArtifact nodes."""
        import uuid

        nodes: list[GraphNode] = []
        relationships: list[GraphRelationship] = []

        # ── Transactions ──
        for txn in raw_data.get("added", []) + raw_data.get("modified", []):
            txn_id = txn.get("transaction_id", str(uuid.uuid4()))
            node_id = f"financial:{user_id}:txn:{txn_id}"

            amount = txn.get("amount", 0)
            # Plaid: positive = debit (money out), negative = credit (money in)
            direction = "debit" if amount >= 0 else "credit"

            node = GraphNode(
                id=node_id,
                type=NodeType.FINANCIAL_ARTIFACT,
                schema_scope=f"user:{user_id}",
                properties={
                    "artifact_type": "transaction",
                    "transaction_id": txn_id,
                    "amount": abs(amount),
                    "direction": direction,
                    "iso_currency_code": txn.get("iso_currency_code", "USD"),
                    "merchant_name": txn.get("merchant_name") or txn.get("name", ""),
                    "category": txn.get("category", []),
                    "category_id": txn.get("category_id", ""),
                    "date": txn.get("date", ""),
                    "authorized_date": txn.get("authorized_date"),
                    "account_id": txn.get("account_id", ""),
                    "pending": txn.get("pending", False),
                    "payment_channel": txn.get("payment_channel", ""),
                    "source": "plaid",
                },
            )
            nodes.append(node)

        # ── Balances ──
        for account in raw_data.get("balances", []):
            acct_id = account.get("account_id", str(uuid.uuid4()))
            node_id = f"financial:{user_id}:balance:{acct_id}"
            balance = account.get("balances", {})

            node = GraphNode(
                id=node_id,
                type=NodeType.FINANCIAL_ARTIFACT,
                schema_scope=f"user:{user_id}",
                properties={
                    "artifact_type": "balance",
                    "account_id": acct_id,
                    "account_name": account.get("name", ""),
                    "account_type": account.get("type", ""),
                    "account_subtype": account.get("subtype", ""),
                    "available": balance.get("available"),
                    "current": balance.get("current"),
                    "limit": balance.get("limit"),
                    "iso_currency_code": balance.get("iso_currency_code", "USD"),
                    "source": "plaid",
                    "snapshot_at": datetime.now(tz=timezone.utc).isoformat(),
                },
            )
            nodes.append(node)

        logger.info(
            "plaid: transformed %d transactions + %d balances → %d nodes for user %s",
            len(raw_data.get("added", [])) + len(raw_data.get("modified", [])),
            len(raw_data.get("balances", [])),
            len(nodes),
            user_id,
        )
        return nodes, relationships


# ─── Mock helpers ─────────────────────────────────────────────────────────────────────────────

def _mock_transactions() -> dict[str, Any]:
    today = datetime.now(tz=timezone.utc)
    return {
        "added": [
            {
                "transaction_id": "txn_mock_001",
                "account_id": "acct_mock_checking",
                "amount": 12.50,
                "iso_currency_code": "USD",
                "merchant_name": "Blue Bottle Coffee",
                "name": "BLUE BOTTLE COFFEE",
                "category": ["Food and Drink", "Restaurants", "Coffee Shop"],
                "category_id": "13005032",
                "date": today.strftime("%Y-%m-%d"),
                "pending": False,
                "payment_channel": "in store",
            },
            {
                "transaction_id": "txn_mock_002",
                "account_id": "acct_mock_checking",
                "amount": 240.00,
                "iso_currency_code": "USD",
                "merchant_name": "Whole Foods Market",
                "name": "WHOLEFDS MKT",
                "category": ["Shops", "Supermarkets and Groceries"],
                "category_id": "19046000",
                "date": (today - timedelta(days=2)).strftime("%Y-%m-%d"),
                "pending": False,
                "payment_channel": "in store",
            },
            {
                "transaction_id": "txn_mock_003",
                "account_id": "acct_mock_checking",
                "amount": -3500.00,  # salary (credit)
                "iso_currency_code": "USD",
                "merchant_name": None,
                "name": "DIRECT DEP EMPLOYER",
                "category": ["Transfer", "Credit"],
                "category_id": "21007000",
                "date": (today - timedelta(days=5)).strftime("%Y-%m-%d"),
                "pending": False,
                "payment_channel": "online",
            },
        ],
        "modified": [],
        "removed": [],
        "balances": [
            {
                "account_id": "acct_mock_checking",
                "name": "Primary Checking",
                "type": "depository",
                "subtype": "checking",
                "balances": {
                    "available": 4823.67,
                    "current": 4823.67,
                    "limit": None,
                    "iso_currency_code": "USD",
                },
            },
            {
                "account_id": "acct_mock_savings",
                "name": "High-Yield Savings",
                "type": "depository",
                "subtype": "savings",
                "balances": {
                    "available": 15200.00,
                    "current": 15200.00,
                    "limit": None,
                    "iso_currency_code": "USD",
                },
            },
        ],
        "sync_cursor": "mock_cursor_abc123",
    }
