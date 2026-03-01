"""
ZenSensei User Service - User CRUD Service

Business logic for reading, updating, and deleting user profiles,
managing preferences, subscription tiers, and computing user statistics.

Falls back to in-memory storage when Firestore/Neo4j are unavailable.
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from typing import Any

import structlog

_shared_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if _shared_path not in sys.path:
    sys.path.insert(0, _shared_path)

from fastapi import HTTPException, status

from shared.models.user import LifeStage, SubscriptionTier, UserResponse, UserUpdate

from services.user_service.config import UserServiceConfig, get_user_service_config
from services.user_service.schemas import (
    SubscriptionResponse,
    SubscriptionUpdateRequest,
    UserPreferencesResponse,
    UserPreferencesUpdate,
    UserStatsResponse,
)
from services.user_service.services.auth_service import (
    _firestore_get_user_by_id,
    _firestore_update_user,
    _user_record_to_response,
    _users_store,
)

logger = structlog.get_logger(__name__)

# ─── In-memory fallback stores for preferences ────────────────────────────────
_preferences_store: dict[str, dict[str, Any]] = {}
_stats_store: dict[str, dict[str, Any]] = {}


# ─── Internal helpers ─────────────────────────────────────────────────────────


async def _get_user_or_404(user_id: str) -> dict[str, Any]:
    """Fetch a user record or raise 404."""
    record = await _firestore_get_user_by_id(user_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "USER_NOT_FOUND",
                "message": f"User '{user_id}' not found.",
            },
        )
    return record


async def _firestore_get_preferences(user_id: str) -> dict[str, Any] | None:
    """Fetch preferences from Firestore with in-memory fallback."""
    try:
        from shared.database.firestore import get_firestore_client
        client = get_firestore_client()
        if client._db is not None:
            return await client.get("user_preferences", user_id)
    except Exception as exc:
        logger.warning("Firestore unavailable for preferences", error=str(exc))
    return _preferences_store.get(user_id)


async def _firestore_set_preferences(user_id: str, data: dict[str, Any]) -> None:
    """Persist preferences to Firestore with in-memory fallback."""
    try:
        from shared.database.firestore import get_firestore_client
        client = get_firestore_client()
        if client._db is not None:
            await client.set("user_preferences", user_id, data, merge=True)
            return
    except Exception as exc:
        logger.warning("Firestore unavailable for preferences", error=str(exc))
    existing = _preferences_store.get(user_id, {})
    existing.update(data)
    _preferences_store[user_id] = existing


# ─── User CRUD ────────────────────────────────────────────────────────────────


async def get_user(user_id: str) -> UserResponse:
    """
    Retrieve a public-safe user profile by ID.

    Raises:
        HTTPException 404 if the user does not exist.
    """
    record = await _get_user_or_404(user_id)
    logger.debug("Fetched user profile", user_id=user_id)
    return _user_record_to_response(record)


async def update_user(
    user_id: str,
    update: UserUpdate,
    requesting_user_id: str,
) -> UserResponse:
    """
    Apply a partial update to a user's profile.

    Only the user themselves (or an admin) may update their profile.

    Raises:
        HTTPException 403 if the requester is not the profile owner.
        HTTPException 404 if the user does not exist.
    """
    if user_id != requesting_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "FORBIDDEN",
                "message": "You can only update your own profile.",
            },
        )

    record = await _get_user_or_404(user_id)

    update_data: dict[str, Any] = update.model_dump(exclude_none=True, exclude_unset=True)
    if not update_data:
        return _user_record_to_response(record)

    # Normalise email if provided
    if "email" in update_data:
        update_data["email"] = update_data["email"].lower().strip()

    # Update is_premium derived field when subscription_tier changes
    if "subscription_tier" in update_data:
        tier = SubscriptionTier(update_data["subscription_tier"])
        update_data["is_premium"] = tier in (SubscriptionTier.PREMIUM, SubscriptionTier.PRO)

    update_data["updated_at"] = datetime.now(tz=timezone.utc)

    await _firestore_update_user(user_id, update_data)

    # Merge into cached record for response
    record.update(update_data)
    logger.info("User profile updated", user_id=user_id, fields=list(update_data.keys()))
    return _user_record_to_response(record)


async def delete_user(user_id: str, requesting_user_id: str) -> None:
    """
    Soft-delete a user by setting ``is_active=False``.

    The user record is retained in Firestore for audit / recovery purposes.

    Raises:
        HTTPException 403 if the requester is not the profile owner.
        HTTPException 404 if the user does not exist.
    """
    if user_id != requesting_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "FORBIDDEN",
                "message": "You can only delete your own account.",
            },
        )

    record = await _get_user_or_404(user_id)

    if not record.get("is_active", True):
        # Already deactivated — idempotent
        return

    now = datetime.now(tz=timezone.utc)
    await _firestore_update_user(
        user_id,
        {
            "is_active": False,
            "deactivated_at": now,
            "updated_at": now,
        },
    )
    logger.info("User soft-deleted", user_id=user_id)


# ─── Preferences ────────────────────────────────────────────────────────────────


async def get_user_preferences(user_id: str) -> UserPreferencesResponse:
    """
    Retrieve per-user notification and privacy preferences.

    Returns default preferences if none have been saved yet.
    """
    await _get_user_or_404(user_id)  # Ensure user exists

    raw = await _firestore_get_preferences(user_id)
    if raw:
        prefs_data = {**raw, "user_id": user_id}
    else:
        prefs_data = {"user_id": user_id}

    return UserPreferencesResponse(**prefs_data)


async def update_user_preferences(
    user_id: str,
    update: UserPreferencesUpdate,
    requesting_user_id: str,
) -> UserPreferencesResponse:
    """
    Partially update user preferences.

    Raises:
        HTTPException 403 if the requester is not the profile owner.
        HTTPException 404 if the user does not exist.
    """
    if user_id != requesting_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "FORBIDDEN",
                "message": "You can only update your own preferences.",
            },
        )

    await _get_user_or_404(user_id)

    update_data = update.model_dump(exclude_none=True, exclude_unset=True)
    if update_data:
        await _firestore_set_preferences(user_id, update_data)
        logger.info("Preferences updated", user_id=user_id, fields=list(update_data.keys()))

    # Return merged preferences
    raw = await _firestore_get_preferences(user_id) or {}
    return UserPreferencesResponse(user_id=user_id, **raw)


# ─── Subscription ─────────────────────────────────────────────────────────────────


_TIER_FEATURES: dict[str, list[str]] = {
    SubscriptionTier.FREE: [
        "basic_goals",
        "basic_tasks",
        "limited_insights",
    ],
    SubscriptionTier.PREMIUM: [
        "basic_goals",
        "basic_tasks",
        "unlimited_insights",
        "priority_support",
        "advanced_analytics",
        "integrations",
    ],
    SubscriptionTier.PRO: [
        "basic_goals",
        "basic_tasks",
        "unlimited_insights",
        "priority_support",
        "advanced_analytics",
        "integrations",
        "ai_coaching",
        "custom_reports",
        "team_features",
        "api_access",
    ],
}


async def get_subscription(user_id: str) -> SubscriptionResponse:
    """Return a user's current subscription details."""
    record = await _get_user_or_404(user_id)
    tier = SubscriptionTier(record.get("subscription_tier", SubscriptionTier.FREE))

    return SubscriptionResponse(
        user_id=user_id,
        tier=tier,
        is_premium=tier in (SubscriptionTier.PREMIUM, SubscriptionTier.PRO),
        started_at=record.get("subscription_started_at"),
        expires_at=record.get("subscription_expires_at"),
        auto_renew=record.get("subscription_auto_renew", False),
        billing_cycle=record.get("subscription_billing_cycle"),
        features=_TIER_FEATURES.get(tier, []),
    )


async def update_subscription(
    user_id: str,
    update: SubscriptionUpdateRequest,
    requesting_user_id: str,
) -> SubscriptionResponse:
    """
    Update a user's subscription tier.

    In production this would integrate with Stripe/billing. For now it
    directly updates the Firestore record.

    Raises:
        HTTPException 403 if the requester is not the profile owner.
    """
    if user_id != requesting_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "FORBIDDEN",
                "message": "You can only update your own subscription.",
            },
        )

    await _get_user_or_404(user_id)

    tier = update.tier
    now = datetime.now(tz=timezone.utc)

    update_payload: dict[str, Any] = {
        "subscription_tier": str(tier),
        "is_premium": tier in (SubscriptionTier.PREMIUM, SubscriptionTier.PRO),
        "subscription_started_at": now,
        "updated_at": now,
    }
    if update.billing_cycle:
        update_payload["subscription_billing_cycle"] = update.billing_cycle

    await _firestore_update_user(user_id, update_payload)
    logger.info("Subscription updated", user_id=user_id, tier=tier)

    return await get_subscription(user_id)


# ─── Statistics ────────────────────────────────────────────────────────────────


async def get_user_stats(user_id: str) -> UserStatsResponse:
    """
    Compute aggregated statistics for a user.

    Queries Firestore collections for goals and tasks, and Neo4j for
    insights. Falls back to zero-value stats when services are unavailable.
    """
    record = await _get_user_or_404(user_id)

    goals_count = 0
    active_goals_count = 0
    tasks_count = 0
    completed_tasks_count = 0
    insights_count = 0

    # ── Goals ────────────────────────────────────────────────────────────────
    try:
        from shared.database.firestore import get_firestore_client
        client = get_firestore_client()
        if client._db is not None:
            goals = await client.query_collection(
                "goals",
                filters=[("user_id", "==", user_id)],
                limit=1000,
            )
            goals_count = len(goals)
            active_goals_count = sum(
                1 for g in goals if g.get("status") in ("ACTIVE", "IN_PROGRESS")
            )

            tasks = await client.query_collection(
                "tasks",
                filters=[("user_id", "==", user_id)],
                limit=1000,
            )
            tasks_count = len(tasks)
            completed_tasks_count = sum(
                1 for t in tasks if t.get("status") == "COMPLETED"
            )
    except Exception as exc:
        logger.warning("Could not fetch goals/tasks stats from Firestore", error=str(exc))

    # ── Insights ───────────────────────────────────────────────────────────────
    try:
        from shared.database.neo4j import get_neo4j_client
        neo4j = get_neo4j_client()
        if neo4j._driver is not None:
            result = await neo4j.run_query_single(
                "MATCH (p:Person {id: $id})-[:RECEIVES]->(i:Insight) RETURN count(i) AS cnt",
                {"id": user_id},
            )
            insights_count = int(result.get("cnt", 0)) if result else 0
    except Exception as exc:
        logger.warning("Could not fetch insights count from Neo4j", error=str(exc))

    # ── Streak (in-memory stats store, extendable) ───────────────────────────────
    cached_stats = _stats_store.get(user_id, {})
    current_streak = cached_stats.get("current_streak_days", 0)
    longest_streak = cached_stats.get("longest_streak_days", 0)

    created_at = record.get("created_at")
    last_active = record.get("last_active_at")

    return UserStatsResponse(
        user_id=user_id,
        goals_count=goals_count,
        active_goals_count=active_goals_count,
        tasks_count=tasks_count,
        completed_tasks_count=completed_tasks_count,
        insights_count=insights_count,
        current_streak_days=current_streak,
        longest_streak_days=longest_streak,
        member_since=created_at,
        last_active_at=last_active,
    )
