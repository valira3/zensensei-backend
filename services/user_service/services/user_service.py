"""
ZenSensei User Service - User CRUD Service

Business logic for reading, updating, and deleting user accounts.
Handles profile management, preferences, subscription tracking,
onboarding state, and cascading deletion across all services.

Falls back to in-memory storage when Firestore/Neo4j are unavailable.
"""

from __future__ import annotations

import sys
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

_shared_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if _shared_path not in sys.path:
    sys.path.insert(0, _shared_path)

from fastapi import HTTPException, status

from shared.models.user import LifeStage, SubscriptionTier, UserResponse

logger = structlog.get_logger(__name__)


# ─── In-memory fallback (mirrors auth_service) ───────────────────────────────────

# Shared with auth_service via module reference; import lazily to avoid circular deps.
def _get_users_store() -> dict[str, dict[str, Any]]:
    from services.user_service.services import auth_service
    return auth_service._users_store


def _get_email_index() -> dict[str, str]:
    from services.user_service.services import auth_service
    return auth_service._email_index


# ─── Firestore helpers ───────────────────────────────────────────────────────────


async def _fs_get(user_id: str) -> dict[str, Any] | None:
    try:
        from shared.database.firestore import get_firestore_client
        client = get_firestore_client()
        if client._db is not None:
            return await client.get("users", user_id)
    except Exception as exc:
        logger.warning("Firestore unavailable", error=str(exc))
    return _get_users_store().get(user_id)


async def _fs_update(user_id: str, data: dict[str, Any]) -> None:
    try:
        from shared.database.firestore import get_firestore_client
        client = get_firestore_client()
        if client._db is not None:
            await client.update("users", user_id, data)
            return
    except Exception as exc:
        logger.warning("Firestore unavailable", error=str(exc))
    store = _get_users_store()
    if user_id in store:
        store[user_id].update(data)


async def _fs_delete(user_id: str) -> None:
    try:
        from shared.database.firestore import get_firestore_client
        client = get_firestore_client()
        if client._db is not None:
            await client.delete("users", user_id)
            return
    except Exception as exc:
        logger.warning("Firestore unavailable", error=str(exc))
    store = _get_users_store()
    record = store.pop(user_id, None)
    if record:
        _get_email_index().pop(record.get("email", ""), None)


# ─── Public API ───────────────────────────────────────────────────────────────


async def get_user(user_id: str) -> dict[str, Any] | None:
    """Return a user's public profile dict, or None if not found."""
    record = await _fs_get(user_id)
    if not record:
        return None
    # Strip sensitive fields before returning
    safe = {k: v for k, v in record.items() if k not in ("hashed_password",)}
    return safe


async def update_user(
    user_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """
    Apply a partial update to a user's profile.

    Allowed fields: display_name, avatar_url, life_stage, bio.
    Raises HTTPException 404 if user not found.
    """
    _ALLOWED = {"display_name", "avatar_url", "life_stage", "bio"}
    filtered = {k: v for k, v in updates.items() if k in _ALLOWED}
    if not filtered:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No updatable fields provided.",
        )

    filtered["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
    await _fs_update(user_id, filtered)

    record = await _fs_get(user_id)
    if not record:
        raise HTTPException(status_code=404, detail="User not found.")
    return {k: v for k, v in record.items() if k != "hashed_password"}


async def delete_user(user_id: str) -> None:
    """
    Permanently delete a user account and cascade to related services.

    Raises HTTPException 404 if user not found.
    """
    record = await _fs_get(user_id)
    if not record:
        raise HTTPException(status_code=404, detail="User not found.")

    # Cascade: delete Neo4j Person node
    try:
        from shared.database.neo4j import get_neo4j_client
        client = get_neo4j_client()
        if client._driver is not None:
            await client.run_query(
                "MATCH (p:Person {id: $id}) DETACH DELETE p",
                {"id": user_id},
            )
    except Exception as exc:
        logger.warning("Neo4j cascade delete failed", user_id=user_id, error=str(exc))

    await _fs_delete(user_id)
    logger.info("User deleted", user_id=user_id)


async def update_subscription(
    user_id: str,
    tier: SubscriptionTier,
) -> dict[str, Any]:
    """
    Update the subscription tier for a user (admin operation).

    Raises HTTPException 404 if user not found.
    """
    record = await _fs_get(user_id)
    if not record:
        raise HTTPException(status_code=404, detail="User not found.")

    is_premium = tier != SubscriptionTier.FREE
    await _fs_update(user_id, {
        "subscription_tier": tier,
        "is_premium": is_premium,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
    })

    record = await _fs_get(user_id)
    return {k: v for k, v in record.items() if k != "hashed_password"}
